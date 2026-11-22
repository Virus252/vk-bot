import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import sys
import signal
import logging
import time
import asyncio
from config import VK_TOKEN, VK_GROUP_ID
from database import db
from handlers import handle_message

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

if not VK_TOKEN:
    logger.critical("❌ Токен VK_TOKEN не найден в .env файле!")
    sys.exit(1)

try:
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, group_id=VK_GROUP_ID)
    logger.info("✅ VK API инициализирован.")
except Exception as e:
    logger.critical(f"❌ Ошибка VK API: {e}")
    sys.exit(1)


def graceful_shutdown(signum, frame):
    logger.info("⛔ Остановка...")
    time.sleep(1)
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)


async def main():
    try:
        await db.init()
        await db.start_backup_scheduler()
        logger.info("🤖 Бот запущен.")

        while True:
            try:
                for event in longpoll.listen():
                    if event.type == VkBotEventType.MESSAGE_NEW:
                        try:
                            await handle_message(event, vk)
                        except Exception as e:
                            logger.error(f"⚠️ Ошибка обработки сообщения: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"⚠️ Ошибка LongPoll: {e}. Переподключение через 5с...")
                await asyncio.sleep(5)
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
    