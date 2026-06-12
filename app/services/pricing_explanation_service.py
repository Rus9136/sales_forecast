"""C4': LLM-обоснования отдельных ценовых рекомендаций.

Для каждой рекомендации собирает контекст прямым SQL (экономика рекомендации,
эластичность с CI, роль в меню, продажи за 4 недели, дата последнего изменения
цены), зовёт Claude-движок существующей AI-подсистемы и сохраняет структурированный
JSON в price_recommendation.llm_explanation. Числа подаются модели готовым
JSON-блоком — модель их не пересчитывает (ТЗ п.4.8).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

AGENT_NAME = "PricingRecommendationAgent"
SYSTEM_PROMPT = (
    "Ты — аналитик ценообразования сети ресторанов. Отвечай на русском, "
    "строго по приложенным данным, только валидным JSON."
)
MAX_CONCURRENCY = 4

EXPLANATION_KEYS = {"summary", "factors", "expected_effect", "risks", "recommended_action"}


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def parse_explanation(raw: str) -> Optional[dict]:
    """Извлечь JSON-объект из ответа модели. None — если валидного JSON нет.

    Модель просят отвечать чистым JSON, но защищаемся от markdown-обёрток
    и преамбулы: берём подстроку от первой '{' до последней '}'.
    """
    if not raw:
        return None
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(cleaned[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict) or "summary" not in obj:
        return None
    # Лишние ключи не страшны, но схему сужаем до известных полей
    return {k: obj[k] for k in EXPLANATION_KEYS if k in obj}


class PricingExplanationService:
    def __init__(self, db: Session):
        self.db = db

    # ── Context collection ─────────────────────────────────────────
    def collect_context(self, rec_id: int) -> Optional[dict[str, Any]]:
        r = self.db.execute(
            text("""
                SELECT pr.id, pr.product_id, pr.department_id::text AS department_id,
                       pr.current_price, pr.recommended_price, pr.delta_pct,
                       pr.cogs, pr.current_qty_forecast, pr.new_qty_forecast,
                       pr.current_gp, pr.expected_gp, pr.delta_gp,
                       pr.elasticity_used, pr.elasticity_grade, pr.menu_role,
                       pr.constraints_applied, pr.rec_type, pr.status,
                       p.name AS product_name, d.name AS department_name,
                       se.elasticity_mean, se.elasticity_ci_lower, se.elasticity_ci_upper,
                       se.estimation_level, se.n_price_events,
                       (SELECT MAX(scp.date_from)
                        FROM sku_catalog_price scp
                        WHERE scp.product_id = pr.product_id
                          AND scp.department_id = pr.department_id
                          AND scp.date_from <= CURRENT_DATE) AS last_price_change
                FROM price_recommendation pr
                JOIN product p ON p.id = pr.product_id
                JOIN departments d ON d.id = pr.department_id
                LEFT JOIN sku_elasticity se
                    ON se.product_id = pr.product_id
                   AND se.department_id = pr.department_id
                WHERE pr.id = :id
            """),
            {"id": rec_id},
        ).mappings().first()
        if not r:
            return None

        sales = self.db.execute(
            text("""
                SELECT COALESCE(SUM(total_qty), 0) AS qty,
                       COALESCE(SUM(total_revenue), 0) AS revenue,
                       COALESCE(SUM(days_with_sales), 0) AS days_with_sales
                FROM sku_weekly_summary
                WHERE product_id = :pid
                  AND department_id = CAST(:dept AS uuid)
                  AND week_start >= CURRENT_DATE - 28
            """),
            {"pid": r["product_id"], "dept": r["department_id"]},
        ).mappings().first()

        price = _f(r["current_price"]) or 0.0
        new_price = _f(r["recommended_price"]) or 0.0
        cogs = _f(r["cogs"])
        cur_qty = _f(r["current_qty_forecast"])
        new_qty = _f(r["new_qty_forecast"])
        return {
            "product": {"name": r["product_name"], "id": r["product_id"]},
            "department": r["department_name"],
            "rec_type": r["rec_type"],
            "price": {
                "current": price,
                "recommended": new_price,
                "delta_pct": _f(r["delta_pct"]),
                "last_change_date": str(r["last_price_change"]) if r["last_price_change"] else None,
            },
            "economics": {
                "cogs": cogs,
                "margin_current_pct": round((price - cogs) / price * 100, 1) if cogs is not None and price else None,
                "margin_new_pct": round((new_price - cogs) / new_price * 100, 1) if cogs is not None and new_price else None,
            },
            "weekly_forecast": {
                "qty_current": cur_qty,
                "qty_new": new_qty,
                "delta_qty_pct": round((new_qty - cur_qty) / cur_qty * 100, 1) if cur_qty and new_qty is not None else None,
                "gp_current": _f(r["current_gp"]),
                "gp_expected": _f(r["expected_gp"]),
                "delta_gp": _f(r["delta_gp"]),
            },
            "elasticity": {
                "used_for_planning": _f(r["elasticity_used"]),
                "grade": r["elasticity_grade"],
                "mean": _f(r["elasticity_mean"]),
                "ci_lower": _f(r["elasticity_ci_lower"]),
                "ci_upper": _f(r["elasticity_ci_upper"]),
                "estimation_level": r["estimation_level"],
                "n_price_events": r["n_price_events"],
            },
            "menu_role": r["menu_role"],
            "constraints_applied": list(r["constraints_applied"]) if r["constraints_applied"] else [],
            "sales_last_4_weeks": {
                "qty": _f(sales["qty"]),
                "revenue": _f(sales["revenue"]),
                "days_with_sales": sales["days_with_sales"],
            },
        }

    # ── LLM call ───────────────────────────────────────────────────
    async def explain_one(self, rec_id: int) -> dict:
        """Сгенерировать и сохранить обоснование одной рекомендации."""
        from .ai.engines.dispatcher import get_dispatcher
        from .ai.prompts import get_prompt

        context = self.collect_context(rec_id)
        if context is None:
            return {"status": "not_found", "recommendation_id": rec_id}

        engine = get_dispatcher().get_engine("claude")
        if engine is None or not engine.is_configured():
            return {"status": "no_llm", "recommendation_id": rec_id}

        template = get_prompt(self.db, AGENT_NAME)
        user_prompt = (
            template
            + "\n\nДАННЫЕ (JSON):\n"
            + json.dumps(context, ensure_ascii=False, default=str)
        )
        # db передаём ради аудита в ai_prompt_logs (analysis_id остаётся NULL)
        result = await engine.analyze_with_agent(
            agent_name=AGENT_NAME,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            db=self.db,
            max_tokens=1000,
            temperature=0.3,
        )
        if not result.success:
            logger.error("Explanation failed for rec %s: %s", rec_id, result.error)
            return {"status": "error", "recommendation_id": rec_id, "error": result.error}

        parsed = parse_explanation(result.content or "")
        # Невалидный JSON — сохраняем сырой текст: хуже структуры, лучше пустоты
        stored = (
            json.dumps(parsed, ensure_ascii=False)
            if parsed is not None
            else (result.content or "").strip()
        )
        self.db.execute(
            text("UPDATE price_recommendation SET llm_explanation = :exp WHERE id = :id"),
            {"exp": stored, "id": rec_id},
        )
        self.db.commit()
        return {
            "status": "ok",
            "recommendation_id": rec_id,
            "structured": parsed is not None,
            "tokens_used": result.tokens_used,
            "explanation": stored,
        }

    async def explain_batch(
        self,
        department_id: Optional[str] = None,
        top_n_per_department: int = 10,
        statuses: tuple[str, ...] = ("new",),
    ) -> dict:
        """Объяснить топ-N рекомендаций на подразделение по ΔGP без обоснования.

        Дневной батч оптимизатора замещает открытые рекомендации, поэтому
        обоснования генерируются заново после каждой генерации (05:00).
        """
        dept_clause = " AND department_id = CAST(:dept AS uuid)" if department_id else ""
        rows = self.db.execute(
            text(f"""
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY department_id
                               ORDER BY delta_gp DESC NULLS LAST
                           ) AS rn
                    FROM price_recommendation
                    WHERE status = ANY(:statuses)
                      AND llm_explanation IS NULL
                      {dept_clause}
                ) ranked
                WHERE rn <= :top_n
            """),
            {"statuses": list(statuses), "dept": department_id, "top_n": top_n_per_department},
        ).fetchall()
        rec_ids = [r[0] for r in rows]
        if not rec_ids:
            return {"status": "ok", "explained": 0, "errors": 0, "total": 0}

        sem = asyncio.Semaphore(MAX_CONCURRENCY)

        async def _one(rid: int) -> dict:
            # Своя сессия на задачу: SQLAlchemy Session не рассчитана на
            # переплетение коммитов из параллельных корутин.
            from ..db import SessionLocal

            async with sem:
                task_db = SessionLocal()
                try:
                    return await PricingExplanationService(task_db).explain_one(rid)
                except Exception as e:  # noqa: BLE001 — один сбой не валит батч
                    logger.error("Explanation crashed for rec %s: %s", rid, e, exc_info=True)
                    return {"status": "error", "recommendation_id": rid, "error": str(e)}
                finally:
                    task_db.close()

        results = await asyncio.gather(*[_one(rid) for rid in rec_ids])
        ok = sum(1 for r in results if r["status"] == "ok")
        errors = [r for r in results if r["status"] not in ("ok",)]
        if errors:
            logger.warning("Explanation batch: %d of %d failed", len(errors), len(rec_ids))
        return {
            "status": "ok" if not errors else "partial",
            "total": len(rec_ids),
            "explained": ok,
            "errors": len(errors),
            "error_details": [
                {"recommendation_id": e["recommendation_id"], "error": e.get("error")}
                for e in errors[:10]
            ],
        }
