import re
import time
import logging
from typing import Dict, Set
from collections import defaultdict
from config import VK_GROUP_ID, VALID_NOTE_CHARS

logger = logging.getLogger(__name__)

# Rate limiting
rate_limits: Dict[int, list] = defaultdict(list)

def check_rate_limit(user_id: int) -> bool:
    """Проверка rate limit"""
    from config import RATE_LIMIT_MESSAGES, RATE_LIMIT_PERIOD
    
    current_time = time.time()
    user_requests = rate_limits[user_id]
    
    # Удаляем старые запросы
    user_requests[:] = [t for t in user_requests if current_time - t < RATE_LIMIT_PERIOD]
    
    if len(user_requests) >= RATE_LIMIT_MESSAGES:
        return False
    
    user_requests.append(current_time)
    return True

def validate_note_text(text: str) -> bool:
    """Валидация текста заметки"""
    if not text or len(text.strip()) == 0:
        return False
    
    # Проверяем на опасные символы
    for char in text:
        if char not in VALID_NOTE_CHARS and not char.isspace():
            logger.warning(f"Обнаружен подозрительный символ в заметке: {repr(char)}")
            return False
    
    return True

RE_MENTION = re.compile(r'\[club' + str(VK_GROUP_ID) + r'\|[^]]+\]')
RE_STATUS_CMD = re.compile(r'^статус$', re.IGNORECASE)

def is_bot_mentioned(text: str) -> bool:
    """Проверка упоминания бота"""
    return bool(RE_MENTION.search(text))

def extract_command(text: str) -> str:
    """Извлечение команды из текста"""
    return RE_MENTION.sub('', text).strip()

# Метрики
metrics: Dict[str, int] = defaultdict(int)

def increment_metric(metric_name: str):
    """Увеличение счётчика метрики"""
    metrics[metric_name] += 1

def get_metrics() -> Dict[str, int]:
    """Получение всех метрик"""
    return dict(metrics)

def log_metrics():
    """Логирование метрик"""
    if metrics:
        logger.info(f"📊 Метрики: {dict(metrics)}")