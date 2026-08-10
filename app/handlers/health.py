import logging

from sqlalchemy import inspect, select, text
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.session import SessionLocal, engine
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.access_control import can_manage_platform
from app.services.timezone import APP_TIMEZONE, local_naive_now


logger = logging.getLogger(__name__)


REQUIRED_REMINDER_COLUMNS = {
    "reminder_24h_client_sent",
    "reminder_24h_master_sent",
    "reminder_2h_client_sent",
    "reminder_2h_master_sent",
    "reminder_24h_client_claimed_at",
    "reminder_24h_master_claimed_at",
    "reminder_2h_client_claimed_at",
    "reminder_2h_master_claimed_at",
}


def _job_status(
    context: ContextTypes.DEFAULT_TYPE,
    name: str,
) -> str:
    job_queue = context.application.job_queue

    if job_queue is None:
        return "❌ JobQueue недоступна"

    try:
        jobs = job_queue.get_jobs_by_name(
            name
        )
    except Exception:
        logger.exception(
            "Не удалось проверить job %s",
            name,
        )
        return "❌ ошибка проверки"

    if not jobs:
        return "❌ не зарегистрирована"

    enabled_jobs = [
        job
        for job in jobs
        if getattr(
            job,
            "enabled",
            True,
        )
    ]

    if not enabled_jobs:
        return (
            "⚠️ зарегистрирована, "
            "но выключена"
        )

    return (
        f"✅ активна ({len(enabled_jobs)})"
    )


def _table_status(
    table_name: str,
) -> str:
    try:
        inspector = inspect(engine)

        if (
            table_name
            in inspector.get_table_names()
        ):
            return "✅ есть"

        return "❌ отсутствует"

    except Exception:
        logger.exception(
            "Не удалось проверить таблицу %s",
            table_name,
        )
        return "❌ ошибка проверки"


def _reminder_schema_status() -> str:
    try:
        inspector = inspect(engine)

        if (
            "bookings"
            not in inspector.get_table_names()
        ):
            return (
                "❌ таблица bookings отсутствует"
            )

        columns = {
            column["name"]
            for column in inspector.get_columns(
                "bookings"
            )
        }

        missing = (
            REQUIRED_REMINDER_COLUMNS
            - columns
        )

        if not missing:
            return "✅ актуальна"

        return (
            "⚠️ не хватает: "
            + ", ".join(
                sorted(missing)
            )
        )

    except Exception:
        logger.exception(
            "Не удалось проверить "
            "схему reminders"
        )
        return "❌ ошибка проверки"


def _user_main_menu(
    db,
    user: User | None,
    telegram_id: int,
):
    if user is None:
        return main_menu(
            telegram_id=telegram_id,
        )

    has_salon = (
        db.scalar(
            select(Salon.id)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .limit(1)
        )
        is not None
    )

    has_master = (
        db.scalar(
            select(Master.id)
            .where(
                Master.user_id == user.id
            )
            .limit(1)
        )
        is not None
    )

    return main_menu(
        role=user.role,
        telegram_id=telegram_id,
        has_salon=has_salon,
        has_master=has_master,
    )


async def health_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id
                == update.effective_user.id
            )
        )

        if not can_manage_platform(
            user
        ):
            await update.message.reply_text(
                "⛔ Команда /health доступна "
                "только администратору "
                "SaaS-платформы.",
                reply_markup=_user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        database_status = "❌ недоступна"

        try:
            db.execute(
                text("SELECT 1")
            )
            database_status = "✅ доступна"
        except Exception:
            logger.exception(
                "Ошибка проверки подключения к БД"
            )
            db.rollback()

        job_queue_status = (
            "✅ доступна"
            if context.application.job_queue
            is not None
            else "❌ недоступна"
        )

        reminder_job_status = _job_status(
            context,
            "booking_reminders",
        )

        subscription_job_status = _job_status(
            context,
            "subscription_maintenance",
        )

        invite_job_status = _job_status(
            context,
            "master_invite_maintenance",
        )

        reminder_schema = (
            _reminder_schema_status()
        )

        plan_requests_table = _table_status(
            "subscription_plan_requests"
        )

        master_invites_table = _table_status(
            "master_salon_invites"
        )

        now = local_naive_now()

        await update.message.reply_text(
            "🩺 GlowFlow — состояние системы\n\n"
            "🤖 Telegram-бот: ✅ работает\n"
            f"🗄 PostgreSQL: {database_status}\n"
            f"⚙️ JobQueue: {job_queue_status}\n\n"
            "Фоновые задачи:\n"
            f"⏰ Напоминания: "
            f"{reminder_job_status}\n"
            f"💳 Подписки: "
            f"{subscription_job_status}\n"
            f"📨 Приглашения мастеров: "
            f"{invite_job_status}\n\n"
            "Схема БД:\n"
            f"🔔 Reminder-схема: "
            f"{reminder_schema}\n"
            f"💳 Запросы тарифов: "
            f"{plan_requests_table}\n"
            f"🤝 Приглашения мастеров: "
            f"{master_invites_table}\n\n"
            f"🌍 Часовой пояс: "
            f"{APP_TIMEZONE}\n"
            "🕒 Локальное время: "
            f"{now.strftime('%d.%m.%Y %H:%M:%S')}",
            reply_markup=_user_main_menu(
                db,
                user,
                update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()

        logger.exception(
            "Ошибка /health"
        )

        await update.message.reply_text(
            "❌ Не удалось выполнить "
            "полную проверку системы.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


health_handler = CommandHandler(
    "health",
    health_check,
)
