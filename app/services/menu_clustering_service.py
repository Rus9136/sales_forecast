"""SKU menu role clustering — classifies each (product, department) into 5 business roles.

Roles: premium_anchor, margin_driver, traffic_driver, image_rare, tail.
Uses KMeans on 5 features derived from sku_weekly_summary (90-day window).
"""

import json
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

FEATURE_SQL = text("""
    WITH active_window AS (
        SELECT product_id, department_id,
               SUM(total_qty)     AS sum_qty,
               SUM(total_revenue) AS sum_revenue,
               AVG(gp_margin)     AS avg_gp_margin,
               AVG(qty_cv)        AS avg_qty_cv,
               AVG(avg_price)     AS avg_price,
               COUNT(*)           AS weeks_active
        FROM sku_weekly_summary
        WHERE week_start >= :cutoff_date
          AND total_qty > 0
        GROUP BY product_id, department_id
        HAVING COUNT(*) >= 3
    ),
    dept_totals AS (
        SELECT department_id,
               SUM(sum_qty)     AS dept_total_qty,
               SUM(sum_revenue) AS dept_total_revenue
        FROM active_window
        GROUP BY department_id
    ),
    category_medians AS (
        SELECT p.category_id,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY aw.avg_price) AS median_price
        FROM active_window aw
        JOIN product p ON p.id = aw.product_id
        WHERE p.category_id IS NOT NULL
        GROUP BY p.category_id
    )
    SELECT
        aw.product_id,
        aw.department_id::text,
        CASE WHEN dt.dept_total_qty > 0
             THEN aw.sum_qty / dt.dept_total_qty ELSE 0 END AS qty_share,
        CASE WHEN dt.dept_total_revenue > 0
             THEN aw.sum_revenue / dt.dept_total_revenue ELSE 0 END AS revenue_share,
        COALESCE(aw.avg_gp_margin, 0)  AS gp_margin,
        COALESCE(aw.avg_qty_cv, 1.0)   AS demand_cv,
        CASE WHEN cm.median_price > 0
             THEN aw.avg_price / cm.median_price ELSE 1.0 END AS price_index
    FROM active_window aw
    JOIN dept_totals dt ON dt.department_id = aw.department_id
    JOIN product p ON p.id = aw.product_id
    LEFT JOIN category_medians cm ON cm.category_id = p.category_id
""")

UPSERT_SQL = text("""
    INSERT INTO sku_menu_role
        (product_id, department_id, auto_role, features, cluster_meta, updated_at)
    VALUES (:product_id, CAST(:department_id AS uuid), :auto_role,
            CAST(:features AS jsonb), CAST(:cluster_meta AS jsonb), NOW())
    ON CONFLICT (product_id, department_id)
    DO UPDATE SET
        auto_role    = EXCLUDED.auto_role,
        features     = EXCLUDED.features,
        cluster_meta = EXCLUDED.cluster_meta,
        updated_at   = NOW()
""")

FEATURE_NAMES = ["qty_share", "revenue_share", "gp_margin", "demand_cv", "price_index"]

ROLE_SCORES = {
    "traffic_driver":  {"qty_share": 2.0, "revenue_share": 1.5, "demand_cv": -1.5, "price_index": -0.5},
    "margin_driver":   {"gp_margin": 2.0, "revenue_share": 1.0, "qty_share": 0.5},
    "premium_anchor":  {"price_index": 2.0, "qty_share": -1.0, "demand_cv": -0.5, "gp_margin": 0.5},
    "tail":            {"qty_share": -1.5, "gp_margin": -2.0, "revenue_share": -1.5},
    "image_rare":      {"qty_share": -1.5, "price_index": 1.5, "revenue_share": -1.0, "demand_cv": 0.5},
}

ROLE_PRIORITY = ["traffic_driver", "margin_driver", "premium_anchor", "tail", "image_rare"]


