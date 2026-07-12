from telegram import Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.services.user_service import UserService
from app.services.client_service import ClientService

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    db = SessionLocal()

try:
    user = UserService.register(
        db,
        update.effective_user,
    )

    ClientService.create_if_not_exists(
        db,
        user.id,
    )

finally:
    db.close()

await update.message.reply_text(
    f"👋 Добро пожаловать, {update.effective_user.first_name}!",
    reply_markup=main_menu(),
)

from telegram.ext import CommandHandler
start_handler = CommandHandler("start", start)
