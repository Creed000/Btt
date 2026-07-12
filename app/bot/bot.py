from telegram.ext import Application

from app.config.settings import settings

application = (
    Application.builder()
    .token(settings.BOT_TOKEN)
    .build()
)
