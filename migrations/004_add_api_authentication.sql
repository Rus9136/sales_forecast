-- Migration: Add API Key Authentication System
-- Version: 004
-- Date: 2025-06-30
-- Description: Create tables for API key management and usage tracking

-- Create API keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_id VARCHAR(32) UNIQUE NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    rate_limit_per_minute INTEGER DEFAULT 100 NOT NULL,
    rate_limit_per_hour INTEGER DEFAULT 1000 NOT NULL,
    rate_limit_per_day INTEGER DEFAULT 10000 NOT NULL,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    expires_at TIMESTAMP,
    created_by VARCHAR(100)
);

-- Create indexes for API keys
CREATE INDEX IF NOT EXISTS idx_api_keys_key_id ON api_keys(key_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_api_keys_expires_at ON api_keys(expires_at);

-- Create API key usage tracking table
CREATE TABLE IF NOT EXISTS api_key_usage (
    id SERIAL PRIMARY KEY,
    key_id VARCHAR(32) NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW() NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500)
);

-- Create indexes for API key usage (for rate limiting queries)
CREATE INDEX IF NOT EXISTS idx_api_key_usage_key_id ON api_key_usage(key_id);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_timestamp ON api_key_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_key_time ON api_key_usage(key_id, timestamp);

-- Add foreign key constraint (optional, depends on your preference)
-- ALTER TABLE api_key_usage ADD CONSTRAINT fk_api_key_usage_key_id 
--     FOREIGN KEY (key_id) REFERENCES api_keys(key_id) ON DELETE CASCADE;

-- Insert a default API key for testing (remove in production)
-- Key format: sf_test_key_example_secret
-- Full key: sf_dGVzdF9rZXlfZXhhbXBsZQ_dGVzdF9zZWNyZXRfZXhhbXBsZV9rZXk
INSERT INTO api_keys (
    key_id,
    key_hash,
    name,
    description,
    created_by,
    rate_limit_per_minute,
    rate_limit_per_hour,
    rate_limit_per_day
) VALUES (
    'dGVzdF9rZXlfZXhhbXBsZQ',
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', -- SHA256 of empty string (placeholder)
    'Development Test Key',
    'Default API key for development and testing purposes',
    'system',
    1000,
    10000,
    100000
) ON CONFLICT (key_id) DO NOTHING;

-- Create a view for API key statistics
CREATE OR REPLACE VIEW api_key_stats AS
SELECT 
    ak.key_id,
    ak.name,
    ak.is_active,
    ak.last_used_at,
    ak.created_at,
    ak.expires_at,
    COUNT(aku.id) as total_requests,
    COUNT(CASE WHEN aku.timestamp > NOW() - INTERVAL '1 hour' THEN 1 END) as requests_last_hour,
    COUNT(CASE WHEN aku.timestamp > NOW() - INTERVAL '1 day' THEN 1 END) as requests_last_day,
    ak.rate_limit_per_minute,
    ak.rate_limit_per_hour,
    ak.rate_limit_per_day
FROM api_keys ak
LEFT JOIN api_key_usage aku ON ak.key_id = aku.key_id
GROUP BY ak.id, ak.key_id, ak.name, ak.is_active, ak.last_used_at, ak.created_at, ak.expires_at,
         ak.rate_limit_per_minute, ak.rate_limit_per_hour, ak.rate_limit_per_day;

-- Add comments for documentation
COMMENT ON TABLE api_keys IS 'API keys for external access authentication';
COMMENT ON TABLE api_key_usage IS 'Log of API key usage for rate limiting and analytics';
COMMENT ON VIEW api_key_stats IS 'Aggregated statistics for API key usage';

COMMENT ON COLUMN api_keys.key_id IS 'Public identifier part of the API key';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA256 hash of the full API key for secure storage';
COMMENT ON COLUMN api_keys.rate_limit_per_minute IS 'Maximum requests allowed per minute';
COMMENT ON COLUMN api_keys.rate_limit_per_hour IS 'Maximum requests allowed per hour';
COMMENT ON COLUMN api_keys.rate_limit_per_day IS 'Maximum requests allowed per day';