from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    DEBUG: bool = True

    # Telegram ID владельца SaaS.
    # Добавляется в Railway Variables.
    ADMIN_TELEGRAM_ID: int | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()

settings.DATABASE_URL = (
    settings.DATABASE_URL
    .replace("postgres://", "postgresql+psycopg://")
    .replace("postgresql://", "postgresql+psycopg://")
)
