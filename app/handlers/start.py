from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.services.user_service import UserService


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = UserService.register(
            db,
            update.effective_user,
        )

        role = user.role

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось запустить бота. Попробуйте ещё раз."
        )
        return

    finally:
        db.close()

    await update.message.reply_text(
        f"👋 Добро пожаловать, {update.effective_user.first_name}!\n\n"
        "Выберите нужное действие:",
        reply_markup=main_menu(role=role),
    )


start_handler = CommandHandler(
    "start",
    start,
)
