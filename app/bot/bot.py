from telegram.ext import Application

from app.config.settings import settings

from app.handlers.start import start_handler
from app.handlers.profile import profile_handler
from app.handlers.menu import menu_handler
from app.handlers.booking import booking_handler


application = (
    Application.builder()
    .token(settings.BOT_TOKEN)
    .build()
)

# Команды
application.add_handler(start_handler)
application.add_handler(profile_handler)

# Главное меню
application.add_handler(menu_handler)

# Запись к мастеру
application.add_handler(booking_handler)
