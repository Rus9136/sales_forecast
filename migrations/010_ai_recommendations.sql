-- Migration: AI Recommendations subsystem
-- Date: 2026-04-30
-- Description: Tables for storing AI-driven analysis of departments
--   - ai_recommendations: results of multi-agent analysis
--   - ai_prompt_logs: per-agent prompt/response audit log
--   - ai_prompts: editable prompt templates per agent
--
-- Migrated from hr-miniapp Node.js project. Replaces MCP API with direct DB access.

CREATE TABLE IF NOT EXISTS ai_recommendations (
    id              SERIAL PRIMARY KEY,
    department_id   UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    date_start      DATE NOT NULL,
    date_end        DATE NOT NULL,
    mcp_response    JSONB NOT NULL,
    agent_results   JSONB NOT NULL DEFAULT '{}'::jsonb,
    provider        VARCHAR(50) NOT NULL DEFAULT 'claude',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ai_recommendations_department_id
    ON ai_recommendations(department_id);
CREATE INDEX IF NOT EXISTS ix_ai_recommendations_created_at
    ON ai_recommendations(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_recommendations_date_range
    ON ai_recommendations(date_start, date_end);

COMMENT ON TABLE ai_recommendations IS
    'Stored multi-agent AI analysis runs per department/period';
COMMENT ON COLUMN ai_recommendations.mcp_response IS
    'Raw input data collected from local DB (forecast/sales/department_info). Named mcp_response for compatibility with hr-miniapp schema.';
COMMENT ON COLUMN ai_recommendations.agent_results IS
    'JSON map: { agent_name: text_result }';
COMMENT ON COLUMN ai_recommendations.provider IS
    'AI provider used: claude | openai | gemini';


CREATE TABLE IF NOT EXISTS ai_prompt_logs (
    id                  SERIAL PRIMARY KEY,
    analysis_id         INTEGER REFERENCES ai_recommendations(id) ON DELETE CASCADE,
    agent_name          VARCHAR(100) NOT NULL,
    provider            VARCHAR(50) NOT NULL,
    full_prompt         TEXT NOT NULL,
    prompt_length       INTEGER NOT NULL,
    system_prompt       TEXT,
    response_text       TEXT,
    response_length     INTEGER,
    request_timestamp   TIMESTAMP NOT NULL DEFAULT NOW(),
    response_timestamp  TIMESTAMP,
    success             BOOLEAN NOT NULL DEFAULT FALSE,
    error_message       TEXT,
    tokens_used         INTEGER
);

CREATE INDEX IF NOT EXISTS ix_ai_prompt_logs_analysis_id
    ON ai_prompt_logs(analysis_id);
CREATE INDEX IF NOT EXISTS ix_ai_prompt_logs_agent_name
    ON ai_prompt_logs(agent_name);
CREATE INDEX IF NOT EXISTS ix_ai_prompt_logs_request_timestamp
    ON ai_prompt_logs(request_timestamp DESC);

COMMENT ON TABLE ai_prompt_logs IS
    'Per-agent prompt/response audit log. One row per agent invocation.';


CREATE TABLE IF NOT EXISTS ai_prompts (
    agent_name   VARCHAR(50) PRIMARY KEY,
    prompt_text  TEXT NOT NULL,
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ai_prompts IS
    'Editable system prompt templates for each agent. Falls back to hardcoded defaults if missing.';
