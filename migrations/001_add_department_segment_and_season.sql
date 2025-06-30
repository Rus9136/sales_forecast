-- Migration: Add segment_type and seasonal fields to departments table
-- Date: 2025-06-28
-- Description: Adds segment_type enum and seasonal date fields for enhanced forecasting

-- Add segment_type column with enum values
ALTER TABLE departments 
ADD COLUMN segment_type VARCHAR(50) DEFAULT 'restaurant' CHECK (
    segment_type IN (
        'coffeehouse',     -- кофейня
        'restaurant',      -- ресторан  
        'confectionery',   -- кондитерская
        'food_court',      -- фудкорт в ТРЦ
        'store',           -- магазин
        'fast_food',       -- фаст-фуд
        'bakery',          -- пекарня
        'cafe',            -- кафе
        'bar'              -- бар
    )
);

-- Add seasonal fields (optional, mainly for coffeehouses)
ALTER TABLE departments 
ADD COLUMN season_start_date DATE,
ADD COLUMN season_end_date DATE;

-- Add indexes for better performance
CREATE INDEX ix_departments_segment_type ON departments(segment_type);
CREATE INDEX ix_departments_season_dates ON departments(season_start_date, season_end_date);

-- Add comments for documentation
COMMENT ON COLUMN departments.segment_type IS 'Тип подразделения для улучшения прогнозирования';
COMMENT ON COLUMN departments.season_start_date IS 'Дата начала сезона (опционально, в основном для кофеен)';
COMMENT ON COLUMN departments.season_end_date IS 'Дата окончания сезона (опционально, в основном для кофеен)';