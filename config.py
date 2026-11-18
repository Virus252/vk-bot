import os

# ==========================================
# ПРОСТОЙ ПАРСЕР .env ФАЙЛА
# ==========================================
def load_env_file(env_path=".env"):
    """Читает .env файл и добавляет переменные в os.environ"""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                if key not in os.environ:
                    os.environ[key] = value


load_env_file()

# ==========================================
# VK API
# ==========================================
VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", 241749379))

# ==========================================
# Цитаты
# ==========================================
QUOTE_CHAT_ID = int(os.getenv("QUOTE_CHAT_ID", 2000000152))
QUOTE_INTERVAL_SECONDS = int(os.getenv("QUOTE_INTERVAL_SECONDS", 1200))

# ==========================================
# Лимиты
# ==========================================
MAX_NOTES_PER_USER = int(os.getenv("MAX_NOTES_PER_USER", 100))
MAX_GLOBAL_NOTES = int(os.getenv("MAX_GLOBAL_NOTES", 500))
MAX_NOTE_LENGTH = int(os.getenv("MAX_NOTE_LENGTH", 500))
MAX_FWD_MESSAGES = int(os.getenv("MAX_FWD_MESSAGES", 30))
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", 5000))
STATUS_WAIT_TIMEOUT = int(os.getenv("STATUS_WAIT_TIMEOUT", 15))
NOTES_PER_PAGE = int(os.getenv("NOTES_PER_PAGE", 20))

# ==========================================
# База данных
# ==========================================
DB_PATH = os.getenv("DB_PATH", "bot_data.db")
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", 24))

# ==========================================
# Rate limiting
# ==========================================
RATE_LIMIT_MESSAGES = 5   # Макс сообщений за период
RATE_LIMIT_PERIOD = 10    # Период в секундах

# ==========================================
# Валидация
# ==========================================
VALID_NOTE_CHARS = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
                       "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
                       "abcdefghijklmnopqrstuvwxyz"
                       "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                       "0123456789 .,!?-_:;()[]{}@#$%^&*+=/\"'<>|~`")

# ==========================================
# Владелец бота (автоматически Глава гильдии)
# ==========================================
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))

# ==========================================
# СИСТЕМА РОЛЕЙ (Гильдия)
# ==========================================
ROLE_HIERARCHY = {
    "GuildMaster": 5,    # Глава гильдии
    "Deputy": 4,         # Зам главы
    "Cardinal": 3,       # Кардинал
    "Captain": 3,        # Капитан
    "Lieutenant": 2,     # Лейтенант
    "Private": 1         # Рядовой
}

ROLE_NAMES_RU = {
    "GuildMaster": "👑 Глава гильдии",
    "Deputy": "⚔️ Зам главы",
    "Cardinal": "📿 Кардинал",
    "Captain": "🛡️ Капитан",
    "Lieutenant": "🎖️ Лейтенант",
    "Private": "🪖 Рядовой"
}

ROLE_NAMES_FROM_RU = {
    "глава": "GuildMaster",
    "глава гильдии": "GuildMaster",
    "зам": "Deputy",
    "зам главы": "Deputy",
    "кардинал": "Cardinal",
    "капитан": "Captain",
    "лейтенант": "Lieutenant",
    "рядовой": "Private",
    # английские варианты
    "guildmaster": "GuildMaster",
    "deputy": "Deputy",
    "cardinal": "Cardinal",
    "captain": "Captain",
    "lieutenant": "Lieutenant",
    "private": "Private"
}

# ==========================================
# МУТ
# ==========================================
MUTE_ALLOWED_ROLES = ["GuildMaster", "Deputy", "Cardinal"]
DEFAULT_MUTE_DURATION = int(os.getenv("DEFAULT_MUTE_DURATION", 3600))  # 1 час