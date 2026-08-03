import asyncio
import logging

from telegram.error import NetworkError, TimedOut

from app.bot.bot import application


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    retry_delay = 5

    while True:
        try:
            logger.info("Запуск Telegram-бота...")

            await application.initialize()
            await application.start()
            await application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=None,
            )

            logger.info("Telegram-бот успешно запущен")

            while True:
                await asyncio.sleep(3600)

        except (NetworkError, TimedOut) as error:
            logger.warning(
                "Ошибка соединения с Telegram: %s. Повтор через %s секунд.",
                error,
                retry_delay,
            )

        except Exception:
            logger.exception("Критическая ошибка Telegram-бота")

        finally:
            try:
                if application.updater and application.updater.running:
                    await application.updater.stop()

                if application.running:
                    await application.stop()

                await application.shutdown()

            except Exception:
                logger.exception("Ошибка при остановке Telegram-бота")

        await asyncio.sleep(retry_delay)


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Telegram-бот остановлен")
