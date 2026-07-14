from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    DEBUG: bool = True

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
