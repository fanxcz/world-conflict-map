from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "World Conflict Map"
    app_version: str = "1.0.0"
    database_url: str = "sqlite:///./wcm.db"
    jwt_secret: str = "change-me-in-production-use-long-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    admin_email: str = "admin@wcm.local"
    admin_password: str = "Admin123!"
    rate_limit_per_minute: int = 120
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        extra = "ignore"

    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
