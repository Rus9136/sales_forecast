from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://sales_user:sales_password@localhost:5435/sales_forecast"
    API_BASE_URL: str = "http://tco.aqnietgroup.com:5555/v1"
    PROJECT_NAME: str = "Sales Forecast API"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    POSTGRES_USER: str = "sales_user"
    POSTGRES_PASSWORD: str = "sales_password"
    POSTGRES_DB: str = "sales_forecast"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5435"
    
    class Config:
        env_file = ".env"


settings = Settings()