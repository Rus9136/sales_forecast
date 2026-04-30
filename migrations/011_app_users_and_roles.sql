-- Migration: UI authentication via phone-only login
-- Date: 2026-04-30
-- Description:
--   - app_role: editable roles with allowed_sections (JSONB list of section keys)
--   - app_user: phone-based UI users (no password yet — placeholder column)
--   - app_session: opaque session tokens stored server-side
--
-- Note: this layer is a UI-level access gate. Backend API endpoints continue
-- to use the existing API_TOKEN / api_keys auth. Only /api/auth/* and
-- /api/users/* endpoints require a session token.

CREATE TABLE IF NOT EXISTS app_role (
    code             VARCHAR(50) PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    allowed_sections JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_system        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE app_role IS 'UI roles with editable section visibility';
COMMENT ON COLUMN app_role.allowed_sections IS
    'JSON array of section keys, e.g. ["departments","sales.daily","users"]';
COMMENT ON COLUMN app_role.is_system IS
    'System roles cannot be deleted or renamed (admin/manager/accountant/viewer)';


CREATE TABLE IF NOT EXISTS app_user (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone           VARCHAR(20) UNIQUE NOT NULL,
    full_name       VARCHAR(255),
    role_code       VARCHAR(50) NOT NULL REFERENCES app_role(code) ON UPDATE CASCADE,
    password_hash   VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_app_user_role_code ON app_user(role_code);

COMMENT ON TABLE app_user IS 'UI users authenticating by phone number';
COMMENT ON COLUMN app_user.phone IS
    'Normalized phone digits-only with leading country code, e.g. 77001234567';
COMMENT ON COLUMN app_user.password_hash IS
    'Reserved for future password support — currently NULL (phone-only login)';


CREATE TABLE IF NOT EXISTS app_session (
    token       VARCHAR(64) PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_app_session_user_id ON app_session(user_id);
CREATE INDEX IF NOT EXISTS ix_app_session_expires_at ON app_session(expires_at);


-- ---------------------------------------------------------------------------
-- Seed default system roles (idempotent via ON CONFLICT)
-- ---------------------------------------------------------------------------
INSERT INTO app_role (code, name, allowed_sections, is_system)
VALUES
    (
        'admin',
        'Администратор',
        '["departments","employees","sales.daily","sales.hourly","sales.waiters","forecast.branches","forecast.comparison","bonus.calculations","bonus.schemes","bonus.manual-kpi","bonus.monthly-plans","ai.recommendations","sync","users","roles"]'::jsonb,
        TRUE
    ),
    (
        'manager',
        'Менеджер',
        '["departments","employees","sales.daily","sales.hourly","sales.waiters","forecast.branches","forecast.comparison","ai.recommendations","sync"]'::jsonb,
        TRUE
    ),
    (
        'accountant',
        'Бухгалтер',
        '["departments","employees","sales.daily","sales.waiters","bonus.calculations","bonus.schemes","bonus.manual-kpi","bonus.monthly-plans"]'::jsonb,
        TRUE
    ),
    (
        'viewer',
        'Наблюдатель',
        '["sales.daily","sales.hourly","forecast.branches","forecast.comparison"]'::jsonb,
        TRUE
    )
ON CONFLICT (code) DO NOTHING;
