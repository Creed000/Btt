from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.keyboards.master import master_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.master_catalog import (
    available_masters_query,
)


async def search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    text = (
        update.message.text or ""
    ).strip()

    normalized = (
        text.replace("🔍", "")
        .replace("🔎", "")
        .strip()
    )

    if normalized != "Найти мастера":
        return

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id
                == update.effective_user.id
            )
        )

        masters = list(
            db.scalars(
                available_masters_query()
            ).unique().all()
        )

        if not masters:
            has_salon = False
            has_master = False

            if user is not None:
                has_salon = (
                    db.scalar(
                        select(Salon.id)
                        .where(
                            Salon.owner_id
                            == user.id,
                            Salon.is_active.is_(
                                True
                            ),
                        )
                        .limit(1)
                    )
                    is not None
                )

                has_master = (
                    db.scalar(
                        select(Master.id)
                        .where(
                            Master.user_id
                            == user.id
                        )
                        .limit(1)
                    )
                    is not None
                )

            await update.message.reply_text(
                "🔎 Поиск мастеров\n\n"
                "Сейчас нет мастеров, доступных "
                "для новой записи.",
                reply_markup=main_menu(
                    role=(
                        user.role
                        if user
                        else None
                    ),
                    telegram_id=(
                        update.effective_user.id
                    ),
                    has_salon=has_salon,
                    has_master=has_master,
                ),
            )
            return

        lines = [
            "🔎 Доступные мастера",
            "",
            f"Найдено: {len(masters)}",
            "",
        ]

        for master in masters[:20]:
            name = (
                master.user.first_name
                if master.user
                and master.user.first_name
                else "Без имени"
            )

            city = (
                master.city.name
                if master.city
                else "—"
            )

            place = (
                master.salon.name
                if master.salon
                else "Самостоятельный мастер"
            )

            services = [
                service.title
                for service in master.services[:3]
            ]

            services_text = (
                ", ".join(services)
                if services
                else "—"
            )

            lines.extend(
                [
                    f"👤 {name} · ⭐ {master.rating:.1f}",
                    f"🏙 {city} · {place}",
                    f"💼 {services_text}",
                    "",
                ]
            )

        if len(masters) > 20:
            lines.append(
                "Показаны первые 20 мастеров."
            )

        lines.append(
            "Выберите мастера кнопкой ниже."
        )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=master_menu(),
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
        r"^[🔍🔎]?\s*Найти мастера$"
    ),
    search,
)
