from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RPGForge API"
    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(
        default="postgresql+psycopg://rpg:rpg@postgres:5432/rpgforge",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="", alias="DEEPSEEK_BASE_URL")
    deepseek_flash_model: str = Field(
        default="deepseek-v4-flash",
        alias="DEEPSEEK_FLASH_MODEL",
    )
    deepseek_pro_model: str = Field(
        default="deepseek-v4-pro",
        alias="DEEPSEEK_PRO_MODEL",
    )
    settings_admin_token: str = Field(default="", alias="SETTINGS_ADMIN_TOKEN")
    mimo_api_key: str = Field(default="", alias="MIMO_API_KEY")
    audio_storage_path: str = Field(default="/data/audio", alias="AUDIO_STORAGE_PATH")
    portrait_storage_path: str = Field(default="/data/portraits", alias="PORTRAIT_STORAGE_PATH")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
