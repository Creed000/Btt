from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str

    REDIS_URL: str | None = None
    SECRET_KEY: str = "change-me-before-production"

    DEBUG: bool = False
    APP_TIMEZONE: str = "Asia/Bishkek"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("BOT_TOKEN")
    @classmethod
    def validate_bot_token(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "BOT_TOKEN не может быть пустым."
            )

        if ":" not in value:
            raise ValueError(
                "BOT_TOKEN имеет неверный формат."
            )

        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "DATABASE_URL не может быть пустым."
            )

        if value.startswith("postgres://"):
            value = value.replace(
                "postgres://",
                "postgresql+psycopg://",
                1,
            )
        elif value.startswith("postgresql://"):
            value = value.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )

        supported_prefixes = (
            "postgresql+psycopg://",
            "sqlite:///",
        )

        if not value.startswith(
            supported_prefixes
        ):
            raise ValueError(
                "DATABASE_URL должен использовать PostgreSQL "
                "или SQLite."
            )

        return value

    @field_validator("APP_TIMEZONE")
    @classmethod
    def validate_timezone(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(
                f"Неизвестный часовой пояс: {value}"
            ) from error

        return value

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if len(value) < 16:
            raise ValueError(
                "SECRET_KEY должен содержать не менее 16 символов."
            )

        return value


settings = Settings()
