import aiosqlite
import asyncio
import logging
import os
import shutil
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Union
from config import (DB_PATH, BACKUP_INTERVAL_HOURS, MAX_GLOBAL_NOTES,
                    MAX_NOTE_LENGTH, STATUS_WAIT_TIMEOUT)

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self.backup_interval = BACKUP_INTERVAL_HOURS * 3600
        self._backup_task = None

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    role_at_creation TEXT DEFAULT 'Private'
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_roles (
                    user_id INTEGER PRIMARY KEY,
                    role TEXT NOT NULL DEFAULT 'Private'
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS waiting_status (
                    peer_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)

            await db.commit()
            await self._migrate_notes(db)

            await db.execute("CREATE INDEX IF NOT EXISTS idx_notes_author ON notes(author_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_profiles_user ON profiles(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_profiles_timestamp ON profiles(timestamp)")
            await db.commit()
            logger.info(f"✅ База данных инициализирована: {self.db_path}")

    async def _migrate_notes(self, db):
        """Перенос старой таблицы заметок (user_id) в новую (author_id)"""
        cursor = await db.execute("PRAGMA table_info(notes)")
        cols = [row[1] for row in await cursor.fetchall()]
        if "author_id" in cols or "user_id" not in cols:
            return
        logger.warning("🔄 Обнаружена старая таблица заметок — выполняю миграцию...")
        try:
            await db.execute("ALTER TABLE notes RENAME TO notes_old")
            await db.execute("""
                CREATE TABLE notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    role_at_creation TEXT DEFAULT 'Private'
                )
            """)
            await db.execute("""
                INSERT INTO notes (author_id, text, created_at, role_at_creation)
                SELECT user_id, text, created_at, 'Private' FROM notes_old
            """)
            await db.execute("DROP TABLE notes_old")
            await db.commit()
            logger.info("✅ Миграция заметок завершена")
        except Exception as e:
            logger.error(f"Ошибка миграции заметок: {e}")
            await db.rollback()

    async def start_backup_scheduler(self):
        self._backup_task = asyncio.create_task(self._backup_loop())
        logger.info(f"💾 Планировщик бэкапов запущен (интервал: {self.backup_interval}с)")

    async def _backup_loop(self):
        while True:
            try:
                await asyncio.sleep(self.backup_interval)
                await self.create_backup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле бэкапов: {e}")

    async def create_backup(self):
        if not os.path.exists(self.db_path):
            return
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"bot_data_{timestamp}.db")
        try:
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"💾 Бэкап создан: {backup_path}")
            backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("bot_data_")])
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    os.remove(os.path.join(backup_dir, old_backup))
                    logger.info(f"🗑 Удалён старый бэкап: {old_backup}")
        except Exception as e:
            logger.error(f"Ошибка создания бэкапа: {e}")

    # === РОЛИ ===
    async def get_user_role(self, user_id: int) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT role FROM user_roles WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else "Private"

    async def set_user_role(self, user_id: int, role: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO user_roles (user_id, role) VALUES (?, ?)",
                (user_id, role)
            )
            await db.commit()

    async def get_all_roles(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT user_id, role FROM user_roles ORDER BY role"
            )
            rows = await cursor.fetchall()
            return [{"user_id": r[0], "role": r[1]} for r in rows]

    # === ОБЩИЕ ЗАМЕТКИ ===
    async def add_note_global(self, author_id: int, text: str, role: str) -> Union[Dict, str, None]:
        if len(text) > MAX_NOTE_LENGTH:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM notes")
            count = (await cursor.fetchone())[0]
            if count >= MAX_GLOBAL_NOTES:
                return "limit"

            created_at = datetime.now().strftime("%d.%m.%Y %H:%M")
            cursor = await db.execute(
                "INSERT INTO notes (author_id, text, created_at, role_at_creation) VALUES (?, ?, ?, ?)",
                (author_id, text, created_at, role)
            )
            note_id = cursor.lastrowid
            await db.commit()
            return {"id": note_id, "text": text, "created_at": created_at, "author_id": author_id}

    async def get_all_notes(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, author_id, text, created_at, role_at_creation FROM notes ORDER BY id DESC"
            )
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "author_id": r[1], "text": r[2], "created_at": r[3], "role": r[4]}
                for r in rows
            ]

    async def get_note_by_id(self, note_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, author_id, text, role_at_creation FROM notes WHERE id = ?",
                (note_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {"id": row[0], "author_id": row[1], "text": row[2], "role": row[3]}
            return None

    async def delete_note_global(self, note_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            await db.commit()
            return cursor.rowcount > 0

    # === ПРОФИЛИ ===
    async def save_profile_snapshot(self, user_id: int, data: Dict, timestamp: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO profiles (user_id, data, timestamp) VALUES (?, ?, ?)",
                (user_id, json.dumps(data, ensure_ascii=False), timestamp)
            )
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
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT data, timestamp FROM profiles WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [{"data": json.loads(r[0]), "timestamp": r[1]} for r in rows]

    # === ОЖИДАНИЕ СТАТУСА ===
    async def add_waiting_status(self, peer_id: int, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO waiting_status (peer_id, user_id, timestamp) VALUES (?, ?, ?)",
                (peer_id, user_id, time.time())
            )
            await db.commit()

    async def get_and_remove_waiting_status(self, peer_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT user_id, timestamp FROM waiting_status WHERE peer_id = ?", (peer_id,)
            )
            row = await cursor.fetchone()
            if row:
                await db.execute("DELETE FROM waiting_status WHERE peer_id = ?", (peer_id,))
                await db.commit()
                return {"user_id": row[0], "timestamp": row[1]}
            return None

    async def cleanup_waiting_states(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM waiting_status WHERE ? - timestamp > ?",
                (time.time(), STATUS_WAIT_TIMEOUT)
            )
            await db.commit()

    async def close(self):
        if self._backup_task:
            self._backup_task.cancel()
            try:
                await self._backup_task
            except asyncio.CancelledError:
                pass
        logger.info("🔒 База данных закрыта")


db = Database()