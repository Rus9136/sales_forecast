-- Migration: Department enrichment metadata for ML-feature engineering
-- Date: 2026-04-30
-- Description: Adds operational characteristics for sales forecasting model
--   (location type, brand, opening hours, seasonality, tourist dependency).
--   All fields are manual-only — iiko sync MUST NOT touch them.

ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS brand                       VARCHAR(50),
    ADD COLUMN IF NOT EXISTS location_type               VARCHAR(30),
    ADD COLUMN IF NOT EXISTS tourist_traffic_dependent   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_24_7                     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS opening_hour                SMALLINT,
    ADD COLUMN IF NOT EXISTS closing_hour                SMALLINT,
    ADD COLUMN IF NOT EXISTS seasonality_intensity       VARCHAR(10) NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS city                        VARCHAR(100),
    ADD COLUMN IF NOT EXISTS opened_date                 DATE,
    ADD COLUMN IF NOT EXISTS season_start_month          SMALLINT,
    ADD COLUMN IF NOT EXISTS season_end_month            SMALLINT;

ALTER TABLE departments
    ADD CONSTRAINT chk_dept_location_type CHECK (
        location_type IS NULL OR location_type IN (
            'city_center', 'mall', 'business_district',
            'resort_mountain', 'resort_lake', 'visit_center', 'other'
        )
    ),
    ADD CONSTRAINT chk_dept_seasonality CHECK (
        seasonality_intensity IN ('none', 'low', 'medium', 'high')
    ),
    ADD CONSTRAINT chk_dept_opening_hour CHECK (
        opening_hour IS NULL OR opening_hour BETWEEN 0 AND 23
    ),
    ADD CONSTRAINT chk_dept_closing_hour CHECK (
        closing_hour IS NULL OR closing_hour BETWEEN 0 AND 24
    ),
    ADD CONSTRAINT chk_dept_season_start CHECK (
        season_start_month IS NULL OR season_start_month BETWEEN 1 AND 12
    ),
    ADD CONSTRAINT chk_dept_season_end CHECK (
        season_end_month IS NULL OR season_end_month BETWEEN 1 AND 12
    );

CREATE INDEX IF NOT EXISTS idx_departments_brand         ON departments(brand);
CREATE INDEX IF NOT EXISTS idx_departments_location_type ON departments(location_type);

COMMENT ON COLUMN departments.brand                     IS 'Бренд (Tary, Sandyq, Madlen, ...). Manual-only.';
COMMENT ON COLUMN departments.location_type             IS 'Тип локации: city_center | mall | business_district | resort_mountain | resort_lake | visit_center | other';
COMMENT ON COLUMN departments.tourist_traffic_dependent IS 'Зависит ли поток посетителей от туристического трафика';
COMMENT ON COLUMN departments.is_24_7                   IS 'Работает 24/7 (если TRUE, opening/closing_hour игнорируются)';
COMMENT ON COLUMN departments.opening_hour              IS 'Час открытия 0..23 (локальное время)';
COMMENT ON COLUMN departments.closing_hour              IS 'Час закрытия 0..24 (24 = полночь)';
COMMENT ON COLUMN departments.seasonality_intensity     IS 'Интенсивность сезонности: none | low | medium | high';
COMMENT ON COLUMN departments.city                      IS 'Город размещения';
COMMENT ON COLUMN departments.opened_date               IS 'Дата открытия точки (для фичи "tenure")';
COMMENT ON COLUMN departments.season_start_month        IS 'Месяц старта сезона 1..12 (если seasonality_intensity != none)';
COMMENT ON COLUMN departments.season_end_month          IS 'Месяц конца сезона 1..12 (если seasonality_intensity != none)';
