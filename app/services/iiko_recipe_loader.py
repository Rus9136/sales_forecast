"""Loader for iiko assembly charts (recipes / tech cards).

Fetches bulk via GET /resto/api/v2/assemblyCharts/getAll?dateFrom=...
and upserts into recipe + recipe_ingredient tables.

Strategy:
  1. Fetch all assemblyCharts for each domain (one HTTP call per domain, ~40 МБ Sandy)
  2. Resolve assembledProductId → product.id  (batch)
  3. Upsert recipes via execute_values ON CONFLICT (iiko_source_domain, iiko_assembly_chart_id)
  4. Delete + re-insert ingredients for upserted recipes
  5. Resolve ingredient productId → product.id  (batch)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx
from psycopg2.extras import Json, execute_values
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)


def _domain_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or url


class IikoRecipeLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def fetch_from_single_domain(self, base_url: str) -> List[dict]:
        host = _domain_host(base_url)
        try:
            auth = IikoAuthService(base_url)
            token = await auth._refresh_token()

            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.get(
                    f"{base_url}/resto/api/v2/assemblyCharts/getAll",
                    params={"key": token, "dateFrom": "2020-01-01"},
                )
                resp.raise_for_status()
                data = resp.json()
                charts = data.get("assemblyCharts") or []
                logger.info(f"{host}: fetched {len(charts)} assembly charts")
                return charts

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching recipes from {host}: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"status={e.response.status_code} body={e.response.text[:300]}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching recipes from {host}: {e}", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # FK resolution
    # ------------------------------------------------------------------

    def _build_product_map(self, domain: str, uuids: Set[str]) -> Dict[str, int]:
        """Map iiko product UUID (str) → product.id (BIGINT)."""
        if not uuids:
            return {}
        rows = self.db.execute(
            text("""
                SELECT iiko_product_id::text, id
                FROM product
                WHERE iiko_source_domain = :domain
                  AND iiko_product_id = ANY(:ids ::uuid[])
            """),
            {"domain": domain, "ids": list(uuids)},
        ).fetchall()
        return {str(r[0]): r[1] for r in rows}

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def _upsert_recipes(
        self,
        charts: List[dict],
        domain: str,
        product_map: Dict[str, int],
    ) -> Tuple[int, int]:
        """Upsert recipes + ingredients. Returns (recipe_count, ingredient_count)."""
        if not charts:
            return 0, 0

        now = datetime.utcnow()
        conn = self.db.connection().connection

        # Filter charts where assembledProductId resolves
        valid_charts = []
        for c in charts:
            pid = product_map.get(c["assembledProductId"])
            if pid:
                valid_charts.append((c, pid))

        if not valid_charts:
            return 0, 0

        # 1. Upsert recipe headers
        recipe_rows = []
        for c, pid in valid_charts:
            recipe_rows.append((
                domain,
                c["id"],
                pid,
                c.get("dateFrom"),
                c.get("dateTo"),
                c.get("assembledAmount", 1),
                c.get("description") or None,
                c.get("technologyDescription") or None,
                Json({k: v for k, v in c.items() if k not in ("items",)}),
                now,
            ))

        with conn.cursor() as cur:
            returned = execute_values(
                cur,
                """
                INSERT INTO recipe (
                    iiko_source_domain, iiko_assembly_chart_id, product_id,
                    date_from, date_to, assembled_amount,
                    description, technology_description, iiko_payload, synced_at
                ) VALUES %s
                ON CONFLICT (iiko_source_domain, iiko_assembly_chart_id) DO UPDATE SET
                    product_id = EXCLUDED.product_id,
                    date_from = EXCLUDED.date_from,
                    date_to = EXCLUDED.date_to,
                    assembled_amount = EXCLUDED.assembled_amount,
                    description = EXCLUDED.description,
                    technology_description = EXCLUDED.technology_description,
                    iiko_payload = EXCLUDED.iiko_payload,
                    synced_at = EXCLUDED.synced_at
                RETURNING id, iiko_assembly_chart_id
                """,
                recipe_rows,
                template="(%s, %s::uuid, %s, %s::date, %s::date, %s, %s, %s, %s::jsonb, %s)",
                fetch=True,
            )
            chart_id_to_db: Dict[str, int] = {str(uuid): db_id for db_id, uuid in returned}
            recipe_count = len(returned)

            # 2. Delete existing ingredients for these recipes
            recipe_ids = list(chart_id_to_db.values())
            if recipe_ids:
                cur.execute(
                    "DELETE FROM recipe_ingredient WHERE recipe_id = ANY(%s)",
                    (recipe_ids,),
                )

            # 3. Collect all ingredient product UUIDs and resolve
            all_ing_uuids: Set[str] = set()
            for c, _ in valid_charts:
                for it in (c.get("items") or []):
                    if it.get("productId"):
                        all_ing_uuids.add(it["productId"])

            ing_product_map = self._build_product_map(domain, all_ing_uuids)

            # 4. Insert ingredients
            ing_rows = []
            for c, _ in valid_charts:
                recipe_db_id = chart_id_to_db.get(c["id"])
                if not recipe_db_id:
                    continue
                for it in (c.get("items") or []):
                    ing_pid = ing_product_map.get(it.get("productId")) if it.get("productId") else None
                    ing_rows.append((
                        recipe_db_id,
                        it.get("id"),
                        ing_pid,
                        it.get("productId"),
                        it.get("sortWeight", 0),
                        it.get("amountIn", 0),
                        it.get("amountMiddle"),
                        it.get("amountOut"),
                        now,
                    ))

            ingredient_count = 0
            if ing_rows:
                execute_values(
                    cur,
                    """
                    INSERT INTO recipe_ingredient (
                        recipe_id, iiko_item_id, ingredient_product_id,
                        iiko_ingredient_product_id, sort_weight,
                        amount_in, amount_middle, amount_out, synced_at
                    ) VALUES %s
                    """,
                    ing_rows,
                    template="(%s, %s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s)",
                )
                ingredient_count = len(ing_rows)

        return recipe_count, ingredient_count

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def sync(self) -> dict:
        total_recipes = 0
        total_ingredients = 0
        per_domain: List[dict] = []
        errors: List[str] = []

        for domain_url in self.domains:
            host = _domain_host(domain_url)
            try:
                charts = await self.fetch_from_single_domain(domain_url)
                if not charts:
                    per_domain.append({"domain": host, "recipes": 0, "ingredients": 0})
                    continue

                # Resolve product IDs
                assembled_uuids = {c["assembledProductId"] for c in charts}
                product_map = self._build_product_map(host, assembled_uuids)
                unresolved = len(assembled_uuids) - len(product_map)
                if unresolved > 0:
                    logger.warning(f"{host}: {unresolved} assembledProductId(s) not found in product table")

                rc, ic = self._upsert_recipes(charts, host, product_map)
                self.db.commit()

                per_domain.append({"domain": host, "recipes": rc, "ingredients": ic})
                total_recipes += rc
                total_ingredients += ic

            except Exception as e:
                self.db.rollback()
                msg = f"Recipe sync failed for {host}: {e}"
                logger.error(msg, exc_info=True)
                errors.append(msg)

        status = "success" if not errors else ("partial" if per_domain else "error")
        result = {
            "status": status,
            "total_recipes": total_recipes,
            "total_ingredients": total_ingredients,
            "per_domain": per_domain,
            "errors": errors,
        }
        logger.info(
            f"Recipe sync complete: {total_recipes} recipes, "
            f"{total_ingredients} ingredients across {len(per_domain)} domains"
        )
        return result
