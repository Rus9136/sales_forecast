-- Migration 003: Add postprocessing_settings table
-- Created: 2025-06-30
-- Purpose: Store user-configurable post-processing settings for forecasts

CREATE TABLE IF NOT EXISTS postprocessing_settings (
    id SERIAL PRIMARY KEY,
    
    -- Smoothing settings
    enable_smoothing BOOLEAN NOT NULL DEFAULT TRUE,
    max_change_percent FLOAT NOT NULL DEFAULT 50.0,
    
    -- Business rules settings  
    enable_business_rules BOOLEAN NOT NULL DEFAULT TRUE,
    enable_weekend_adjustment BOOLEAN NOT NULL DEFAULT TRUE,
    enable_holiday_adjustment BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Anomaly detection settings
    enable_anomaly_detection BOOLEAN NOT NULL DEFAULT TRUE,
    anomaly_threshold FLOAT NOT NULL DEFAULT 3.0,
    
    -- Confidence intervals settings
    enable_confidence BOOLEAN NOT NULL DEFAULT TRUE,
    confidence_level FLOAT NOT NULL DEFAULT 0.95,
    
    -- Metadata
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create index for active settings lookup
CREATE INDEX IF NOT EXISTS idx_postprocessing_settings_active ON postprocessing_settings(is_active);

-- Insert default settings
INSERT INTO postprocessing_settings (
    enable_smoothing,
    max_change_percent,
    enable_business_rules,
    enable_weekend_adjustment,
    enable_holiday_adjustment,
    enable_anomaly_detection,
    anomaly_threshold,
    enable_confidence,
    confidence_level,
    is_active
) VALUES (
    TRUE,    -- enable_smoothing
    50.0,    -- max_change_percent
    TRUE,    -- enable_business_rules
    TRUE,    -- enable_weekend_adjustment
    TRUE,    -- enable_holiday_adjustment
    TRUE,    -- enable_anomaly_detection
    3.0,     -- anomaly_threshold
    TRUE,    -- enable_confidence
    0.95,    -- confidence_level
    TRUE     -- is_active
) ON CONFLICT DO NOTHING;

-- Add comment
COMMENT ON TABLE postprocessing_settings IS 'User-configurable settings for forecast post-processing';