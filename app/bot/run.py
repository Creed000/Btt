from app.database.init_db import init_db
from app.bot.bot import application

if __name__ == "__main__":
    init_db()          # создаёт все таблицы
    application.run_polling()
