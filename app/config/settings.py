from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str

    REDIS_URL: str | None = None
    SECRET_KEY: str | None = None

    DEBUG: bool = False
    APP_TIMEZONE: str = "Asia/Bishkek"

    # Telegram ID главного владельца SaaS.
    OWNER_TELEGRAM_ID: int | None = None

    # Дополнительные администраторы через запятую:
    # 123456789,987654321
    ADMIN_TELEGRAM_IDS: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def admin_telegram_ids(self) -> set[int]:
        result: set[int] = set()

        for value in self.ADMIN_TELEGRAM_IDS.split(","):
            value = value.strip()

            if not value:
                continue

            try:
                result.add(int(value))
            except ValueError:
                continue

        return result

    def role_for_telegram_id(
        self,
        telegram_id: int,
    ) -> str | None:
        if (
            self.OWNER_TELEGRAM_ID is not None
            and telegram_id == self.OWNER_TELEGRAM_ID
        ):
            return "owner"

        if telegram_id in self.admin_telegram_ids:
            return "admin"

        return None

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
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        if len(value) < 16:
            raise ValueError(
                "SECRET_KEY должен содержать не менее 16 символов."
            )

        return value


settings = Settings()
