from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str = "Главное меню:",
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

        role = (
            user.role
            if user is not None
            else None
        )

        has_salon = False
        has_master = False

        if user is not None:
            salon_id = db.scalar(
                select(Salon.id)
                .where(
                    Salon.owner_id == user.id,
                    Salon.is_active.is_(True),
                )
                .limit(1)
            )

            master_id = db.scalar(
                select(Master.id)
                .where(
                    Master.user_id == user.id
                )
                .limit(1)
            )

            has_salon = salon_id is not None
            has_master = master_id is not None

        await update.message.reply_text(
            text,
            reply_markup=main_menu(
                role=role,
                telegram_id=update.effective_user.id,
                has_salon=has_salon,
                has_master=has_master,
            ),
        )

    finally:
        db.close()
