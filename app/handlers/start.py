from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
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

        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!",
            reply_markup=main_menu(
                role=user.role,
                telegram_id=user.telegram_id,
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
