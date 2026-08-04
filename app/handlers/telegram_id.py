from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


async def show_telegram_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    user = update.effective_user

    username = (
        f"@{user.username}"
        if user.username
        else "не указан"
    )

    await update.message.reply_text(
        "🆔 Ваши данные Telegram\n\n"
        f"Telegram ID: `{user.id}`\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Username: {username}\n\n"
        "Скопируйте Telegram ID и добавьте его в Railway:\n"
        "`OWNER_TELEGRAM_ID=ваш_id`",
        parse_mode="Markdown",
    )


telegram_id_handler = CommandHandler(
    "id",
    show_telegram_id,
)
