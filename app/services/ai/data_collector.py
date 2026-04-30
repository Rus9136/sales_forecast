"""Direct DB data collection for AI agents.

Replaces the MCP API client used in hr-miniapp. Returns a dict in the same
shape that agents expect, so the agent code stays unchanged.

Sections:
- forecast       — predicted sales per day (and actual where available)
- plan_vs_fact   — combined predicted/actual with deviation
- hourly_sales   — sales by hour
- department_info — department metadata
- payroll        — None for now (Variant A)
- reviews        — None for now (Variant A)
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _get_forecast(
    db: Session, department_id: UUID, date_start: date, date_end: date
) -> list[dict]:
    """Predicted sales per day for the period, with actual when available.

    `forecasts.branch_id` is a VARCHAR holding the same UUID as departments.id.
    """
    rows = db.execute(
        text(
            """
            SELECT
                f.forecast_date AS date,
                f.predicted_amount AS predicted_sales,
                s.total_sales AS actual_sales
            FROM forecasts f
            LEFT JOIN sales_summary s
                ON s.department_id = :dept_id
                AND s.date = f.forecast_date
            WHERE f.branch_id = :branch_id
              AND f.forecast_date BETWEEN :date_start AND :date_end
            ORDER BY f.forecast_date
            """
        ),
        {
            "dept_id": str(department_id),
            "branch_id": str(department_id),
            "date_start": date_start,
            "date_end": date_end,
        },
    ).mappings().all()

    return [
        {
            "date": r["date"].isoformat(),
            "predicted_sales": float(r["predicted_sales"]) if r["predicted_sales"] is not None else None,
            "actual_sales": float(r["actual_sales"]) if r["actual_sales"] is not None else None,
        }
        for r in rows
    ]


def _get_plan_vs_fact(
    db: Session, department_id: UUID, date_start: date, date_end: date
) -> list[dict]:
    """Plan vs fact comparison.

    Uses sales_summary as the driving table so we still get rows on days where
    no forecast was made. Includes deviation as a percentage.
    """
    rows = db.execute(
        text(
            """
            SELECT
                s.date,
                f.predicted_amount AS predicted_sales,
                s.total_sales AS actual_sales,
                CASE
                    WHEN f.predicted_amount IS NOT NULL AND f.predicted_amount > 0
                    THEN ((s.total_sales - f.predicted_amount) / f.predicted_amount) * 100
                    ELSE NULL
                END AS error_percentage
            FROM sales_summary s
            LEFT JOIN forecasts f
                ON f.branch_id = :branch_id
                AND f.forecast_date = s.date
            WHERE s.department_id = :dept_id
              AND s.date BETWEEN :date_start AND :date_end
            ORDER BY s.date
            """
        ),
        {
            "dept_id": str(department_id),
            "branch_id": str(department_id),
            "date_start": date_start,
            "date_end": date_end,
        },
    ).mappings().all()

    return [
        {
            "date": r["date"].isoformat(),
            "predicted_sales": float(r["predicted_sales"]) if r["predicted_sales"] is not None else None,
            "actual_sales": float(r["actual_sales"]) if r["actual_sales"] is not None else None,
            "error_percentage": float(r["error_percentage"]) if r["error_percentage"] is not None else None,
        }
        for r in rows
    ]


def _get_hourly_sales(
    db: Session, department_id: UUID, date_start: date, date_end: date
) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT date, hour, sales_amount
            FROM sales_by_hour
            WHERE department_id = :dept_id
              AND date BETWEEN :date_start AND :date_end
            ORDER BY date, hour
            """
        ),
        {
            "dept_id": str(department_id),
            "date_start": date_start,
            "date_end": date_end,
        },
    ).mappings().all()

    return [
        {
            "date": r["date"].isoformat(),
            "hour": int(r["hour"]),
            "sales_amount": float(r["sales_amount"]) if r["sales_amount"] is not None else 0.0,
        }
        for r in rows
    ]


def _get_department_info(db: Session, department_id: UUID) -> Optional[dict]:
    row = db.execute(
        text(
            """
            SELECT
                d.id,
                d.name,
                d.code,
                d.type,
                d.brand,
                d.city,
                d.location_type,
                d.segment_type,
                d.is_24_7,
                d.opening_hour,
                d.closing_hour,
                p.name AS parent_name
            FROM departments d
            LEFT JOIN departments p ON p.id = d.parent_id
            WHERE d.id = :dept_id
            """
        ),
        {"dept_id": str(department_id)},
    ).mappings().first()

    if not row:
        return None

    return {
        "object_name": row["name"],
        "object_code": row["code"],
        "object_company": row["parent_name"] or row["name"],
        "type": row["type"],
        "brand": row["brand"],
        "city": row["city"],
        "location_type": row["location_type"],
        "segment_type": row["segment_type"],
        "is_24_7": bool(row["is_24_7"]),
        "opening_hour": row["opening_hour"],
        "closing_hour": row["closing_hour"],
        # Fields kept for prompt compatibility — not stored in our schema yet.
        "hall_area": None,
        "kitchen_area": None,
        "seats_count": None,
    }


def collect_dashboard_data(
    db: Session,
    department_id: Any,
    date_start: date,
    date_end: date,
) -> dict:
    """Collect all sections needed by the agents.

    Output schema mirrors the hr-miniapp MCP response so existing agent code
    can consume it without changes. Sections without a local data source
    (`payroll`, `reviews`) are returned as None — agents that depend on them
    are disabled in Variant A.
    """
    dept_id = _coerce_uuid(department_id)

    forecast = _get_forecast(db, dept_id, date_start, date_end)
    plan_vs_fact = _get_plan_vs_fact(db, dept_id, date_start, date_end)
    hourly_sales = _get_hourly_sales(db, dept_id, date_start, date_end)
    department_info = _get_department_info(db, dept_id)

    return {
        "forecast": forecast,
        "plan_vs_fact": plan_vs_fact,
        "hourly_sales": hourly_sales,
        "department_info": department_info,
        "payroll": None,
        "reviews": None,
    }
