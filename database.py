import aiosqlite
import asyncio
import logging
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional
from config import DB_PATH, BACKUP_INTERVAL_HOURS

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self.backup_interval = BACKUP_INTERVAL_HOURS * 3600
        self._backup_task = None
        
    async def init(self):
        """Инициализация БД и создание таблиц"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица заметок
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, id)
                )
            """)
            
            # Таблица профилей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            # Таблица ожидания статуса
            await db.execute("""
                CREATE TABLE IF NOT EXISTS waiting_status (
                    peer_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            
            # Индексы для быстрого поиска
            await db.execute("CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_profiles_user ON profiles(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_profiles_timestamp ON profiles(timestamp)")
            
            await db.commit()
            logger.info(f"✅ База данных инициализирована: {self.db_path}")
    
    async def start_backup_scheduler(self):
        """Запуск планировщика бэкапов"""
        self._backup_task = asyncio.create_task(self._backup_loop())
        logger.info(f"💾 Планировщик бэкапов запущен (интервал: {self.backup_interval}с)")
    
    async def _backup_loop(self):
        """Цикл создания бэкапов"""
        while True:
            try:
                await asyncio.sleep(self.backup_interval)
                await self.create_backup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле бэкапов: {e}")
    
    async def create_backup(self):
        """Создание бэкапа БД"""
        if not os.path.exists(self.db_path):
            return
        
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"bot_data_{timestamp}.db")
        
        try:
            # Копируем файл БД
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"💾 Бэкап создан: {backup_path}")
            
            # Удаляем старые бэкапы (оставляем последние 10)
            backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("bot_data_")])
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    old_path = os.path.join(backup_dir, old_backup)
                    os.remove(old_path)
                    logger.info(f"🗑 Удалён старый бэкап: {old_path}")
        except Exception as e:
            logger.error(f"Ошибка создания бэкапа: {e}")
    
    # === ЗАМЕТКИ ===
    
    async def add_note(self, user_id: int, text: str) -> Optional[Dict]:
        """Добавление заметки"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем лимит
            cursor = await db.execute(
                "SELECT COUNT(*) FROM notes WHERE user_id = ?",
                (user_id,)
            )
            count = (await cursor.fetchone())[0]
            
            from config import MAX_NOTES_PER_USER
            if count >= MAX_NOTES_PER_USER:
                return "limit"
            
            # Получаем следующий ID
            cursor = await db.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM notes WHERE user_id = ?",
                (user_id,)
            )
            note_id = (await cursor.fetchone())[0]
            
            created_at = datetime.now().strftime("%d.%m.%Y %H:%M")
            
            await db.execute(
                "INSERT INTO notes (id, user_id, text, created_at) VALUES (?, ?, ?, ?)",
                (note_id, user_id, text, created_at)
            )
            await db.commit()
            
            return {
                "id": note_id,
                "text": text,
                "created_at": created_at
            }
    
    async def get_notes(self, user_id: int) -> List[Dict]:
        """Получение списка заметок"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, text, created_at FROM notes WHERE user_id = ? ORDER BY id",
                (user_id,)
            )
            rows = await cursor.fetchall()
            
            return [
                {"id": row[0], "text": row[1], "created_at": row[2]}
                for row in rows
            ]
    
    async def delete_note(self, user_id: int, note_id: int) -> bool:
        """Удаление заметки"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM notes WHERE user_id = ? AND id = ?",
                (user_id, note_id)
            )
            await db.commit()
            return cursor.rowcount > 0
    
    # === ПРОФИЛИ ===
    
    async def save_profile_snapshot(self, user_id: int, data: Dict, timestamp: str):
        """Сохранение снимка профиля"""
        import json
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO profiles (user_id, data, timestamp) VALUES (?, ?, ?)",
                (user_id, json.dumps(data, ensure_ascii=False), timestamp)
            )
            
            # Удаляем старые снимки (оставляем последние 10)
            await db.execute("""
                DELETE FROM profiles 
                WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM profiles 
                    WHERE user_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT 10
                )
            """, (user_id, user_id))
            
            await db.commit()
    
    async def get_profile_snapshots(self, user_id: int) -> List[Dict]:
        """Получение снимков профиля"""
        import json
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT data, timestamp FROM profiles WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
                (user_id,)
            )
            rows = await cursor.fetchall()
            
            return [
                {"data": json.loads(row[0]), "timestamp": row[1]}
                for row in rows
            ]
    
    # === ОЖИДАНИЕ СТАТУСА ===
    
    async def add_waiting_status(self, peer_id: int, user_id: int):
        """Добавление в ожидание статуса"""
        import time
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO waiting_status (peer_id, user_id, timestamp) VALUES (?, ?, ?)",
                (peer_id, user_id, time.time())
            )
            await db.commit()
    
    async def get_and_remove_waiting_status(self, peer_id: int) -> Optional[Dict]:
        """Получение и удаление из ожидания"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT user_id, timestamp FROM waiting_status WHERE peer_id = ?",
                (peer_id,)
            )
            row = await cursor.fetchone()
            
            if row:
                await db.execute(
                    "DELETE FROM waiting_status WHERE peer_id = ?",
                    (peer_id,)
                )
                await db.commit()
                return {"user_id": row[0], "timestamp": row[1]}
            
            return None
    
    async def cleanup_waiting_states(self):
        """Очистка устаревших ожиданий"""
        import time
        from config import STATUS_WAIT_TIMEOUT
        
        async with aiosqlite.connect(self.db_path) as db:
            current_time = time.time()
            await db.execute(
                "DELETE FROM waiting_status WHERE ? - timestamp > ?",
                (current_time, STATUS_WAIT_TIMEOUT)
            )
            await db.commit()
    
    async def close(self):
        """Закрытие БД"""
        if self._backup_task:
            self._backup_task.cancel()
            try:
                await self._backup_task
            except asyncio.CancelledError:
                pass
        logger.info("🔒 База данных закрыта")

# Глобальный экземпляр
db = Database()