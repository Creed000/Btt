from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.services.subscription_access import (
    salon_has_active_access,
)


async def search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    text = (update.message.text or "").strip()

    normalized = (
        text.replace("🔍", "")
        .replace("🔎", "")
        .strip()
    )

    if normalized != "Найти мастера":
        return

    db = SessionLocal()

    try:
        masters = list(
            db.scalars(
                select(Master)
                .options(
                    joinedload(Master.user),
                    joinedload(Master.city),
                    joinedload(Master.salon),
                    joinedload(Master.branch),
                    selectinload(Master.services),
                )
                .where(
                    Master.booking_enabled.is_(True),
                    Master.is_verified.is_(True),
                )
                .order_by(
                    Master.rating.desc(),
                    Master.id.asc(),
                )
                .limit(50)
            ).unique().all()
        )

        available_masters: list[Master] = []

        for master in masters:
            if master.user is None or not master.user.is_active:
                continue

            if master.city is None or not master.city.is_active:
                continue

            if not master.services:
                continue

            if master.salon is not None:
                allowed, _ = salon_has_active_access(
                    master.salon
                )

                if not allowed:
                    continue

            available_masters.append(master)

        if not available_masters:
            await update.message.reply_text(
                "🔎 Сейчас доступных мастеров нет.\n\n"
                "Попробуйте позже или выберите другой город.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        lines = [
            "🔎 Каталог мастеров",
            "",
        ]

        for master in available_masters[:20]:
            master_name = (
                master.user.first_name
                or "Мастер"
            )

            city_name = (
                master.city.name
                if master.city is not None
                else "Город не указан"
            )

            workplace = "Самостоятельный мастер"

            if master.salon is not None:
                workplace = master.salon.name

                if master.branch is not None:
                    workplace += (
                        f" · {master.branch.name}"
                    )

            services_text = ", ".join(
                (
                    f"{service.title} — "
                    f"{service.price} сом"
                )
                for service in master.services[:5]
            )

            if len(master.services) > 5:
                services_text += ", …"

            description = (
                master.description.strip()
                if master.description
                else "Описание пока не добавлено."
            )

            lines.extend(
                [
                    f"👤 {master_name}",
                    f"🏙 {city_name}",
                    f"🏢 {workplace}",
                    f"⭐ Рейтинг: {master.rating:.1f}",
                    f"💼 {services_text}",
                    f"📝 {description}",
                    "",
                ]
            )

        lines.append(
            "Для записи нажмите «📅 Записаться» "
            "в главном меню."
        )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить каталог мастеров.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


search_handler = MessageHandler(
    filters.Regex(
        r"^(🔍|🔎)?\s*Найти мастера$"
    ),
    search,
)
