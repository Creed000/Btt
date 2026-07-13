from telegram.ext import Application

from app.config.settings import settings

from app.handlers.start import start_handler
from app.handlers.menu import menu_handler

application = (
    Application.builder()
    .token(settings.BOT_TOKEN)
    .build()
)

application.add_handler(start_handler)
application.add_handler(menu_handler)
