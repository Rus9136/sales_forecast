"""Pricing engine API — elasticity (B2), optimizer (B3), rules (B4)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import get_api_key_or_bypass
from ..auth_ui import get_optional_user, user_has_section
from ..db import get_db
from ..models.auth_ui import AppUser

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pricing-engine",
    tags=["pricing-engine"],
    dependencies=[Depends(get_api_key_or_bypass)],
)

# Коды ошибок статусной машины, транслируемые в HTTP 409 (конфликт состояния)
_CONFLICT_CODES = {"cycle_cap_exceeded", "expired", "stale_price", "min_frequency",
                   "stop_list", "label_exists"}


def _require_section(user: Optional[AppUser], *sections: str) -> None:
    """Проверка секции роли для мутаций. user=None (чистый API-token клиент:
    curl/автоматизация) — допускается, актор аудита будет 'api'."""
    if user is None:
        return
    if not user_has_section(user, *sections):
        from fastapi import status as _st
        raise HTTPException(
            _st.HTTP_403_FORBIDDEN,
            f"Роль '{user.role_code}' не имеет доступа к разделу: {' / '.join(sections)}",
        )


def _actor_of(user: Optional[AppUser]) -> Optional[str]:
    if user is None:
        return None
    label = user.full_name or user.phone
    return f"{label} ({user.phone})" if user.full_name else label


def _parse_ids(raw: Optional[str]) -> Optional[list[int]]:
    if not raw:
        return None
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()] or None
    except ValueError:
        raise HTTPException(400, "rec_ids must be comma-separated integers")


# ==================== B4: Rules ====================

@router.get("/rules")
async def list_rules(
    rule_type: Optional[str] = None,
    scope_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    from ..services.pricing_rules_service import PricingRulesService
    svc = PricingRulesService(db)
    items = svc.list_rules(rule_type, scope_type, is_active)
    return {"items": items, "total": len(items)}


@router.get("/rules/constraint-stats")
async def rule_constraint_stats(
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Сколько открытых (new) рекомендаций сейчас сдерживает каждое правило.

    Считается по price_recommendation.constraints_applied (text[]) — код правила
    попадает туда, когда ограничение реально урезало кандидата в grid search.
    """
    dept_filter = ""
    params: dict = {}
    if department_id:
        dept_filter = "AND pr.department_id = CAST(:dept_id AS uuid)"
        params["dept_id"] = department_id

    rows = db.execute(
        text(f"""
            SELECT c AS code, COUNT(*) AS n
            FROM price_recommendation pr, unnest(pr.constraints_applied) AS c
            WHERE pr.status = 'new' {dept_filter}
            GROUP BY c
        """),
        params,
    ).fetchall()
    total_new = db.execute(
        text(f"SELECT COUNT(*) FROM price_recommendation pr WHERE pr.status = 'new' {dept_filter}"),
        params,
    ).scalar()
    return {"by_constraint": {r.code: r.n for r in rows}, "total_new": total_new}


