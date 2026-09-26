from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/oshi_schedule.db"
    app_base_url: str = "http://127.0.0.1:8000"
    x_bearer_token: SecretStr | None = None
    x_api_base_url: str = "https://api.x.com"
    x_api_timeout_seconds: float = Field(default=10, gt=0, le=120)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
