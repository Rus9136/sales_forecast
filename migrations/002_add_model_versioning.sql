-- Migration: Add model versioning and monitoring tables
-- Date: 2025-06-30

-- Table for storing model versions with metadata
CREATE TABLE IF NOT EXISTS model_versions (
    id SERIAL PRIMARY KEY,
    version_id VARCHAR(50) UNIQUE NOT NULL,
    model_type VARCHAR(50) DEFAULT 'LGBMRegressor',
    training_date TIMESTAMP NOT NULL,
    training_end_date TIMESTAMP,
    
    -- Training parameters
    n_features INTEGER NOT NULL,
    n_samples INTEGER NOT NULL,
    training_days INTEGER,
    outlier_method VARCHAR(50),
    hyperparameters JSONB,
    
    -- Model metrics
    train_mape FLOAT,
    validation_mape FLOAT,
    test_mape FLOAT,
    train_r2 FLOAT,
    validation_r2 FLOAT,
    test_r2 FLOAT,
    cv_mape FLOAT,
    cv_folds INTEGER,
    
    -- Feature importance
    top_features JSONB,
    feature_names TEXT[],
    
    -- Model file info
    model_path VARCHAR(255) NOT NULL,
    model_size_mb FLOAT,
    
    -- Status
    is_active BOOLEAN DEFAULT FALSE,
    status VARCHAR(50) DEFAULT 'trained', -- trained, deployed, archived, failed
    deployment_date TIMESTAMP,
    archived_date TIMESTAMP,
    
    -- Metadata
    created_by VARCHAR(50) DEFAULT 'system',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes
    INDEX idx_model_versions_version_id (version_id),
    INDEX idx_model_versions_is_active (is_active),
    INDEX idx_model_versions_training_date (training_date),
    INDEX idx_model_versions_status (status)
);

-- Table for model retraining history
CREATE TABLE IF NOT EXISTS model_retraining_log (
    id SERIAL PRIMARY KEY,
    retrain_date TIMESTAMP NOT NULL,
    trigger_type VARCHAR(50) NOT NULL, -- 'scheduled', 'manual', 'performance_degradation'
    trigger_details JSONB,
    
    -- Previous model info
    previous_version_id VARCHAR(50),
    previous_mape FLOAT,
    
    -- New model info
    new_version_id VARCHAR(50),
    new_mape FLOAT,
    
    -- Performance comparison
    mape_improvement FLOAT,
    decision VARCHAR(50), -- 'deployed', 'rejected', 'pending_review'
    decision_reason TEXT,
    
    -- Execution details
    execution_time_seconds INTEGER,
    status VARCHAR(50) DEFAULT 'completed', -- 'started', 'completed', 'failed'
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign keys
    FOREIGN KEY (previous_version_id) REFERENCES model_versions(version_id),
    FOREIGN KEY (new_version_id) REFERENCES model_versions(version_id),
    
    -- Indexes
    INDEX idx_retraining_log_date (retrain_date),
    INDEX idx_retraining_log_status (status)
);

-- Table for continuous model performance monitoring
CREATE TABLE IF NOT EXISTS model_performance_metrics (
    id SERIAL PRIMARY KEY,
    model_version_id VARCHAR(50) NOT NULL,
    metric_date DATE NOT NULL,
    
    -- Daily aggregated metrics
    daily_mape FLOAT,
    daily_mae FLOAT,
    daily_rmse FLOAT,
    daily_predictions_count INTEGER,
    
    -- Segment analysis
    worst_branch_mape FLOAT,
    worst_branch_id UUID,
    best_branch_mape FLOAT,
    best_branch_id UUID,
    
    -- Trend metrics (compared to last 7 days)
    mape_trend FLOAT, -- positive means getting worse
    prediction_bias FLOAT, -- average over/under prediction
    
    -- Alerts
    has_degradation_alert BOOLEAN DEFAULT FALSE,
    alert_details JSONB,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key
    FOREIGN KEY (model_version_id) REFERENCES model_versions(version_id),
    
    -- Indexes
    INDEX idx_performance_metrics_date (metric_date),
    INDEX idx_performance_metrics_version (model_version_id),
    INDEX idx_performance_metrics_alerts (has_degradation_alert),
    
    -- Unique constraint to ensure one metric per day per model
    UNIQUE(model_version_id, metric_date)
);

-- Add model_version_id to existing tables
ALTER TABLE forecasts 
ADD COLUMN IF NOT EXISTS model_version_id VARCHAR(50),
ADD FOREIGN KEY (model_version_id) REFERENCES model_versions(version_id);

ALTER TABLE forecast_accuracy_log
ADD COLUMN IF NOT EXISTS model_version_id VARCHAR(50),
ADD FOREIGN KEY (model_version_id) REFERENCES model_versions(version_id);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_forecasts_model_version ON forecasts(model_version_id);
CREATE INDEX IF NOT EXISTS idx_accuracy_log_model_version ON forecast_accuracy_log(model_version_id);

-- Comments
COMMENT ON TABLE model_versions IS 'Stores all trained model versions with their metadata and metrics';
COMMENT ON TABLE model_retraining_log IS 'Tracks all model retraining attempts and their outcomes';
COMMENT ON TABLE model_performance_metrics IS 'Daily aggregated performance metrics for active models';