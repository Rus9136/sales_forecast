from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/sales_forecast"
    API_BASE_URL: str = "http://tco.aqnietgroup.com:5555/v1"
    PROJECT_NAME: str = "Sales Forecast API"
    VERSION: str = "0.1.0"
    DEBUG: bool = False

    API_TOKEN: str = ""

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "sales_forecast"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"

    IIKO_LOGIN: str = ""
    IIKO_PASSWORD: str = ""

    IIKO_DOMAINS: str = "https://sandy-co-co.iiko.it,https://madlen-group-so.iiko.it"

    ALLOWED_ORIGINS: str = "https://aqniet.site"
    LOG_LEVEL: str = "INFO"

    # AI Recommendations subsystem
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_API_KEY_PAYROLL: str = ""
    ANTHROPIC_API_KEY_STAFFING: str = ""
    ANTHROPIC_API_KEY_NARRATIVE: str = ""
    ANTHROPIC_API_KEY_REPUTATION: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # UI auth bootstrap (creates first admin if none exists)
    BOOTSTRAP_ADMIN_PHONE: str = ""
    BOOTSTRAP_ADMIN_NAME: str = "Администратор"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()