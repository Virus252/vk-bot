import os
from dotenv import load_dotenv

load_dotenv()

# VK API
VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", 241749379))

# Цитаты
QUOTE_CHAT_ID = int(os.getenv("QUOTE_CHAT_ID", 2000000152))
QUOTE_INTERVAL_SECONDS = int(os.getenv("QUOTE_INTERVAL_SECONDS", 1200))

# Лимиты
MAX_NOTES_PER_USER = int(os.getenv("MAX_NOTES_PER_USER", 100))
MAX_NOTE_LENGTH = int(os.getenv("MAX_NOTE_LENGTH", 500))
MAX_FWD_MESSAGES = int(os.getenv("MAX_FWD_MESSAGES", 30))
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", 5000))
STATUS_WAIT_TIMEOUT = int(os.getenv("STATUS_WAIT_TIMEOUT", 15))

# База данных
DB_PATH = os.getenv("DB_PATH", "bot_data.db")
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", 24))

# Rate limiting
RATE_LIMIT_MESSAGES = 5  # Макс сообщений за период
RATE_LIMIT_PERIOD = 10   # Период в секундах

# Валидация
VALID_NOTE_CHARS = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
                       "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
                       "abcdefghijklmnopqrstuvwxyz"
                       "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                       "0123456789 .,!?-_:;()[]{}@#$%^&*+=/\\\"'<>|~`")