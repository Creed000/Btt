from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.user import User


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str = "Главное меню:",
) -> None:
    """
    Показывает главное меню с учётом роли и Telegram ID.

    Используйте эту функцию вместо прямого вызова main_menu(),
    когда пользователь нажимает «⬅️ Назад».
    """
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

        await update.message.reply_text(
            text,
            reply_markup=main_menu(
                role=role,
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