@router.post("/rules")
async def create_rule(
    rule_type: str = Query(...),
    scope_type: str = Query("global"),
    scope_id: Optional[str] = None,
    params: str = Query(..., description="JSON string"),
    configured_by_role: Optional[str] = None,
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    import json
    from ..services.pricing_rules_service import PricingRulesService
    _require_section(user, "pricing.rules")
    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON in params")

    svc = PricingRulesService(db)
    try:
        return svc.create_rule({
            "rule_type": rule_type,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "params": params_dict,
            "configured_by_role": (user.role_code if user else configured_by_role),
        }, actor=_actor_of(user))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    params: Optional[str] = None,
    is_active: Optional[bool] = None,
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    import json
    from ..services.pricing_rules_service import PricingRulesService
    _require_section(user, "pricing.rules")
    data = {}
    if params:
        try:
            data["params"] = json.loads(params)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON in params")
    if is_active is not None:
        data["is_active"] = is_active

    svc = PricingRulesService(db)
    result = svc.update_rule(rule_id, data, actor=_actor_of(user))
    if result.get("status") == "error":
        raise HTTPException(404, result.get("message", "Rule not found"))
    return result


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    from ..services.pricing_rules_service import PricingRulesService
    _require_section(user, "pricing.rules")
    svc = PricingRulesService(db)
    result = svc.delete_rule(rule_id, actor=_actor_of(user))
    if result.get("status") == "error":
        raise HTTPException(404, result.get("message", "Rule not found"))
    return result


@router.get("/rules/effective/{product_id}/{department_id}")
async def get_effective_rules(
    product_id: int,
    department_id: str,
    segment_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from ..services.pricing_rules_service import PricingRulesService
    svc = PricingRulesService(db)
    rules = svc.get_effective_rules(product_id, department_id, segment_type)
    return {"rules": rules}


# ==================== B2: Elasticity ====================

@router.get("/elasticity")
async def list_elasticity(
    department_id: Optional[str] = None,
    product_id: Optional[int] = None,
    reliability_grade: Optional[str] = None,
    estimation_level: Optional[str] = None,
    limit: int = Query(200, le=2000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    conditions = ["1=1"]
    params: dict = {}
    if department_id:
        conditions.append("se.department_id = CAST(:dept_id AS uuid)")
        params["dept_id"] = department_id
    if product_id:
        conditions.append("se.product_id = :product_id")
        params["product_id"] = product_id
    if reliability_grade:
        conditions.append("se.reliability_grade = :grade")
        params["grade"] = reliability_grade
    if estimation_level:
        conditions.append("se.estimation_level = :level")
        params["level"] = estimation_level

    where = " AND ".join(conditions)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM sku_elasticity se WHERE {where}"), params
    ).scalar()

    rows = db.execute(
        text(f"""
            SELECT se.*, p.name AS product_name
            FROM sku_elasticity se
            JOIN product p ON p.id = se.product_id
            WHERE {where}
            ORDER BY ABS(se.elasticity_mean) DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    items = [
        {
            "product_id": r.product_id,
            "department_id": str(r.department_id),
            "product_name": r.product_name,
            "elasticity_mean": float(r.elasticity_mean),
            "elasticity_ci_lower": float(r.elasticity_ci_lower),
            "elasticity_ci_upper": float(r.elasticity_ci_upper),
            "elasticity_se": float(r.elasticity_se) if r.elasticity_se is not None else None,
            "n_price_events": r.n_price_events,
            "n_observations": r.n_observations,
            "estimation_level": r.estimation_level,
            "reliability_grade": r.reliability_grade,
            "group_key": r.group_key,
            "model_r_squared": float(r.model_r_squared) if r.model_r_squared is not None else None,
            "model_version": r.model_version,
            "updated_at": str(r.updated_at),
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@router.get("/elasticity/summary")
async def elasticity_summary(db: Session = Depends(get_db)):
    by_grade = {}
    rows = db.execute(text(
        "SELECT reliability_grade, COUNT(*) FROM sku_elasticity GROUP BY 1 ORDER BY 1"
    )).fetchall()
    for r in rows:
        by_grade[r[0]] = r[1]

    by_level = {}
    rows = db.execute(text(
        "SELECT estimation_level, COUNT(*) FROM sku_elasticity GROUP BY 1 ORDER BY 1"
    )).fetchall()
    for r in rows:
        by_level[r[0]] = r[1]

    total = sum(by_grade.values())

    global_prior = db.execute(text(
        "SELECT elasticity_mean FROM sku_elasticity WHERE estimation_level = 'global' LIMIT 1"
    )).scalar()

    return {
        "by_grade": by_grade,
        "by_level": by_level,
        "total": total,
        "global_prior": float(global_prior) if global_prior is not None else None,
    }


@router.post("/elasticity/estimate")
def trigger_elasticity_estimation(
    lookback_days: int = Query(730, ge=90, le=730),
    background: bool = Query(False, description="true → 202 + job_id, статус через GET /jobs/{id}"),
    db: Session = Depends(get_db),
):
    """Sync def: FastAPI runs it in the threadpool — иначе многоминутный
    OLS-прогон блокирует event loop единственного воркера.
    С background=true возвращается сразу job_id (не держит HTTP-соединение)."""
    if background:
        from ..db import SessionLocal
        from ..services.pricing_jobs import job_registry

        def _run():
            job_db = SessionLocal()
            try:
                from ..services.elasticity_estimation_service import ElasticityEstimationService
                return ElasticityEstimationService(job_db).estimate_all(lookback_days=lookback_days)
            finally:
                job_db.close()

        job_id = job_registry.submit("elasticity_estimate", _run)
        return {"status": "running", "job_id": job_id}

    from ..services.elasticity_estimation_service import ElasticityEstimationService
    svc = ElasticityEstimationService(db)
    return svc.estimate_all(lookback_days=lookback_days)


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Статус фонового джоба, запущенного с ?background=true."""
    from ..services.pricing_jobs import job_registry
    job = job_registry.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found (реестр процесс-локальный и очищается при рестарте)")
    return job


@router.get("/elasticity/{product_id}/{department_id}")
async def get_sku_elasticity(
    product_id: int,
    department_id: str,
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("""
            SELECT se.*, p.name AS product_name
            FROM sku_elasticity se
            JOIN product p ON p.id = se.product_id
            WHERE se.product_id = :pid AND se.department_id = CAST(:did AS uuid)
        """),
        {"pid": product_id, "did": department_id},
    ).fetchone()

    if not row:
        raise HTTPException(404, "Elasticity not found for this SKU")

    return {
        "product_id": row.product_id,
        "department_id": str(row.department_id),
        "product_name": row.product_name,
        "elasticity_mean": float(row.elasticity_mean),
        "elasticity_ci_lower": float(row.elasticity_ci_lower),
        "elasticity_ci_upper": float(row.elasticity_ci_upper),
        "n_price_events": row.n_price_events,
        "estimation_level": row.estimation_level,
        "reliability_grade": row.reliability_grade,
        "group_key": row.group_key,
        "diagnostics": row.diagnostics,
    }


# ==================== B3: Recommendations ====================

@router.post("/recommendations/generate")
def generate_recommendations(
    department_id: str = Query(...),
    min_gp_threshold: float = Query(500.0, ge=0),
    db: Session = Depends(get_db),
):
    """Sync def → threadpool: не блокирует event loop при долгом прогоне."""
    from ..services.price_optimizer_service import PriceOptimizerService
    svc = PriceOptimizerService(db)
    return svc.generate_recommendations(department_id, min_gp_threshold)


#: Белый список серверных сортировок инбокса рекомендаций (UI: sort=)
_REC_SORT_SQL = {
    "delta_gp": "pr.delta_gp DESC NULLS LAST",
    "delta_pct": "ABS(pr.delta_pct) DESC NULLS LAST",
    "grade": ("CASE pr.elasticity_grade WHEN 'A' THEN 4 WHEN 'B' THEN 3 "
              "WHEN 'C' THEN 2 WHEN 'D' THEN 1 ELSE 0 END DESC, "
              "pr.delta_gp DESC NULLS LAST"),
}


@router.get("/recommendations")
async def list_recommendations(
    department_id: Optional[str] = None,
    status: Optional[str] = None,
    batch_id: Optional[str] = None,
    rec_type: Optional[str] = Query(None, description="optimizer | experiment"),
    search: Optional[str] = Query(None, description="ILIKE-поиск по названию блюда"),
    menu_role: Optional[str] = None,
    elasticity_grade: Optional[str] = Query(None, description="A | B | C | D"),
    sort: Optional[str] = Query(None, description="delta_gp | delta_pct | grade"),
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    conditions = ["1=1"]
    params: dict = {}
    if department_id:
        conditions.append("pr.department_id = CAST(:dept_id AS uuid)")
        params["dept_id"] = department_id
    if status:
        conditions.append("pr.status = :status")
        params["status"] = status
    if batch_id:
        conditions.append("pr.batch_id = CAST(:batch_id AS uuid)")
        params["batch_id"] = batch_id
    if rec_type:
        conditions.append("pr.rec_type = :rec_type")
        params["rec_type"] = rec_type
    if search and search.strip():
        conditions.append("p.name ILIKE :search")
        params["search"] = f"%{search.strip()}%"
    if menu_role:
        conditions.append("pr.menu_role = :menu_role")
        params["menu_role"] = menu_role
    if elasticity_grade:
        conditions.append("pr.elasticity_grade = :egrade")
        params["egrade"] = elasticity_grade

    where = " AND ".join(conditions)
    order_by = _REC_SORT_SQL.get(sort or "delta_gp", _REC_SORT_SQL["delta_gp"])

    total = db.execute(
        text(f"""
            SELECT COUNT(*)
            FROM price_recommendation pr
            JOIN product p ON p.id = pr.product_id
            WHERE {where}
        """),
        params,
    ).scalar()

    rows = db.execute(
        text(f"""
            SELECT pr.*, p.name AS product_name, d.name AS department_name
            FROM price_recommendation pr
            JOIN product p ON p.id = pr.product_id
            JOIN departments d ON d.id = pr.department_id
            WHERE {where}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    items = [
        {
            "id": r.id,
            "product_id": r.product_id,
            "product_name": r.product_name,
            "department_id": str(r.department_id),
            "department_name": r.department_name,
            "batch_id": str(r.batch_id),
            "current_price": float(r.current_price),
            "recommended_price": float(r.recommended_price),
            "delta_pct": float(r.delta_pct) if r.delta_pct is not None else None,
            "cogs": float(r.cogs) if r.cogs is not None else None,
            "current_qty_forecast": float(r.current_qty_forecast) if r.current_qty_forecast is not None else None,
            "new_qty_forecast": float(r.new_qty_forecast) if r.new_qty_forecast is not None else None,
            "current_gp": float(r.current_gp) if r.current_gp is not None else None,
            "expected_gp": float(r.expected_gp) if r.expected_gp is not None else None,
            "delta_gp": float(r.delta_gp) if r.delta_gp is not None else None,
            "elasticity_used": float(r.elasticity_used) if r.elasticity_used is not None else None,
            "elasticity_grade": r.elasticity_grade,
            "menu_role": r.menu_role,
            "constraints_applied": r.constraints_applied,
            "llm_explanation": r.llm_explanation,
            "status": r.status,
            "rec_type": r.rec_type,
            "reverses_recommendation_id": r.reverses_recommendation_id,
            "created_at": str(r.created_at),
            "reviewed_at": str(r.reviewed_at) if r.reviewed_at else None,
            "review_comment": r.review_comment,
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@router.post("/recommendations/{rec_id}/explain")
def explain_recommendation(rec_id: int, db: Session = Depends(get_db)):
    """C4': сгенерировать LLM-обоснование одной рекомендации (on-demand из UI).

    Sync def → threadpool: вызов Claude занимает 5–15с и не должен блокировать
    event loop; asyncio.run в воркер-треде — тот же паттерн, что в scheduler.
    """
    import asyncio

    from ..services.pricing_explanation_service import PricingExplanationService
    result = asyncio.run(PricingExplanationService(db).explain_one(rec_id))
    if result["status"] == "not_found":
        raise HTTPException(404, f"Recommendation {rec_id} not found")
    if result["status"] == "no_llm":
        raise HTTPException(503, "LLM provider is not configured (see AI_DEFAULT_PROVIDER and its API key)")
    if result["status"] == "error":
        raise HTTPException(502, f"LLM call failed: {result.get('error')}")
    return result


@router.post("/recommendations/explain-batch")
def explain_recommendations_batch(
    department_id: Optional[str] = None,
    top_n_per_department: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """C4': обоснования для топ-N новых рекомендаций по ΔGP (на подразделение)."""
    import asyncio

    from ..services.pricing_explanation_service import PricingExplanationService
    svc = PricingExplanationService(db)
    return asyncio.run(svc.explain_batch(department_id, top_n_per_department))


@router.get("/recommendations/export")
async def export_recommendations(
    department_id: Optional[str] = None,
    status: str = Query("approved", description="Filter by status (default approved)"),
    db: Session = Depends(get_db),
):
    """Export recommendations to XLSX for manual upload into iiko."""
    import io
    from datetime import date as _date

    from openpyxl import Workbook
    from openpyxl.styles import Font

    conditions = ["pr.status = :status"]
    params: dict = {"status": status}
    if department_id:
        conditions.append("pr.department_id = CAST(:dept_id AS uuid)")
        params["dept_id"] = department_id
    where = " AND ".join(conditions)

    rows = db.execute(
        text(f"""
            SELECT pr.*, p.name AS product_name, p.code AS product_code,
                   d.name AS department_name
            FROM price_recommendation pr
            JOIN product p ON p.id = pr.product_id
            JOIN departments d ON d.id = pr.department_id
            WHERE {where}
            ORDER BY d.name, pr.delta_gp DESC NULLS LAST
        """),
        params,
    ).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Рекомендации"

    headers = [
        "Подразделение", "Код", "Позиция", "Роль",
        "Текущая цена", "Рекомендуемая цена", "Δ %",
        "COGS", "Текущая GP", "Ожидаемая GP", "Δ GP",
        "Эластичность", "Надёжность", "Статус",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for r in rows:
        ws.append([
            r.department_name,
            r.product_code,
            r.product_name,
            r.menu_role,
            float(r.current_price) if r.current_price is not None else None,
            float(r.recommended_price) if r.recommended_price is not None else None,
            float(r.delta_pct) if r.delta_pct is not None else None,
            float(r.cogs) if r.cogs is not None else None,
            float(r.current_gp) if r.current_gp is not None else None,
            float(r.expected_gp) if r.expected_gp is not None else None,
            float(r.delta_gp) if r.delta_gp is not None else None,
            float(r.elasticity_used) if r.elasticity_used is not None else None,
            r.elasticity_grade,
            r.status,
        ])

    widths = [26, 12, 36, 16, 14, 16, 8, 12, 14, 14, 14, 13, 11, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"price_recommendations_{status}_{_date.today().isoformat()}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/recommendations/{rec_id}/review")
async def review_recommendation(
    rec_id: int,
    status: str = Query(..., description="approved or rejected"),
    comment: Optional[str] = None,
    reviewer_id: Optional[str] = None,
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be 'approved' or 'rejected'")
    _require_section(user, "pricing.recommendations")
    # при наличии сессии reviewer_id берётся из неё — клиентский параметр
    # подделываем и игнорируется
    if user is not None:
        reviewer_id = str(user.id)
    from ..services.price_optimizer_service import PriceOptimizerService
    svc = PriceOptimizerService(db)
    result = svc.review_recommendation(rec_id, status, reviewer_id, comment,
                                       actor=_actor_of(user))
    if result.get("status") == "error":
        if result.get("code") in _CONFLICT_CODES:
            raise HTTPException(409, result.get("message"))
        raise HTTPException(404, result.get("message", "Recommendation not found"))
    return result


@router.post("/recommendations/batch-review")
async def batch_review_recommendations(
    rec_ids: str = Query(..., description="Comma-separated IDs"),
    status: str = Query(..., description="approved or rejected"),
    reviewer_id: Optional[str] = None,
    comment: Optional[str] = None,
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be 'approved' or 'rejected'")
    _require_section(user, "pricing.recommendations")
    if user is not None:
        reviewer_id = str(user.id)
    from ..services.price_optimizer_service import PriceOptimizerService
    try:
        ids = [int(x.strip()) for x in rec_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "rec_ids must be comma-separated integers")
    svc = PriceOptimizerService(db)
    result = svc.batch_review(ids, status, reviewer_id, comment, actor=_actor_of(user))
    if result.get("status") == "error" and result.get("code") in _CONFLICT_CODES:
        raise HTTPException(409, result.get("message"))
    return result


# ==================== №7: Price experiments ====================

@router.post("/experiments/generate")
def generate_experiments(
    department_id: str = Query(...),
    n: int = Query(10, ge=1, le=50),
    delta_pct: float = Query(4.0, ge=2.0, le=5.0),
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Сгенерировать контролируемые ценовые эксперименты для grade C/D SKU.
    Идут обычным циклом approve → applied → outcome; цель — измерение эластичности."""
    from ..services.price_optimizer_service import PriceOptimizerService
    _require_section(user, "pricing.recommendations", "pricing.outcomes")
    svc = PriceOptimizerService(db)
    return svc.generate_experiments(department_id, n, delta_pct, actor=_actor_of(user))


@router.post("/rollbacks/generate")
def generate_rollbacks(
    department_id: Optional[str] = Query(None, description="Точка; пусто — вся сеть"),
    dry_run: bool = Query(False, description="Показать, что будет создано, ничего не записывая"),
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Вернуть прежнюю цену там, где повышение доказанно навредило.

    Кандидаты — применённые решения с отрицательным эффектом, у которых либо
    bootstrap-интервал целиком ниже нуля, либо заведено правило stop_list
    (доказательство на уровне категории; решение принимает человек).
    Цель отката — цена ДО решения. Идёт обычным циклом approve → applied →
    outcome, поэтому даёт второй замер в обратную сторону.
    """
    from ..services.price_optimizer_service import PriceOptimizerService
    _require_section(user, "pricing.recommendations", "pricing.outcomes")
    return PriceOptimizerService(db).generate_rollbacks(
        department_id=department_id, actor=_actor_of(user), dry_run=dry_run)


# ==================== Audit log ====================

@router.get("/audit-log")
async def list_audit_log(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    department_id: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    conditions = ["1=1"]
    params: dict = {}
    if entity_type:
        conditions.append("a.entity_type = :etype")
        params["etype"] = entity_type
    if entity_id:
        conditions.append("a.entity_id = :eid")
        params["eid"] = entity_id
    if action:
        conditions.append("a.action = :action")
        params["action"] = action
    if department_id:
        conditions.append("a.department_id = CAST(:dept_id AS uuid)")
        params["dept_id"] = department_id
    where = " AND ".join(conditions)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM pricing_audit_log a WHERE {where}"), params
    ).scalar()

    rows = db.execute(
        text(f"""
            SELECT a.id, a.entity_type, a.entity_id, a.action, a.actor,
                   a.department_id::text AS department_id, a.details, a.created_at
            FROM pricing_audit_log a
            WHERE {where}
            ORDER BY a.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    # Обогащение ссылками на объекты: рекомендация/роль меню → карточка позиции в UI
    rec_ids: list[int] = []
    role_pids: list[int] = []
    for r in rows:
        if r.entity_type == "recommendation" and r.entity_id and r.entity_id.isdigit():
            rec_ids.append(int(r.entity_id))
        elif r.entity_type == "menu_role" and r.entity_id and "/" in r.entity_id:
            pid = r.entity_id.split("/", 1)[0]
            if pid.isdigit():
                role_pids.append(int(pid))

    rec_map: dict = {}
    if rec_ids:
        for rr in db.execute(
            text("""
                SELECT pr.id, pr.product_id, pr.department_id::text AS department_id,
                       p.name AS product_name
                FROM price_recommendation pr
                JOIN product p ON p.id = pr.product_id
                WHERE pr.id = ANY(:ids)
            """),
            {"ids": rec_ids},
        ).fetchall():
            rec_map[rr.id] = rr

    product_names: dict = {}
    if role_pids:
        for pr_row in db.execute(
            text("SELECT id, name FROM product WHERE id = ANY(:ids)"),
            {"ids": role_pids},
        ).fetchall():
            product_names[pr_row.id] = pr_row.name

    def _object_of(r) -> dict:
        if r.entity_type == "recommendation" and r.entity_id and r.entity_id.isdigit():
            rr = rec_map.get(int(r.entity_id))
            if rr is not None:
                return {
                    "object_label": rr.product_name,
                    "object_product_id": rr.product_id,
                    "object_department_id": rr.department_id,
                }
        if r.entity_type == "menu_role" and r.entity_id and "/" in r.entity_id:
            pid, dept = r.entity_id.split("/", 1)
            if pid.isdigit():
                return {
                    "object_label": product_names.get(int(pid), f"Блюдо #{pid}"),
                    "object_product_id": int(pid),
                    "object_department_id": dept,
                }
        return {}

    items = [
        {
            "id": r.id,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "action": r.action,
            "actor": r.actor,
            "department_id": r.department_id,
            "details": r.details,
            "created_at": str(r.created_at),
            **_object_of(r),
        }
        for r in rows
    ]
    return {"items": items, "total": total}


# ==================== Приказы: выгрузка утверждённых цен в iiko ====================

def _price_order_service(db: Session):
    from ..services.price_order_service import PriceOrderService
    return PriceOrderService(db)


def _order_error(e) -> HTTPException:
    return HTTPException(e.http_status, {"code": e.code, "message": e.message})


def _parse_effective_date(value: Optional[str]) -> date:
    """По умолчанию — завтра: цена меняется на границе учётного дня, окна
    замера не разрезают день пополам."""
    from datetime import timedelta as _td
    if not value:
        return date.today() + _td(days=1)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "effective_date должен быть в формате YYYY-MM-DD")


@router.get("/price-orders")
async def list_price_orders(
    department_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    """Журнал приказов об изменении цен."""
    return {"items": _price_order_service(db).list_orders(department_id, status, limit)}


@router.get("/price-orders/{order_id}")
async def get_price_order(order_id: int, db: Session = Depends(get_db)):
    from ..services.price_order_service import PriceOrderError
    try:
        return _price_order_service(db).get_order(order_id)
    except PriceOrderError as e:
        raise _order_error(e)


@router.post("/price-orders/preview")
async def preview_price_order(
    department_id: str = Query(...),
    effective_date: Optional[str] = Query(None, description="YYYY-MM-DD, по умолчанию завтра"),
    rec_ids: Optional[str] = Query(None, description="Comma-separated ID рекомендаций"),
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Что уедет в iiko: позиции, исключённые с причинами, суммарный эффект.
    Ничего не пишет и в iiko не ходит."""
    from ..services.price_order_service import PriceOrderError
    _require_section(user, "pricing.apply")
    try:
        return _price_order_service(db).build_preview(
            department_id, _parse_effective_date(effective_date), _parse_ids(rec_ids))
    except PriceOrderError as e:
        raise _order_error(e)


@router.post("/price-orders")
async def create_price_order(
    department_id: str = Query(...),
    effective_date: Optional[str] = Query(None, description="YYYY-MM-DD, по умолчанию завтра"),
    rec_ids: Optional[str] = Query(None, description="Comma-separated ID рекомендаций"),
    dry_run: bool = Query(False, description="Собрать payload, но не отправлять"),
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Собрать и отправить приказ в iiko. Публикация цен в боевую кассу."""
    from ..services.price_order_service import PriceOrderError
    _require_section(user, "pricing.apply")
    try:
        return await _price_order_service(db).send_order(
            department_id,
            _parse_effective_date(effective_date),
            _parse_ids(rec_ids),
            created_by=str(user.id) if user else None,
            actor=_actor_of(user),
            dry_run=dry_run,
        )
    except PriceOrderError as e:
        raise _order_error(e)


@router.post("/price-orders/{order_id}/cancel")
async def cancel_price_order(
    order_id: int,
    reason: Optional[str] = None,
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Отмена: удаление документа в iiko, а если приказ уже действует —
    обратный приказ с прежними ценами."""
    from ..services.price_order_service import PriceOrderError
    _require_section(user, "pricing.apply")
    try:
        return await _price_order_service(db).cancel_order(
            order_id, actor=_actor_of(user), reason=reason)
    except PriceOrderError as e:
        raise _order_error(e)


@router.post("/price-orders/{order_id}/sync")
async def sync_price_order(
    order_id: int,
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Сверить статус приказа с iiko (могли провести или удалить руками)."""
    from ..services.price_order_service import PriceOrderError
    _require_section(user, "pricing.apply")
    try:
        return await _price_order_service(db).sync_order_status(order_id)
    except PriceOrderError as e:
        raise _order_error(e)


# ==================== Feedback loop: applied + outcomes + baseline ====================

@router.post("/recommendations/detect-applied")
def detect_applied_recommendations(
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Mark approved recs as applied when the catalog shows the recommended price.
    Также выполняется автоматически после ежедневного синка цен (03:20)."""
    from ..services.pricing_feedback_service import PricingFeedbackService
    return PricingFeedbackService(db).detect_applied(actor=_actor_of(user) or "api")


@router.post("/outcomes/evaluate")
def evaluate_outcomes_now(
    recompute: bool = Query(False, description="Пересчитать уже оценённые результаты"),
    eval_days: Optional[int] = Query(None, ge=7, le=90, description="Разово переопределить окно замера"),
    baseline_days: Optional[int] = Query(None, ge=7, le=90, description="Разово переопределить базу"),
    db: Session = Depends(get_db),
):
    """Оценить applied-рекомендации с истёкшим окном (планировщик: 05:30).

    Без параметров окна берутся из правила effect_measurement («Правила цен»).
    """
    from ..services.pricing_feedback_service import PricingFeedbackService
    return PricingFeedbackService(db).evaluate_outcomes(
        eval_window_days=eval_days, baseline_days=baseline_days, recompute=recompute)


@router.get("/outcomes")
async def list_outcomes(
    department_id: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    conditions = ["1=1"]
    params: dict = {}
    if department_id:
        conditions.append("o.department_id = CAST(:dept_id AS uuid)")
        params["dept_id"] = department_id
    where = " AND ".join(conditions)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM price_recommendation_outcome o WHERE {where}"), params
    ).scalar()

    rows = db.execute(
        text(f"""
            SELECT o.*, p.name AS product_name, d.name AS department_name
            FROM price_recommendation_outcome o
            JOIN product p ON p.id = o.product_id
            JOIN departments d ON d.id = o.department_id
            WHERE {where}
            ORDER BY o.applied_at DESC, o.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()

    def _f(v):
        return float(v) if v is not None else None

    items = [
        {
            "id": r.id,
            "recommendation_id": r.recommendation_id,
            "product_id": r.product_id,
            "product_name": r.product_name,
            "department_id": str(r.department_id),
            "department_name": r.department_name,
            "applied_at": str(r.applied_at),
            "eval_window_days": r.eval_window_days,
            "old_price": _f(r.old_price),
            "new_price": _f(r.new_price),
            "qty_before": _f(r.qty_before),
            "qty_after": _f(r.qty_after),
            # выручка за окно — «сколько на самом деле продали в деньгах»;
            # прибыль без неё висит в воздухе
            "revenue_before": _f(r.revenue_before),
            "revenue_after": _f(r.revenue_after),
            "gp_before": _f(r.gp_before),
            "gp_after": _f(r.gp_after),
            "expected_delta_gp": _f(r.expected_delta_gp),
            "actual_delta_gp": _f(r.actual_delta_gp),
            "qty_change_pct": _f(r.qty_change_pct),
            "control_qty_change_pct": _f(r.control_qty_change_pct),
            "adj_qty_change_pct": _f(r.adj_qty_change_pct),
            "realized_elasticity": _f(r.realized_elasticity),
            "n_control_skus": r.n_control_skus,
            "days_before": r.days_before,
            "days_after": r.days_after,
            "counterfactual_qty": _f(r.counterfactual_qty),
            "incremental_delta_gp": _f(r.incremental_delta_gp),
            "significance_z": _f(r.significance_z),
            "control_method": r.control_method,
            "measurable": r.measurable,
            "not_measurable_reason": r.not_measurable_reason,
            "n_control_stores": r.n_control_stores,
            "control_qty_before": _f(r.control_qty_before),
            "control_qty_after": _f(r.control_qty_after),
            "control_trend": _f(r.control_trend),
            # дни, выброшенные из окон из-за отсутствия товара; None — снимков
            # остатков за период нет, проверка не проводилась
            "days_no_stock_before": r.days_no_stock_before,
            "days_no_stock_after": r.days_no_stock_after,
            "store_trend_adj": _f(r.store_trend_adj),
            "effect_ci_low": _f(r.effect_ci_low),
            "effect_ci_high": _f(r.effect_ci_high),
            "p_negative": _f(r.p_negative),
            "concept": r.concept,
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@router.get("/outcomes/summary")
async def outcomes_summary(
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    dept_filter = ""
    params: dict = {}
    if department_id:
        dept_filter = "WHERE department_id = CAST(:dept_id AS uuid)"
        params["dept_id"] = department_id

    # «Подтверждено» = интервал не накрывает ноль. Раньше тут стоял порог по
    # z-оценке; интервал честнее — он показывает и знак, и величину сомнения.
    row = db.execute(
        text(f"""
            SELECT COUNT(*),
                   COALESCE(SUM(expected_delta_gp), 0),
                   COALESCE(SUM(actual_delta_gp), 0),
                   COUNT(*) FILTER (WHERE incremental_delta_gp > 0),
                   AVG(realized_elasticity),
                   COALESCE(SUM(incremental_delta_gp), 0),
                   COUNT(*) FILTER (WHERE effect_ci_low > 0 OR effect_ci_high < 0),
                   COALESCE(SUM(incremental_delta_gp)
                            FILTER (WHERE effect_ci_low > 0 OR effect_ci_high < 0), 0),
                   COUNT(*) FILTER (WHERE measurable IS NOT TRUE),
                   -- разложение «касса → фон → эффект» считаем ТОЛЬКО по
                   -- измеримым позициям, иначе прибыль по 18 позициям минус
                   -- эффект по 17 дадут контрфакт, который ни с чем не сходится
                   COALESCE(SUM(gp_before * days_after::numeric / NULLIF(days_before, 0))
                            FILTER (WHERE measurable), 0),
                   COALESCE(SUM(gp_after) FILTER (WHERE measurable), 0),
                   COUNT(*) FILTER (WHERE measurable)
            FROM price_recommendation_outcome
            {dept_filter}
        """),
        params,
    ).fetchone()

    # dept_filter подходит обеим таблицам — колонка называется одинаково
    batches = db.execute(
        text(f"""
            SELECT COUNT(*),
                   COALESCE(SUM(effect_gp), 0),
                   COALESCE(SUM(effect_ci_low), 0),
                   COALESCE(SUM(effect_ci_high), 0)
            FROM price_outcome_batch
            {dept_filter}
        """),
        params,
    ).fetchone()

    total = row[0]
    measured = total - (row[8] or 0)
    return {
        "total_evaluated": total,
        "expected_delta_gp": float(row[1]),
        "actual_delta_gp": float(row[2]),
        "positive_outcomes": row[3],
        "hit_rate": round(row[3] / measured, 4) if measured else None,
        "avg_realized_elasticity": float(row[4]) if row[4] is not None else None,
        # эффект решения о цене: контрфакт по тем же товарам в других точках
        "incremental_delta_gp": float(row[5]),
        "significant_outcomes": row[6],
        "significant_delta_gp": float(row[7]),
        "not_measurable": row[8] or 0,
        # пачка решений — главная цифра: у позиций общие дни, поэтому интервал
        # считается совместно, а не складывается
        "batches": batches[0],
        "batch_effect_gp": float(batches[1]),
        "batch_ci_low": float(batches[2]),
        "batch_ci_high": float(batches[3]),
        # цепочка для разложения итога на экране: было → стало → было бы
        "decomp_positions": row[11],
        "decomp_gp_before": float(row[9]),
        "decomp_gp_after": float(row[10]),
        "decomp_cash": float(row[10]) - float(row[9]),
    }


@router.get("/outcomes/{outcome_id}/daily")
async def outcome_daily_series(outcome_id: int, db: Session = Depends(get_db)):
    """Дневные ряды «факт против контрфакта» для одного измеренного решения.

    Нужен, чтобы показать метод картинкой: одно число не объясняет, откуда
    взялся эффект, а две линии — объясняют.
    """
    from ..services.pricing_effect import PriceEffectEstimator

    row = db.execute(
        text("""
            SELECT o.product_id, o.department_id::text, o.applied_at,
                   o.baseline_from, o.baseline_to, o.eval_from, o.eval_to,
                   o.old_price, o.new_price, o.measurable, o.not_measurable_reason,
                   o.counterfactual_qty, o.qty_after, o.incremental_delta_gp,
                   (o.revenue_before - o.gp_before) / NULLIF(o.qty_before, 0) AS cogs,
                   p.name AS product_name, d.name AS department_name
            FROM price_recommendation_outcome o
            JOIN product p ON p.id = o.product_id
            JOIN departments d ON d.id = o.department_id
            WHERE o.id = :oid
        """),
        {"oid": outcome_id},
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Outcome not found")

    head = {
        "outcome_id": outcome_id,
        "product_id": row.product_id,
        "product_name": row.product_name,
        "department_id": row.department_id,
        "department_name": row.department_name,
        "applied_at": str(row.applied_at),
        "old_price": float(row.old_price) if row.old_price is not None else None,
        "new_price": float(row.new_price) if row.new_price is not None else None,
        "measurable": row.measurable,
        "not_measurable_reason": row.not_measurable_reason,
        "counterfactual_qty": float(row.counterfactual_qty) if row.counterfactual_qty is not None else None,
        "qty_after": float(row.qty_after) if row.qty_after is not None else None,
        "incremental_delta_gp": float(row.incremental_delta_gp) if row.incremental_delta_gp is not None else None,
    }
    if not row.measurable:
        return {**head, "days": []}

    est = PriceEffectEstimator(db)
    panel, res = est.build_panel(
        product_id=row.product_id, dept_id=row.department_id,
        old_price=float(row.old_price or 0), new_price=float(row.new_price or 0),
        cogs=float(row.cogs or 0),
        baseline_from=row.baseline_from, baseline_to=row.baseline_to,
        eval_from=row.eval_from, eval_to=row.eval_to,
    )
    if panel is None:
        return {**head, "days": [], "not_measurable_reason": res.reason}
    return {**head, "days": est.daily_breakdown(panel)}


@router.get("/outcomes/batches")
async def list_outcome_batches(
    department_id: Optional[str] = None,
    concept: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    """Эффект приказов целиком. concept разделяет Madlen и Sandyq."""
    conditions = ["1=1"]
    params: dict = {"limit": limit}
    if department_id:
        conditions.append("b.department_id = CAST(:dept_id AS uuid)")
        params["dept_id"] = department_id
    if concept:
        conditions.append("b.concept = :concept")
        params["concept"] = concept

    rows = db.execute(
        text(f"""
            SELECT b.*, d.name AS department_name
            FROM price_outcome_batch b
            JOIN departments d ON d.id = b.department_id
            WHERE {" AND ".join(conditions)}
            ORDER BY b.applied_at DESC, b.id DESC
            LIMIT :limit
        """),
        params,
    ).fetchall()

    def _f(v):
        return float(v) if v is not None else None

    return {"items": [
        {
            "id": r.id,
            "department_id": str(r.department_id),
            "department_name": r.department_name,
            "applied_at": str(r.applied_at),
            "concept": r.concept,
            "eval_window_days": r.eval_window_days,
            "n_positions": r.n_positions,
            "n_measurable": r.n_measurable,
            "gp_before": _f(r.gp_before),
            "gp_after": _f(r.gp_after),
            "actual_delta_gp": _f(r.actual_delta_gp),
            "expected_delta_gp": _f(r.expected_delta_gp),
            "effect_gp": _f(r.effect_gp),
            "effect_ci_low": _f(r.effect_ci_low),
            "effect_ci_high": _f(r.effect_ci_high),
            "p_negative": _f(r.p_negative),
        }
        for r in rows
    ]}


@router.post("/baseline/freeze")
def freeze_baseline(
    label: str = Query(..., description="Например 'pre-pilot-2026-06'"),
    weeks: int = Query(8, ge=2, le=26),
    force: bool = Query(False, description="Перезаписать существующий label"),
    as_of: Optional[date] = Query(
        None,
        description="Отсчитывать окно не от сегодня, а от этой даты — "
                    "чтобы пересчитать уже замороженный снимок за ТОТ ЖЕ период",
    ),
    user: Optional[AppUser] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Заморозить KPI за N полных недель как базу для метрики пилота.
    Существующий label без force=true не перезаписывается (409)."""
    from ..services.pricing_feedback_service import PricingFeedbackService
    _require_section(user, "pricing.outcomes")
    result = PricingFeedbackService(db).freeze_baseline(label, weeks, force=force,
                                                        actor=_actor_of(user), as_of=as_of)
    if result.get("status") == "error" and result.get("code") in _CONFLICT_CODES:
        raise HTTPException(409, result.get("message"))
    return result


@router.get("/baseline")
async def get_baseline(
    label: Optional[str] = None,
    db: Session = Depends(get_db),
):
    conditions = ["1=1"]
    params: dict = {}
    if label:
        conditions.append("b.label = :label")
        params["label"] = label
    where = " AND ".join(conditions)

    rows = db.execute(
        text(f"""
            SELECT b.*, d.name AS department_name
            FROM pricing_baseline_kpi b
            LEFT JOIN departments d ON d.id = b.department_id
            WHERE {where}
            ORDER BY b.label, b.scope DESC, d.name NULLS FIRST
        """),
        params,
    ).fetchall()

    def _f(v):
        return float(v) if v is not None else None

    items = [
        {
            "id": r.id,
            "label": r.label,
            "scope": r.scope,
            "department_id": str(r.department_id) if r.department_id else None,
            "department_name": r.department_name,
            "baseline_from": str(r.baseline_from),
            "baseline_to": str(r.baseline_to),
            "weeks": r.weeks,
            "total_revenue": _f(r.total_revenue),
            "total_cost": _f(r.total_cost),
            "gross_profit": _f(r.gross_profit),
            "gp_margin": _f(r.gp_margin),
            "total_receipts": r.total_receipts,
            "avg_receipt_sum": _f(r.avg_receipt_sum),
            "weekly_gp_avg": _f(r.weekly_gp_avg),
            "weekly_gp_stddev": _f(r.weekly_gp_stddev),
            "active_skus": r.active_skus,
            "cost_coverage": _f(r.cost_coverage),
            "created_at": str(r.created_at),
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/recommendations/summary")
async def recommendations_summary(
    department_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    dept_filter = ""
    params: dict = {}
    if department_id:
        dept_filter = "WHERE department_id = CAST(:dept_id AS uuid)"
        params["dept_id"] = department_id

    by_status = {}
    rows = db.execute(
        text(f"SELECT status, COUNT(*) FROM price_recommendation {dept_filter} GROUP BY 1"),
        params,
    ).fetchall()
    for r in rows:
        by_status[r[0]] = r[1]

    total_delta_gp = db.execute(
        text(f"""
            SELECT COALESCE(SUM(delta_gp), 0)
            FROM price_recommendation
            {'WHERE department_id = CAST(:dept_id AS uuid) AND' if department_id else 'WHERE'}
            status = 'new' AND delta_gp > 0
        """),
        params,
    ).scalar()

    return {
        "by_status": by_status,
        "total": sum(by_status.values()),
        "total_delta_gp_new": float(total_delta_gp),
    }


# ==================== C4: Pricing reports ====================

def _report_row(r) -> dict:
    return {
        "id": r.id,
        "report_type": r.report_type,
        "scope": r.scope,
        "department_id": str(r.department_id) if r.department_id else None,
        "department_name": getattr(r, "department_name", None),
        "period_start": str(r.period_start),
        "period_end": str(r.period_end),
        "kpis": r.kpis,
        "provider": r.provider,
        "model": r.model,
        "status": r.status,
        "created_at": str(r.created_at),
    }


@router.get("/reports")
async def list_reports(
    report_type: Optional[str] = None,
    department_id: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    conditions = ["1=1"]
    params: dict = {}
    if report_type:
        conditions.append("rp.report_type = :rt")
        params["rt"] = report_type
    if department_id:
        conditions.append("rp.department_id = CAST(:dept AS uuid)")
        params["dept"] = department_id
    where = " AND ".join(conditions)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM pricing_report rp WHERE {where}"), params
    ).scalar()
    rows = db.execute(
        text(f"""
            SELECT rp.id, rp.report_type, rp.scope, rp.department_id,
                   d.name AS department_name, rp.period_start, rp.period_end,
                   rp.kpis, rp.provider, rp.model, rp.status, rp.created_at
            FROM pricing_report rp
            LEFT JOIN departments d ON d.id = rp.department_id
            WHERE {where}
            ORDER BY rp.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": limit, "offset": offset},
    ).fetchall()
    return {"items": [_report_row(r) for r in rows], "total": total}


@router.get("/reports/{report_id}")
async def get_report(report_id: int, db: Session = Depends(get_db)):
    r = db.execute(
        text("""
            SELECT rp.*, d.name AS department_name
            FROM pricing_report rp
            LEFT JOIN departments d ON d.id = rp.department_id
            WHERE rp.id = :id
        """),
        {"id": report_id},
    ).fetchone()
    if not r:
        raise HTTPException(404, "Report not found")
    out = _report_row(r)
    out["data"] = r.data
    out["narrative"] = r.narrative
    return out


@router.post("/reports/generate")
async def generate_report(
    report_type: str = Query(..., description="weekly | monthly"),
    department_id: Optional[str] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if report_type not in ("weekly", "monthly", "effect"):
        raise HTTPException(400, "report_type must be 'weekly', 'monthly' or 'effect'")

    # Отчёт об эффекте собирается расчётом, а не LLM: в нём три числа, которые
    # легко перепутать (касса / эффект / уверенность), и пересказ моделью
    # воспроизводил бы ровно ту ошибку, которую подсистема уже допускала.
    if report_type == "effect":
        if not department_id:
            raise HTTPException(400, "department_id обязателен для отчёта об эффекте")
        from ..services.pricing_effect_report import PricingEffectReportService
        report = PricingEffectReportService(db).generate(department_id)
        return {
            "id": report.id,
            "report_type": report.report_type,
            "status": report.status,
            "period_start": str(report.period_start),
            "period_end": str(report.period_end),
            "has_narrative": report.narrative is not None,
        }

    from ..services.pricing_report_service import (
        PricingReportService, last_full_week, last_full_month,
    )
    if period_start is None or period_end is None:
        period_start, period_end = (
            last_full_week(date.today()) if report_type == "weekly"
            else last_full_month(date.today())
        )
    report = await PricingReportService(db).generate(
        report_type, period_start, period_end, department_id, provider
    )
    return {
        "id": report.id,
        "report_type": report.report_type,
        "status": report.status,
        "period_start": str(report.period_start),
        "period_end": str(report.period_end),
        "has_narrative": report.narrative is not None,
    }
