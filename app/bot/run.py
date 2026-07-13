from app.bot.bot import application
from app.database.init_db import init_db

if __name__ == "__main__":
    init_db()
    application.run_polling()
