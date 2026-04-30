"""Top errors analysis on backtest output."""
from __future__ import annotations
import sys
import pandas as pd

src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/backtest_results.csv"
df = pd.read_csv(src)

df["err"] = df["raw"] - df["actual"]
df["ape"] = (df["err"].abs() / df["actual"]).clip(upper=10)
df["abs_err"] = df["err"].abs()
df["date"] = pd.to_datetime(df["date"]).dt.date

# Top 50 worst by APE (filter actual > 50K to avoid trivial small-denominator cases)
top = (df[df["actual"] > 50_000]
       .sort_values("ape", ascending=False)
       .head(50)
       .copy())
top["under_pred_pct"] = (top["err"] / top["actual"] * 100).round(1)

print("\n" + "=" * 100)
print("TOP-50 WORST FORECASTS (by APE, actual > 50K)")
print("=" * 100)
print(f"{'date':<12} {'segment':<11} {'dept':<35} {'actual':>12} {'raw':>12} {'APE%':>7} {'underΔ%':>8}")
for _, r in top.iterrows():
    name = (r["department_name"] or "")[:35]
    print(f"{str(r['date']):<12} {(r['segment_type'] or '?')[:10]:<11} {name:<35} "
          f"{r['actual']:>12,.0f} {r['raw']:>12,.0f} {r['ape']*100:>6.1f}% {r['under_pred_pct']:>7.1f}%")

# Patterns in top-50
print("\n" + "=" * 100)
print("PATTERNS IN TOP-50")
print("=" * 100)

print("\nBy segment:")
print(top.groupby("segment_type")
      .agg(n=("ape", "size"), avg_ape=("ape", lambda s: round(s.mean()*100, 1)),
           avg_actual=("actual", lambda s: round(s.mean()))).sort_values("n", ascending=False)
      .to_string())

print("\nBy date (most frequent):")
date_counts = top["date"].value_counts().head(10)
for d, n in date_counts.items():
    same_day = top[top["date"] == d]
    weekday = pd.Timestamp(d).day_name()
    print(f"  {d} ({weekday}): {n} bad forecasts, "
          f"avg actual {same_day['actual'].mean():,.0f}, avg pred {same_day['raw'].mean():,.0f}, "
          f"avg APE {same_day['ape'].mean()*100:.0f}%")

print("\nBy department (most frequent in top-50):")
dept_counts = (top.groupby("department_name").size().sort_values(ascending=False).head(15))
for name, n in dept_counts.items():
    same = top[top["department_name"] == name]
    print(f"  {n}× | {name[:50]:<50} avg actual {same['actual'].mean():>10,.0f}, "
          f"avg APE {same['ape'].mean()*100:.0f}%")

# Direction of errors
print(f"\nUnder-predictions (model too low): {(top['err'] < 0).sum()} / 50")
print(f"Over-predictions (model too high):  {(top['err'] > 0).sum()} / 50")

# Are these days holidays?
KZ_HOLIDAYS = [
    (1, 1), (1, 2), (3, 8), (3, 21), (3, 22), (3, 23), (3, 24),
    (5, 1), (5, 7), (5, 9), (7, 6), (8, 30), (12, 1), (12, 16), (12, 17), (12, 18),
    (5, 27),  # Kurban-Ait 2026
]
top["is_kz_holiday"] = top["date"].apply(lambda d: (d.month, d.day) in KZ_HOLIDAYS)
print(f"\nOn Kazakhstan holidays:        {top['is_kz_holiday'].sum()} / 50")

# Pre/post holiday
def near_holiday(d, days=2):
    for offset in range(-days, days + 1):
        dd = d + pd.Timedelta(days=offset)
        if (dd.month, dd.day) in KZ_HOLIDAYS:
            return True
    return False

top["near_holiday_2d"] = top["date"].apply(lambda d: near_holiday(pd.Timestamp(d)))
print(f"Within ±2 days of KZ holiday:  {top['near_holiday_2d'].sum()} / 50")

# Compare to overall: random sample
random_sample = df[df["actual"] > 50_000].sample(min(500, len(df)), random_state=42)
random_sample["near_holiday_2d"] = random_sample["date"].apply(lambda d: near_holiday(pd.Timestamp(d)))
holiday_rate_overall = random_sample["near_holiday_2d"].mean()
print(f"  (overall sample {len(random_sample)} rows: holiday rate {holiday_rate_overall*100:.1f}%)")

# Weekend pattern
weekend_count = sum(pd.Timestamp(d).dayofweek in (5, 6) for d in top["date"])
print(f"\nOn weekends (Sat/Sun):         {weekend_count} / 50")

# Per-department total error contribution
print("\n" + "=" * 100)
print("WORST DEPARTMENTS BY MEAN APE (filter actual > 50K, n >= 30)")
print("=" * 100)
dept_stats = (df[df["actual"] > 50_000]
              .groupby("department_name")
              .agg(n=("ape", "size"),
                   mean_ape=("ape", lambda s: round(s.mean()*100, 1)),
                   median_ape=("ape", lambda s: round(s.median()*100, 1)),
                   avg_actual=("actual", lambda s: round(s.mean())))
              .query("n >= 30")
              .sort_values("mean_ape", ascending=False)
              .head(15))
print(dept_stats.to_string())
