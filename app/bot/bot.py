from telegram.ext import Application

from app.config.settings import settings

from app.handlers.start import start_handler
from app.handlers.menu import menu_handler
from app.handlers.booking import booking_handler
from app.handlers.profile import profile_handler
from app.handlers.search import search_handler
from app.handlers.settings import settings_handler

application = (
    Application.builder()
    .token(settings.BOT_TOKEN)
    .build()
)

# Регистрация обработчиков
application.add_handler(start_handler)
application.add_handler(menu_handler)
application.add_handler(booking_handler)
application.add_handler(profile_handler)
application.add_handler(search_handler)
application.add_handler(settings_handler)
