"""For each top-N worst forecast, show surrounding sales context."""
from __future__ import annotations
import sys
from datetime import timedelta
import pandas as pd
sys.path.insert(0, "/app")

from app.db import get_db
from app.models.branch import Department, SalesSummary

db = next(get_db())

cases = [
    ("Tary Ayusai", "2026-04-16"),
    ("Sandyq  Алматы", "2026-04-04"),
    ("Tary Burabay", "2026-03-17"),
    ("Сандык Кайнар", "2026-04-18"),
    ("Tary Kolsay", "2026-04-06"),
    ("Tary Burabay", "2026-03-11"),
]

for dept_name, target_date in cases:
    dept = db.query(Department).filter(Department.name == dept_name).first()
    if not dept:
        print(f"NOT FOUND: {dept_name}")
        continue
    target = pd.to_datetime(target_date).date()
    rows = (db.query(SalesSummary.date, SalesSummary.total_sales)
            .filter(SalesSummary.department_id == dept.id)
            .filter(SalesSummary.date >= target - timedelta(days=14))
            .filter(SalesSummary.date <= target + timedelta(days=7))
            .order_by(SalesSummary.date).all())
    print(f"\n=== {dept_name} | target {target_date} ===")
    print(f"{'date':<12} {'wd':<3} {'sales':>14} {'<-- bad day' if False else ''}")
    for r in rows:
        wd_name = pd.Timestamp(r.date).day_name()[:3]
        marker = "  <-- BAD" if r.date == target else ""
        print(f"{r.date}  {wd_name:<3} {float(r.total_sales):>14,.0f}{marker}")

# Also: same weekday recent history for Tary Ayusai
print("\n\n=== Tary Ayusai — same weekday (Thursday) history ===")
dept = db.query(Department).filter(Department.name == "Tary Ayusai").first()
if dept:
    rows = (db.query(SalesSummary.date, SalesSummary.total_sales)
            .filter(SalesSummary.department_id == dept.id)
            .filter(SalesSummary.date >= pd.to_datetime("2026-01-01").date())
            .filter(SalesSummary.date <= pd.to_datetime("2026-04-29").date())
            .order_by(SalesSummary.date).all())
    df = pd.DataFrame([{"date": r.date, "sales": float(r.total_sales)} for r in rows])
    df["weekday"] = pd.to_datetime(df["date"]).dt.day_name()
    print(df[df["weekday"] == "Thursday"].to_string(index=False))

    print(f"\nTotal sales by month for Tary Ayusai (all weekdays):")
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")
    print(df.groupby("month")["sales"].agg(["sum", "mean", "count"]).to_string())
