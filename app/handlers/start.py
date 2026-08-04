from sqlalchemy import select
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.salon import Salon
from app.services.user_service import UserService


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.effective_user is None or update.message is None:
        return

    db = SessionLocal()

    try:
        user = UserService.register(
            db,
            update.effective_user,
        )

        salon_id = db.scalar(
            select(Salon.id)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .limit(1)
        )

        await update.message.reply_text(
            (
                f"👋 Добро пожаловать, "
                f"{user.first_name}!"
            ),
            reply_markup=main_menu(
                role=user.role,
                telegram_id=user.telegram_id,
                has_salon=salon_id is not None,
            ),
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


start_handler = CommandHandler(
    "start",
    start,
)
