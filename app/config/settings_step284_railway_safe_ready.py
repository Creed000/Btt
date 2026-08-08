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

        # Критично для Railway/.env.example:
        # OWNER_TELEGRAM_ID= и другие пустые optional
        # значения не должны превращаться в ошибку валидации.
        env_ignore_empty=True,
    )

    @property
    def admin_telegram_ids(self) -> set[int]:
        if not self.ADMIN_TELEGRAM_IDS:
            return set()

        return {
            int(value.strip())
            for value in self.ADMIN_TELEGRAM_IDS.split(",")
            if value.strip()
        }

    @property
    def all_platform_admin_ids(self) -> set[int]:
        result = set(
            self.admin_telegram_ids
        )

        if self.OWNER_TELEGRAM_ID is not None:
            result.add(
                self.OWNER_TELEGRAM_ID
            )

        return result

    def role_for_telegram_id(
        self,
        telegram_id: int,
    ) -> str | None:
        if telegram_id in self.all_platform_admin_ids:
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

        prefix, suffix = value.split(
            ":",
            1,
        )

        if (
            not prefix.isdigit()
            or not suffix
        ):
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

        if value.startswith(
            "postgres://"
        ):
            value = value.replace(
                "postgres://",
                "postgresql+psycopg://",
                1,
            )

        elif value.startswith(
            "postgresql://"
        ):
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
                "DATABASE_URL должен использовать "
                "PostgreSQL (psycopg) или SQLite."
            )

        return value

    @field_validator("APP_TIMEZONE")
    @classmethod
    def validate_timezone(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            return "Asia/Bishkek"

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(
                f"Неизвестный часовой пояс: {value}"
            ) from error

        return value

    @field_validator("OWNER_TELEGRAM_ID")
    @classmethod
    def validate_owner_telegram_id(
        cls,
        value: int | None,
    ) -> int | None:
        if value is None:
            return None

        if value <= 0:
            raise ValueError(
                "OWNER_TELEGRAM_ID должен быть "
                "положительным Telegram ID."
            )

        return value

    @field_validator("ADMIN_TELEGRAM_IDS")
    @classmethod
    def validate_admin_telegram_ids(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            return ""

        normalized: list[str] = []

        for raw_value in value.split(","):
            raw_value = raw_value.strip()

            if not raw_value:
                continue

            if not raw_value.isdigit():
                raise ValueError(
                    "ADMIN_TELEGRAM_IDS должен содержать "
                    "только Telegram ID через запятую."
                )

            telegram_id = int(
                raw_value
            )

            if telegram_id <= 0:
                raise ValueError(
                    "ADMIN_TELEGRAM_IDS содержит "
                    "некорректный Telegram ID."
                )

            normalized.append(
                str(telegram_id)
            )

        # Убираем дубли, сохраняя порядок.
        return ",".join(
            dict.fromkeys(
                normalized
            )
        )

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
                "SECRET_KEY должен содержать "
                "не менее 16 символов."
            )

        return value


settings = Settings()
