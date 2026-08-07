from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.access_control import (
    is_platform_admin,
)


async def show_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        role = user.role if user is not None else None
        has_salon = False
        has_master_profile = False

        if user is not None:
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

            has_master_profile = (
                db.scalar(
                    select(Master.id)
                    .where(
                        Master.user_id == user.id
                    )
                    .limit(1)
                )
                is not None
            )

        lines = [
            "ℹ️ Помощь GlowFlow",
            "",
            "Для клиента:",
            "📅 Записаться — выбрать город, категорию, мастера, услугу, дату и время.",
            "🔍 Найти мастера — открыть каталог доступных мастеров.",
            "👤 Личный кабинет — посмотреть свои записи и отменить будущую запись.",
            "⚙️ Настройки — язык, часовой пояс и уведомления.",
        ]

        if has_master_profile or role == "master":
            lines.extend(
                [
                    "",
                    "Для мастера:",
                    "💼 Стать мастером — открыть или создать профиль мастера.",
                    "📅 Записи мастера — подтверждать, отменять и завершать записи.",
                    "🛠 Услуги — добавлять и управлять услугами.",
                    "🗓 Расписание — настроить рабочие дни и часы.",
                    "🏖 Выходные — добавить нерабочие даты.",
                    "⛔ Блокировки времени — закрыть отдельные интервалы.",
                ]
            )

        if has_salon or role == "owner":
            lines.extend(
                [
                    "",
                    "Для владельца салона:",
                    "🏢 Кабинет салона — профиль, тариф и управление салоном.",
                    "🏬 Филиалы — создавать филиалы.",
                    "👥 Мастера салона — приглашать и назначать по филиалам.",
                    "💳 Тариф и подписка — посмотреть текущий план и ограничения.",
                ]
            )

        if is_platform_admin(update.effective_user.id):
            lines.extend(
                [
                    "",
                    "Для администратора SaaS:",
                    "👑 Админ-панель — пользователи, мастера, записи и статистика.",
                    "💳 Подписки салонов — активировать и отключать тарифы.",
                    "/health — проверить PostgreSQL и фоновые задачи.",
                    "/id — показать Telegram ID.",
                ]
            )

        lines.extend(
            [
                "",
                "Если меню потерялось — отправьте /start.",
            ]
        )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=main_menu(
                role=role,
                telegram_id=update.effective_user.id,
                has_salon=has_salon,
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось открыть раздел помощи. "
            "Отправьте /start и попробуйте снова.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
