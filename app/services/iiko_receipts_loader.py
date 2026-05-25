"""Loader for iiko receipts (checks) with line items.

Fetches OLAP SALES report with per-dish granularity, aggregates into
receipt headers + items, resolves DishId → product.id, and batch-upserts
into partitioned `receipt` / `receipt_item` tables.

Sync strategy per date slice:
  1. Upsert receipt headers → RETURNING id  (build order_num → receipt_id map)
  2. Delete existing items for those receipt_ids + open_date
  3. Batch-insert new items
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from psycopg2.extras import execute_values
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)


def _domain_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or url


class IikoReceiptsLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def fetch_from_single_domain(
        self, base_url: str, from_date: date, to_date: date
    ) -> List[dict]:
        host = _domain_host(base_url)
        try:
            auth = IikoAuthService(base_url)
            token = await auth._refresh_token()

            body = {
                "reportType": "SALES",
                "groupByRowFields": [
                    "Department.Id", "OpenDate.Typed", "OrderNum", "CloseTime",
                    "OrderType", "TableNum", "WaiterName",
                    "DishId", "DishName", "DishCode",
                    "DishGroup", "DishCategory",
                ],
                "aggregateFields": [
                    "DishAmountInt", "DishSumInt", "DishDiscountSumInt",
                    "DishReturnSum", "GuestNum",
                    "ProductCostBase.ProductCost", "ProductCostBase.Percent",
                ],
                "filters": {
                    "OpenDate.Typed": {
                        "filterType": "DateRange",
                        "periodType": "CUSTOM",
                        "from": from_date.strftime("%Y-%m-%d"),
                        "to": to_date.strftime("%Y-%m-%d"),
                        "includeLow": True,
                        "includeHigh": True,
                    },
                    "OrderDeleted": {
                        "filterType": "IncludeValues",
                        "values": ["NOT_DELETED"],
                    },
                    "DeletedWithWriteoff": {
                        "filterType": "IncludeValues",
                        "values": ["NOT_DELETED"],
                    },
                },
            }

            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{base_url}/resto/api/v2/reports/olap",
                    params={"key": token},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                logger.info(f"{host}: fetched {len(data)} receipt line items for {from_date}..{to_date}")
                return data

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching receipts from {host}: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"status={e.response.status_code} body={e.response.text[:300]}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching receipts from {host}: {e}", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Parse OLAP rows into receipt headers + items
    # ------------------------------------------------------------------

    def _parse_olap_rows(
        self, rows: List[dict], domain: str,
    ) -> Tuple[List[dict], List[dict]]:
        """Group OLAP rows by (dept, date, order_num) → receipt headers + item lists."""
        grouped: Dict[Tuple, List[dict]] = defaultdict(list)
        for r in rows:
            key = (r["Department.Id"], r["OpenDate.Typed"], r["OrderNum"])
            grouped[key].append(r)

        receipts: List[dict] = []
        items: List[dict] = []

        for (dept_id, open_date_str, order_num), lines in grouped.items():
            first = lines[0]
            total_sum = sum(self._to_float(ln.get("DishSumInt", 0)) for ln in lines)
            discount = sum(self._to_float(ln.get("DishDiscountSumInt", 0)) for ln in lines)
            return_sum = sum(self._to_float(ln.get("DishReturnSum", 0)) for ln in lines)
            guest_num = max((ln.get("GuestNum") or 0) for ln in lines)

            receipt = {
                "department_id": dept_id,
                "open_date": open_date_str,
                "order_num": order_num,
                "close_time": first.get("CloseTime"),
                "order_type": first.get("OrderType"),
                "table_num": str(first.get("TableNum", "")) if first.get("TableNum") is not None else None,
                "waiter_name": first.get("WaiterName"),
                "guest_num": guest_num if guest_num > 0 else None,
                "total_sum": total_sum,
                "discount_sum": discount,
                "return_sum": return_sum,
                "items_count": len(lines),
                "domain": domain,
            }
            receipts.append(receipt)

            for ln in lines:
                qty = self._to_float(ln.get("DishAmountInt", 0))
                dish_sum = self._to_float(ln.get("DishSumInt", 0))
                ppu = round(dish_sum / qty, 2) if qty else None
                items.append({
                    "receipt_key": (dept_id, open_date_str, order_num),
                    "open_date": open_date_str,
                    "iiko_dish_id": ln.get("DishId"),
                    "dish_name": ln.get("DishName", ""),
                    "dish_code": ln.get("DishCode"),
                    "dish_group": ln.get("DishGroup"),
                    "dish_category": ln.get("DishCategory"),
                    "qty": qty,
                    "price_per_unit": ppu,
                    "dish_sum": dish_sum,
                    "discount_sum": self._to_float(ln.get("DishDiscountSumInt", 0)),
                    "return_sum": self._to_float(ln.get("DishReturnSum", 0)),
                    "cost_price": self._to_float(ln.get("ProductCostBase.ProductCost")) or None,
                    "food_cost_percent": self._to_float(ln.get("ProductCostBase.Percent")) or None,
                    "domain": domain,
                })

        return receipts, items

    @staticmethod
    def _to_float(v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    # ------------------------------------------------------------------
    # Resolve FK: DishId → product.id, WaiterName → employee.id
    # ------------------------------------------------------------------

    def _build_product_map(self, domain: str, dish_ids: set) -> Dict[str, int]:
        """Map iiko_product_id (UUID str) → product.id (BIGINT) for one domain."""
        if not dish_ids:
            return {}
        ids_list = list(dish_ids)
        rows = self.db.execute(
            text("""
                SELECT iiko_product_id::text, id
                FROM product
                WHERE iiko_source_domain = :domain
                  AND iiko_product_id = ANY(:ids ::uuid[])
            """),
            {"domain": domain, "ids": ids_list},
        ).fetchall()
        return {str(r[0]): r[1] for r in rows}

    def _build_employee_map(self, domain: str, names: set) -> Dict[str, str]:
        """Map waiter_name → employee.id (UUID).

        Replicates the logic from iiko_waiter_sales_loader: lookup by name,
        skip if 0 or >1 matches. Employees table has no domain column —
        records are merged by UUID across domains.
        """
        if not names:
            return {}
        rows = self.db.execute(
            text("""
                SELECT name, id
                FROM employees
                WHERE name = ANY(:names)
            """),
            {"names": list(names)},
        ).fetchall()
        name_map: Dict[str, str] = {}
        counts: Dict[str, int] = defaultdict(int)
        first_id: Dict[str, str] = {}
        for name, eid in rows:
            counts[name] += 1
            if counts[name] == 1:
                first_id[name] = str(eid)
        for n, cnt in counts.items():
            if cnt == 1:
                name_map[n] = first_id[n]
        return name_map

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def _upsert_receipts_and_items(
        self,
        receipts: List[dict],
        items: List[dict],
        product_map: Dict[str, int],
        employee_map: Dict[str, str],
    ) -> Tuple[int, int]:
        """Upsert receipts, delete+insert items. Returns (receipt_count, item_count)."""
        if not receipts:
            return 0, 0

        now = datetime.utcnow()
        conn = self.db.connection().connection

        # Group by open_date for partition-aware processing
        by_date: Dict[str, List[dict]] = defaultdict(list)
        for r in receipts:
            by_date[r["open_date"]].append(r)

        items_by_key: Dict[Tuple, List[dict]] = defaultdict(list)
        for it in items:
            items_by_key[it["receipt_key"]].append(it)

        total_receipts = 0
        total_items = 0

        with conn.cursor() as cur:
            for open_date_str, date_receipts in by_date.items():
                # 1. Upsert receipt headers
                receipt_rows = []
                for r in date_receipts:
                    emp_id = employee_map.get(r["waiter_name"]) if r.get("waiter_name") else None
                    receipt_rows.append((
                        r["department_id"],
                        r["open_date"],
                        r["order_num"],
                        r["close_time"],
                        r.get("order_type"),
                        r.get("table_num"),
                        r.get("waiter_name"),
                        emp_id,
                        r.get("guest_num"),
                        r["total_sum"],
                        r["discount_sum"],
                        r["return_sum"],
                        r["items_count"],
                        now,
                    ))

                returned = execute_values(
                    cur,
                    """
                    INSERT INTO receipt (
                        department_id, open_date, order_num, close_time,
                        order_type, table_num, waiter_name, waiter_employee_id,
                        guest_num, total_sum, discount_sum, return_sum,
                        items_count, synced_at
                    ) VALUES %s
                    ON CONFLICT (department_id, open_date, order_num) DO UPDATE SET
                        close_time = EXCLUDED.close_time,
                        order_type = EXCLUDED.order_type,
                        table_num = EXCLUDED.table_num,
                        waiter_name = EXCLUDED.waiter_name,
                        waiter_employee_id = EXCLUDED.waiter_employee_id,
                        guest_num = EXCLUDED.guest_num,
                        total_sum = EXCLUDED.total_sum,
                        discount_sum = EXCLUDED.discount_sum,
                        return_sum = EXCLUDED.return_sum,
                        items_count = EXCLUDED.items_count,
                        synced_at = EXCLUDED.synced_at
                    RETURNING id, department_id, order_num
                    """,
                    receipt_rows,
                    template="(%s::uuid, %s::date, %s, %s::timestamp, %s, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s)",
                    fetch=True,
                )
                # Build (dept_id, date, order_num) → receipt_id map
                key_to_id: Dict[Tuple, int] = {}
                for (rid, dept_id, onum) in returned:
                    key_to_id[(str(dept_id), open_date_str, onum)] = rid
                total_receipts += len(returned)

                # 2. Delete existing items for these receipt_ids
                receipt_ids = list(key_to_id.values())
                if receipt_ids:
                    cur.execute(
                        "DELETE FROM receipt_item WHERE receipt_id = ANY(%s) AND open_date = %s::date",
                        (receipt_ids, open_date_str),
                    )

                # 3. Insert items
                item_rows = []
                for r in date_receipts:
                    rkey = (r["department_id"], r["open_date"], r["order_num"])
                    receipt_id = key_to_id.get(rkey)
                    if not receipt_id:
                        continue
                    for it in items_by_key.get(rkey, []):
                        product_id = product_map.get(it["iiko_dish_id"]) if it.get("iiko_dish_id") else None
                        item_rows.append((
                            receipt_id,
                            it["open_date"],
                            product_id,
                            it.get("iiko_dish_id"),
                            it["dish_name"],
                            it.get("dish_code"),
                            it.get("dish_group"),
                            it.get("dish_category"),
                            it["qty"],
                            it.get("price_per_unit"),
                            it["dish_sum"],
                            it["discount_sum"],
                            it["return_sum"],
                            it.get("cost_price"),
                            it.get("food_cost_percent"),
                        ))

                if item_rows:
                    execute_values(
                        cur,
                        """
                        INSERT INTO receipt_item (
                            receipt_id, open_date, product_id, iiko_dish_id,
                            dish_name, dish_code, dish_group, dish_category,
                            qty, price_per_unit, dish_sum, discount_sum, return_sum,
                            cost_price, food_cost_percent
                        ) VALUES %s
                        """,
                        item_rows,
                        template="(%s, %s::date, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    )
                    total_items += len(item_rows)

        return total_receipts, total_items

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def sync(
        self,
        from_date: date,
        to_date: date,
        department_id: Optional[str] = None,
    ) -> dict:
        total_receipts = 0
        total_items = 0
        per_domain: List[dict] = []
        errors: List[str] = []

        # Build dept → domain map for filtering
        dept_domain_map: Dict[str, str] = {}
        rows = self.db.execute(
            text("SELECT id::text, iiko_source_domain FROM departments")
        ).fetchall()
        for did, dom in rows:
            dept_domain_map[did] = dom

        for domain_url in self.domains:
            host = _domain_host(domain_url)
            try:
                raw = await self.fetch_from_single_domain(domain_url, from_date, to_date)
                if not raw:
                    per_domain.append({"domain": host, "receipts": 0, "items": 0})
                    continue

                # Filter by department if specified
                if department_id:
                    raw = [r for r in raw if r.get("Department.Id") == department_id]
                    if not raw:
                        per_domain.append({"domain": host, "receipts": 0, "items": 0})
                        continue

                receipts, items = self._parse_olap_rows(raw, host)

                # Resolve FKs
                dish_ids = {it["iiko_dish_id"] for it in items if it.get("iiko_dish_id")}
                product_map = self._build_product_map(host, dish_ids)

                waiter_names = {r["waiter_name"] for r in receipts if r.get("waiter_name")}
                employee_map = self._build_employee_map(host, waiter_names)

                unresolved = len(dish_ids) - len(product_map)
                if unresolved > 0:
                    logger.warning(f"{host}: {unresolved} DishId(s) not found in product table")

                rc, ic = self._upsert_receipts_and_items(receipts, items, product_map, employee_map)
                self.db.commit()

                per_domain.append({"domain": host, "receipts": rc, "items": ic})
                total_receipts += rc
                total_items += ic

            except Exception as e:
                self.db.rollback()
                msg = f"Receipts sync failed for {host}: {e}"
                logger.error(msg, exc_info=True)
                errors.append(msg)

        status = "success" if not errors else ("partial" if per_domain else "error")
        result = {
            "status": status,
            "total_receipts": total_receipts,
            "total_items": total_items,
            "per_domain": per_domain,
            "errors": errors,
        }
        logger.info(
            f"Receipts sync complete: {total_receipts} receipts, {total_items} items "
            f"across {len(per_domain)} domains"
        )
        return result
