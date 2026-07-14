from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from app.database.session import SessionLocal
from app.services.user_service import UserService
from app.keyboards.main import main_menu


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()

    try:
        UserService.register(db, update.effective_user)
    finally:
        db.close()

    await update.message.reply_text(
        f"👋 Добро пожаловать, {update.effective_user.first_name}!",
        reply_markup=main_menu(),
    )


start_handler = CommandHandler("start", start)