class MenuClusteringService:
    def __init__(self, db: Session):
        self.db = db

    def run_clustering(self, lookback_days: int = 90) -> dict:
        cutoff_date = date.today() - timedelta(days=lookback_days)
        logger.info("Menu clustering: cutoff=%s, lookback=%dd", cutoff_date, lookback_days)

        rows = self.db.execute(FEATURE_SQL, {"cutoff_date": cutoff_date}).fetchall()
        if not rows:
            logger.warning("No data for clustering")
            return {"status": "no_data", "skus_classified": 0}

        df = pd.DataFrame(rows, columns=["product_id", "department_id"] + FEATURE_NAMES)
        for col in FEATURE_NAMES:
            df[col] = df[col].astype(float)

        X, scaler = self._normalize(df)
        labels, centroids, sil, inertia = self._fit(X)
        role_map = self._map_roles(centroids)
        df["auto_role"] = [role_map[l] for l in labels]

        self._upsert(df, labels, centroids, sil, X)

        dist = df["auto_role"].value_counts().to_dict()
        logger.info("Clustering done: %d SKUs, silhouette=%.4f, dist=%s", len(df), sil, dist)
        return {
            "status": "ok",
            "skus_classified": len(df),
            "silhouette_score": round(float(sil), 4),
            "role_distribution": dist,
            "lookback_days": lookback_days,
        }

    def _normalize(self, df: pd.DataFrame):
        features = df[FEATURE_NAMES].copy()
        EPS = 1e-8
        features["qty_share"] = np.log1p(features["qty_share"] * 1000)
        features["revenue_share"] = np.log1p(features["revenue_share"] * 1000)
        features["price_index"] = np.log(features["price_index"].clip(lower=EPS))
        features["gp_margin"] = features["gp_margin"].clip(-1.0, 2.0)
        features["demand_cv"] = features["demand_cv"].clip(0.0, 5.0)
        scaler = StandardScaler()
        X = scaler.fit_transform(features.values)
        return X, scaler

    def _fit(self, X: np.ndarray):
        km = KMeans(n_clusters=5, init="k-means++", n_init=20, max_iter=500, random_state=42)
        labels = km.fit_predict(X)
        sil = silhouette_score(X, labels, sample_size=min(10000, len(X)))
        return labels, km.cluster_centers_, float(sil), float(km.inertia_)

    def _map_roles(self, centroids: np.ndarray) -> list:
        feat_idx = {n: i for i, n in enumerate(FEATURE_NAMES)}
        roles = list(ROLE_SCORES.keys())
        scores = np.zeros((len(roles), centroids.shape[0]))

        for ri, role in enumerate(roles):
            for feat, w in ROLE_SCORES[role].items():
                scores[ri, :] += w * centroids[:, feat_idx[feat]]

        cluster_to_role = {}
        used = set()
        for role in ROLE_PRIORITY:
            ri = roles.index(role)
            s = scores[ri].copy()
            for u in used:
                s[u] = -np.inf
            best = int(np.argmax(s))
            cluster_to_role[best] = role
            used.add(best)

        return [cluster_to_role[i] for i in range(centroids.shape[0])]

    def _upsert(self, df: pd.DataFrame, labels, centroids, sil: float, X: np.ndarray):
        run_date = str(date.today())
        n_total = len(df)
        CHUNK = 500

        params_list = []
        for i, row in enumerate(df.itertuples(index=False)):
            params_list.append({
                "product_id": int(row.product_id),
                "department_id": str(row.department_id),
                "auto_role": row.auto_role,
                "features": json.dumps({
                    "qty_share": round(float(row.qty_share), 6),
                    "revenue_share": round(float(row.revenue_share), 6),
                    "gp_margin": round(float(row.gp_margin), 4),
                    "demand_cv": round(float(row.demand_cv), 4),
                    "price_index": round(float(row.price_index), 4),
                }),
                "cluster_meta": json.dumps({
                    "cluster_id": int(labels[i]),
                    "silhouette": round(float(sil), 4),
                    "centroid_dist": round(float(np.linalg.norm(X[i] - centroids[labels[i]])), 4),
                    "run_date": run_date,
                    "n_skus": n_total,
                }),
            })

        for start in range(0, len(params_list), CHUNK):
            for p in params_list[start:start + CHUNK]:
                self.db.execute(UPSERT_SQL, p)
        self.db.commit()
