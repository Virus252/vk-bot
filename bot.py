import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import random
import json
import os
import re
import sys
import signal
import logging
import threading
from datetime import datetime, time as dt_time
import time
from typing import Dict, List, Optional

# ==========================================
# 1. НАСТРОЙКИ И ЛОГИРОВАНИЕ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("VK_TOKEN")
if not TOKEN:
    logger.critical("❌ Токен VK_TOKEN не найден в .env файле!")
    sys.exit(1)
    
NOTES_FILE = "notes.json"
PROFILES_FILE = "profiles.json"
MAX_NOTES_PER_USER = 100
MAX_NOTE_LENGTH = 500
MAX_FWD_MESSAGES = 30
MAX_TEXT_LENGTH = 5000
STATUS_WAIT_TIMEOUT = 15
QUOTE_CHAT_ID = int(os.environ.get("QUOTE_CHAT_ID", 2000000152))
QUOTE_INTERVAL_SECONDS = 1200

# ==========================================
# 2. ХРАНИЛИЩЕ ДАННЫХ
# ==========================================
class DataStore:
    def __init__(self):  
        self._lock = threading.Lock()
        self.notes: Dict[str, List[Dict]] = {}
        self.profiles: Dict[str, Dict] = {}
        self.waiting_status: Dict[int, Dict] = {}
        self._load_initial_data()

    def _load_initial_data(self):
        for filepath, target_dict in [(NOTES_FILE, self.notes), (PROFILES_FILE, self.profiles)]:
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        target_dict.update(json.load(f))
                    logger.info(f"Загружено: {filepath}")
                except Exception as e:
                    logger.error(f"Ошибка чтения {filepath}: {e}")

    def save_notes_async(self):
        self._save_file(NOTES_FILE, self.notes)

    def save_profiles_async(self):
        self._save_file(PROFILES_FILE, self.profiles)

    def _save_file(self, filepath, data):
        temp_path = filepath + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, filepath)
        except Exception as e:
            logger.error(f"Ошибка записи {filepath}: {e}")

    def add_note(self, user_id: int, text: str):
        if len(text) > MAX_NOTE_LENGTH:
            return None
        uid_str = str(user_id)
        with self._lock:
            if uid_str not in self.notes:
                self.notes[uid_str] = []
            if len(self.notes[uid_str]) >= MAX_NOTES_PER_USER:
                return "limit"
            note = {
                "id": len(self.notes[uid_str]) + 1,
                "text": text,
                "created_at": datetime.now().strftime("%d.%m.%Y %H:%M")
            }
            self.notes[uid_str].append(note)
            threading.Thread(target=self.save_notes_async, daemon=True).start()
            return note

    def get_notes(self, user_id: int) -> List[Dict]:
        with self._lock:
            return self.notes.get(str(user_id), [])

    def delete_note(self, user_id: int, note_id: int) -> bool:
        uid_str = str(user_id)
        with self._lock:
            if uid_str not in self.notes:
                return False
            notes_list = self.notes[uid_str]
            for i, note in enumerate(notes_list):
                if note["id"] == note_id:
                    notes_list.pop(i)
                    for idx, n in enumerate(notes_list, 1):
                        n["id"] = idx
                    threading.Thread(target=self.save_notes_async, daemon=True).start()
                    return True
        return False

    def save_profile_snapshot(self, user_id: int, data: Dict, timestamp: str):
        key = str(user_id)
        with self._lock:
            if key not in self.profiles:
                self.profiles[key] = {"snapshots": []}
            snaps = self.profiles[key]["snapshots"]
            snaps.append({"data": data, "timestamp": timestamp})
            if len(snaps) > 10:
                self.profiles[key]["snapshots"] = snaps[-10:]
            threading.Thread(target=self.save_profiles_async, daemon=True).start()
            return list(snaps)

    def add_waiting_status(self, peer_id: int, user_id: int):
        with self._lock:
            self.waiting_status[peer_id] = {"user_id": user_id, "timestamp": time.time()}

    def get_and_remove_waiting_status(self, peer_id: int) -> Optional[Dict]:
        with self._lock:
            return self.waiting_status.pop(peer_id, None)

    def cleanup_waiting_states(self):
        current_time = time.time()
        with self._lock:
            expired = [k for k, v in self.waiting_status.items() if current_time - v["timestamp"] > STATUS_WAIT_TIMEOUT]
            for k in expired:
                del self.waiting_status[k]

store = DataStore()

# ==========================================
# 3. ПАРСЕР ПРОФИЛЯ
# ==========================================
class ProfileFieldParser:
    def __init__(self, key: str, pattern: re.Pattern, group_index: int = 1, type_cast: type = int):  # ИСПРАВЛЕНО
        self.key = key
        self.pattern = pattern
        self.group_index = group_index
        self.type_cast = type_cast

    def parse(self, text: str, profile: Dict):
        match = self.pattern.search(text)
        if match:
            try:
                profile[self.key] = self.type_cast(match.group(self.group_index))
                return True
            except (ValueError, IndexError):
                pass
        return False

PROFILE_PARSERS = [
    ProfileFieldParser("level", re.compile(r'Уровень:\s*(\d+)')),
    ProfileFieldParser("exp_current", re.compile(r'Опыт:\s*([\d.]+)кк/[\d.]+кк'), type_cast=float),
    ProfileFieldParser("exp_max", re.compile(r'Опыт:\s*[\d.]+кк/([\d.]+)кк'), type_cast=float),
    ProfileFieldParser("hp", re.compile(r'❤\s*Здоровье:\s*\d+/(\d+)')),
    ProfileFieldParser("mana", re.compile(r'💙\s*Мана:\s*\d+/(\d+)')),
    ProfileFieldParser("stamina", re.compile(r'🤍\s*Стамина:\s*\d+/(\d+)')),
    ProfileFieldParser("strength", re.compile(r'💪\s*Сила:\s*(\d+)')),
    ProfileFieldParser("intelligence", re.compile(r'🎓\s*Интеллект:\s*(\d+)')),
    ProfileFieldParser("agility", re.compile(r'🌀\s*Ловкость:\s*(\d+)')),
    ProfileFieldParser("luck", re.compile(r'🍀\s*Удача:\s*(\d+)')),
    ProfileFieldParser("speed", re.compile(r'⚡\s*Скорость:\s*(\d+)')),
    ProfileFieldParser("crit", re.compile(r'💥\s*Крит:\s*([\d.]+)%'), type_cast=float),
    ProfileFieldParser("chance", re.compile(r'🎲\s*Шанс:\s*([\d.]+)%'), type_cast=float),
    ProfileFieldParser("cores", re.compile(r'🔮\s*Ядер:\s*(\d+)')),
    ProfileFieldParser("rnd", re.compile(r'🪙\s*RND:\s*(\d+)')),
    ProfileFieldParser("research_points", re.compile(r'🔬\s*Очки исследования:\s*(\d+)/\d+')),
    ProfileFieldParser("research_max", re.compile(r'🔬\s*Очки исследования:\s*\d+/(\d+)')),
    ProfileFieldParser("upgrades", re.compile(r'⚡\s*Доступных улучшений:\s*(\d+)')),
    ProfileFieldParser("race", re.compile(r'Раса:\s*(\S+)'), type_cast=str),
    ProfileFieldParser("phys_def", re.compile(r'Физ.?\s*защита:\s*(\d+)')),
    ProfileFieldParser("magic_def", re.compile(r'Маг.?\s*защита:\s*(\d+)')),
]

def parse_profile_text(text: str) -> Dict:
    profile = {
        "level": 0, "exp_current": 0.0, "exp_max": 0.0,
        "hp": 0, "mana": 0, "stamina": 0,
        "strength": 0, "intelligence": 0, "agility": 0,
        "luck": 0, "speed": 0, "crit": 0.0, "chance": 0.0,
        "min_dmg": 0, "max_dmg": 0, "min_spec": 0, "max_spec": 0,
        "cores": 0, "rnd": 0, "research_points": 0, "research_max": 0,
        "upgrades": 0, "race": "", "phys_def": 0, "magic_def": 0
    }
    dmg_match = re.search(r'(?:Урон|Атака):\s*(\d+)-(\d+)', text)
    if dmg_match:
        profile["min_dmg"] = int(dmg_match.group(1))
        profile["max_dmg"] = int(dmg_match.group(2))
    spec_match = re.search(r'(?:Спец.|Специальный):\s*(\d+)-(\d+)', text)
    if spec_match:
        profile["min_spec"] = int(spec_match.group(1))
        profile["max_spec"] = int(spec_match.group(2))
    for parser in PROFILE_PARSERS:
        parser.parse(text, profile)
    return profile

# ==========================================
# 4. ПРОВЕРКА КЛАССОВ И РАС
# ==========================================
RACE_CLASSES = {
    "Орк": ["Берсерк", "Шаман"],
    "Человек": ["Послушник", "Рыцарь ордена Башни"],
    "Эльф": ["Танцующий с клинками", "Друид"],
    "Гоблин": ["Трикстер", "Шулер"],
}

UNIVERSAL_CLASSES = [
    "Гладиатор", "Бастион", "Жнец", "Алый предвестник",
    "Идущий по грани", "Мародер", "Мистический скульптор",
    "Мученик", "Отродье", "Ассасин", "Ронин",
    "Рунический клинок", "Шут", "Элементалист",
]

CLASS_REQUIREMENTS = {
    "Гладиатор": {"intelligence": "<=99", "strength": ">300", "stamina": ">300"},
    "Бастион": {"stamina": ">500"},
    "Жнец": {"hp": ">300", "mana": ">15", "intelligence": ">15"},
    "Берсерк": {"hp": ">30", "strength": ">15", "stamina": ">20"},
    "Шаман": {"mana": ">50", "intelligence": ">20"},
    "Послушник": {"hp": ">100", "intelligence": ">20", "mana": ">100"},
    "Рыцарь ордена Башни": {"hp": ">200", "strength": ">50", "stamina": ">50"},
    "Танцующий с клинками": {"hp": ">50", "mana": ">40", "stamina": ">40", "strength": ">15", "agility": ">15"},
    "Друид": {"hp": ">20", "mana": ">15", "stamina": ">15", "strength": ">10", "intelligence": ">10"},
    "Трикстер": {"hp": ">30", "mana": ">20", "stamina": ">20", "strength": ">10", "intelligence": ">10", "agility": ">10", "luck": ">10"},
    "Шулер": {"hp": ">30", "stamina": ">15", "strength": ">10", "agility": ">15", "luck": ">10"},
    "Алый предвестник": {"hp": ">1000", "intelligence": ">500", "mana": ">300", "_special": "time_window_00_03"},
    "Идущий по грани": {"hp": ">5", "mana": ">20", "stamina": ">20", "strength": ">30", "intelligence": ">30", "agility": ">40", "luck": ">15", "speed": ">5"},
    "Мародер": {"luck": ">500"},
    "Мистический скульптор": {"strength": "<=50", "mana": ">1500", "intelligence": ">1500"},
    "Мученик": {"hp": ">1100", "agility": "==0", "luck": "<=50"},
    "Отродье": {"hp": ">25", "mana": ">10", "stamina": ">10", "strength": "<=10", "intelligence": "<=10", "agility": "<=10", "luck": "<=10"},
    "Ассасин": {"intelligence": "<=99", "strength": ">200", "speed": ">350"},
    "Ронин": {"speed": ">200", "stamina": ">300"},
    "Рунический клинок": {"mana": ">500", "stamina": ">500", "hp": ">1000"},
    "Шут": {"intelligence": ">500", "speed": ">200"},
    "Элементалист": {"strength": "<=99", "mana": ">500", "intelligence": ">600"},
}

def check_condition(value, condition: str) -> bool:
    condition = condition.strip()
    if '-' in condition and not any(op in condition for op in ['>', '<', '=']):
        try:
            parts = condition.split('-')
            return float(parts[0]) <= value <= float(parts[1])
        except:
            return False
    if condition.startswith(">="): return value >= float(condition[2:].strip())
    if condition.startswith("<="): return value <= float(condition[2:].strip())
    if condition.startswith("=="): return value == float(condition[2:].strip())
    if condition.startswith(">"): return value > float(condition[1:].strip())
    if condition.startswith("<"): return value < float(condition[1:].strip())
    return False

def check_class_eligibility(profile: Dict, status_time_str: str = "") -> List[str]:
    eligible = []
    current_time = datetime.now().time()
    status_time_obj = None
    if status_time_str:
        try:
            dt_obj = datetime.strptime(status_time_str, "%d.%m.%Y %H:%M")
            status_time_obj = dt_obj.time()
        except ValueError:
            pass
    race = profile.get("race", "").strip()
    if race in RACE_CLASSES:
        allowed_classes = set(RACE_CLASSES[race] + UNIVERSAL_CLASSES)
    else:
        allowed_classes = set(CLASS_REQUIREMENTS.keys())
    for class_name, reqs in CLASS_REQUIREMENTS.items():
        if class_name not in allowed_classes:
            continue
        is_eligible = True
        special_time = False
        for key, cond in reqs.items():
            if key.startswith("_"):
                if key == "_special" and cond == "time_window_00_03":
                    special_time = True
                continue
            if key not in profile or not check_condition(profile[key], cond):
                is_eligible = False
                break
        if special_time:
            check_time = status_time_obj if status_time_obj else current_time
            if not (dt_time(0, 0) <= check_time <= dt_time(3, 0)):
                is_eligible = False
        if is_eligible:
            eligible.append(class_name)
    return eligible

def format_diff(old_p: Dict, new_p: Dict, ts_old: str, ts_new: str) -> str:
    try:
        dt_old = datetime.fromisoformat(ts_old)
        dt_new = datetime.fromisoformat(ts_new)
    except ValueError:
        return "⚠️ Ошибка формата времени."
    delta = dt_new - dt_old
    days, rem = delta.days, delta.seconds
    hours, minutes = rem // 3600, (rem % 3600) // 60
    if days > 0: 
        t = f"{days} дн. {hours} ч."
    elif hours > 0: 
        t = f"{hours} ч. {minutes} мин."
    else: 
        t = f"{minutes} мин."
    r = f"📊 Изменения профиля\n⏳ Прошло: {t}\n"
    r += f"Было: {dt_old.strftime('%d.%m.%Y %H:%M')}\n"
    r += f"Стало: {dt_new.strftime('%d.%m.%Y %H:%M')}\n\n"
    ch = []
    def format_number_with_suffix(val):
        if val == 0: return None
        sign = '+' if val > 0 else ''
        abs_val = abs(val)
        if abs_val >= 1000000: return f"{sign}{val / 1000000:.2f}кк"
        elif abs_val >= 1000: return f"{sign}{val / 1000:.1f}к"
        else: return f"{sign}{int(round(val))}"
    def check_change(key, label, is_float=False, threshold=0.001):
        old_val = old_p.get(key, 0)
        new_val = new_p.get(key, 0)
        d = new_val - old_val
        if abs(d) <= threshold: return
        formatted_val = format_number_with_suffix(d)
        if formatted_val: ch.append(f"{label}: {formatted_val}")
    old_exp = old_p.get("exp_current", 0)
    new_exp = new_p.get("exp_current", 0)
    diff_exp_kk = new_exp - old_exp
    if abs(diff_exp_kk) > 0.0001:
        diff_exp_absolute = diff_exp_kk * 1000000 
        sign = '+' if diff_exp_absolute > 0 else ''
        abs_val = abs(diff_exp_absolute)
        if abs_val >= 1000000: exp_str = f"{sign}{diff_exp_absolute / 1000000:.2f}кк"
        elif abs_val >= 1000: exp_str = f"{sign}{diff_exp_absolute / 1000:.1f}к"
        else: exp_str = f"{sign}{int(round(diff_exp_absolute))}"
        ch.append(f"⭐ Опыт: {exp_str}")
    for key, label in [
        ("hp", "❤ HP"), ("mana", "💙 Мана"), ("stamina", "🤍 Стамина"),
        ("strength", "💪 Сила"), ("intelligence", "🎓 Инт"), ("agility", "🌀 Ловк"),
        ("luck", "🍀 Удача"), ("speed", "⚡ Скор"), ("cores", "🔮 Ядра"),
        ("rnd", "🪙 RND"), ("research_points", "🔬 Иссл."), ("upgrades", "⚡ Апгр")
    ]:
        check_change(key, label)
    check_change("crit", "💥 Крит", is_float=True)
    check_change("chance", "🎲 Шанс", is_float=True)
    check_change("min_dmg", "🗡 Мин.урон")
    check_change("max_dmg", "🗡 Макс.урон")
    check_change("min_spec", "✨ Мин.спец")
    check_change("max_spec", "✨ Макс.спец")
    if not ch:
        r += "✅ Изменений не обнаружено.\n"
    else:
        r += "📈 Динамика:\n" + "\n".join(ch) + "\n"
    return r

# ==========================================
# 5. ПАРСЕР БАШНИ
# ==========================================
def parse_tower_messages(fwd: List[Dict]) -> Dict:
    stats = {
        "stone": 0, "sharpening_stone": 0, "wood": 0,
        "strength": 0, "agility": 0, "intelligence": 0,
        "cores_left": 0, "inventory_slots": 0,
        "gold_items": 0, "red_items": 0, "black_items": 0,
        "gear_items": 0, "diamond_items": 0,
        "messages_count": len(fwd), "limits": {}, "op_points": 0
    }
    limited_fwd = fwd[:MAX_FWD_MESSAGES]
    txt = "\n".join(m.get('text', '') for m in limited_fwd)
    if not txt: return stats
    lines = txt.split('\n')
    for line in lines:
        if 'Вам выпало:' in line:
            count_match = re.search(r'\(х(\d+)\)', line)
            c = int(count_match.group(1)) if count_match else 1
            if '🟡' in line: stats["gold_items"] += c
            elif '🔴' in line: stats["red_items"] += c
            elif '⚫' in line: stats["black_items"] += c
            elif '⚙' in line: stats["gear_items"] += c
            elif '💠' in line: stats["diamond_items"] += c
    sharpening_matches = re.findall(r'[Кк]амень заточки\s*\(х(\d+)\)', txt)
    if sharpening_matches: stats["sharpening_stone"] = sum(int(x) for x in sharpening_matches)
    stone_simple = re.findall(r'(?<!заточки )[Кк]амень\s*[xхX](\d+)', txt)
    stone_emoji = re.findall(r'🧱.*?[xх\(]\s*(\d+)', txt)
    stats["stone"] = sum(int(x) for x in stone_simple) + sum(int(x) for x in stone_emoji)
    wood_paren = re.findall(r'[Дд]ревесина\s*\(х(\d+)\)', txt)
    wood_simple = re.findall(r'[Дд]ревесина\s*[xхX](\d+)', txt)
    wood_emoji = re.findall(r'🪵.*?[xх\(]\s*(\d+)', txt)
    stats["wood"] = sum(int(x) for x in wood_paren) + sum(int(x) for x in wood_simple) + sum(int(x) for x in wood_emoji)
    char_map = {"strength": ["💪", "Сила"], "agility": ["🌀", "Ловкость"], "intelligence": ["🎓", "Интеллект"]}
    for stat_key, identifiers in char_map.items():
        emoji, name_ru = identifiers
        for line in lines:
            if emoji in line or name_ru in line:
                val_match = re.search(r'на\s+(\d+)', line)
                count_match = re.search(r'\(х(\d+)\)', line)
                if val_match and count_match:
                    total = int(val_match.group(1)) * int(count_match.group(1))
                    if 'уменьшена' in line.lower() or '⬇️' in line: stats[stat_key] -= total
                    elif 'увеличена' in line.lower() or '⬆️' in line: stats[stat_key] += total
    if cm := re.search(r'🔮\s*Осталось ядер:\s*(\d+)', txt): stats["cores_left"] = int(cm.group(1))
    if sl := re.search(r'🎒\s*Свободных слотов инвентаря:\s*(\d+)', txt): stats["inventory_slots"] = int(sl.group(1))
    limit_pattern = re.compile(r'(💪|🎓|🌀|❤|💙|🤍)\s*([^:]+):\s*\d+\s*\(Предел\s*(\d+)\)')
    limits_found = limit_pattern.findall(txt)
    if limits_found:
        for emoji, name, limit_val in limits_found:
            stats["limits"][name.strip()] = int(limit_val)
    op_match = re.search(r'🧬\s*Очки предела\s*\(ОП\):\s*(\d+)', txt)
    if op_match: stats["op_points"] = int(op_match.group(1))
    return stats

def format_tower_report(s: Dict, user_profile: Dict = None) -> Optional[str]:
    has = any([s["stone"], s["sharpening_stone"], s["wood"], s["strength"], s["agility"], s["intelligence"], s["gold_items"], s["red_items"], s["black_items"], s["gear_items"], s["diamond_items"], s["limits"], s["op_points"]])
    if not has: return None
    r = f"🏰 Отчёт по Башне\n📨 Сообщений: {s['messages_count']}\n\n"
    items = []
    if s["gold_items"]: items.append(f"🟡 Легендарные: {s['gold_items']}")
    if s["red_items"]: items.append(f"🔴 Мифические: {s['red_items']}")
    if s["black_items"]: items.append(f"⚫ Проклятые: {s['black_items']}")
    if s["gear_items"]: items.append(f"⚙️ Моды: {s['gear_items']}")
    if s["diamond_items"]: items.append(f"💠 Сет: {s['diamond_items']}")
    if items: r += "🎁 Предметы:\n" + "\n".join(items) + "\n\n"
    mats = []
    if s["stone"]: mats.append(f"🧱 Камень: +{s['stone']}")
    if s["sharpening_stone"]: mats.append(f"🧿 Камень заточки: +{s['sharpening_stone']}")
    if s["wood"]: mats.append(f"🪵 Дерево: +{s['wood']}")
    if mats: r += "🧱 Материалы:\n" + "\n".join(mats) + "\n\n"
    chars = []
    for k, l in [("strength", "💪 Сила"), ("agility", "🌀 Ловк"), ("intelligence", "🎓 Инт")]:
        if s[k]: chars.append(f"{l}: {'+' if s[k]>0 else ''}{s[k]}")
    if chars: r += "✨ Характеристики:\n" + "\n".join(chars) + "\n\n"
    if s["cores_left"]: r += f"🔮 Ядер осталось: {s['cores_left']}\n"
    if s["inventory_slots"]: r += f"🎒 Слотов: {s['inventory_slots']}\n"
    if s["limits"]:
        if user_profile:
            check_profile = dict(user_profile)
            name_to_key = {"Сила": "strength", "Интеллект": "intelligence", "Ловкость": "agility", "Здоровье": "hp", "Мана": "mana", "Стамина": "stamina"}
            for limit_name, limit_val in s["limits"].items():
                key = name_to_key.get(limit_name)
                if key: check_profile[key] = limit_val
            eligible_classes = check_class_eligibility(check_profile, "")
            race = check_profile.get("race", "Не определена")
            speed = check_profile.get("speed", 0)
            if eligible_classes:
                r += f"\n🧬 Раса: {race} | ⚡ Скорость: {speed}\n"
                r += "🎭 Доступные классы (по пределам):\n"
                r += "\n".join(f"• {c}" for c in eligible_classes) + "\n"
            else:
                r += f"\n🧬 Раса: {race} | ⚡ Скорость: {speed}\n"
                r += "⚠️ По текущим пределам и статам нет доступных классов.\n"
        else:
            r += "\n⚠️ Не удалось найти сохраненный профиль для точной проверки классов.\n"
    return r

# ==========================================
# 6. VK API
# ==========================================
try:
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, group_id=GROUP_ID)
    logger.info("✅ VK API инициализирован.")
except Exception as e:
    logger.critical(f"❌ Ошибка VK API: {e}")
    sys.exit(1)

RE_MENTION = re.compile(r'\[club' + str(GROUP_ID) + r'\|[^]]+\]')  
RE_STATUS_CMD = re.compile(r'^статус$', re.IGNORECASE)

def send_message(peer_id: int, text: str):
    try:
        vk.messages.send(peer_id=peer_id, message=text, random_id=random.getrandbits(32))
    except Exception as e:
        logger.error(f"Ошибка отправки в {peer_id}: {e}")

def is_bot_mentioned(text: str) -> bool:
    return bool(RE_MENTION.search(text))

def extract_command(text: str) -> str:
    return RE_MENTION.sub('', text).strip()

# ==========================================
# 7. ОБРАБОТЧИК СООБЩЕНИЙ
# ==========================================
def handle_message(event):
    msg = event.object.get('message', {})
    text = msg.get('text', '').strip()
    peer_id = msg.get('peer_id')
    from_id = msg.get('from_id')
    if not peer_id or not from_id: return
    if len(text) > MAX_TEXT_LENGTH: text = text[:MAX_TEXT_LENGTH]
    is_chat = peer_id > 2000000000
    store.cleanup_waiting_states()

    if is_chat and peer_id in store.waiting_status:
        wait_info = store.get_and_remove_waiting_status(peer_id)
        if wait_info and (time.time() - wait_info["timestamp"]) < STATUS_WAIT_TIMEOUT:
            has_level = any(p.key == "level" and p.pattern.search(text) for p in PROFILE_PARSERS)
            has_stats = any(p.key in ["strength", "hp"] and p.pattern.search(text) for p in PROFILE_PARSERS)
            if has_level and has_stats:
                time_match = re.search(r'(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})', text)
                status_time_str = time_match.group(1) if time_match else ""
                current_time_iso = datetime.now().isoformat()
                new_profile = parse_profile_text(text)
                if new_profile["level"] > 0:
                    snapshots = store.save_profile_snapshot(wait_info["user_id"], new_profile, current_time_iso)
                    if len(snapshots) >= 2:
                        old = snapshots[-2]
                        send_message(peer_id, format_diff(old["data"], new_profile, old["timestamp"], current_time_iso))
                    else:
                        eligible = check_class_eligibility(new_profile, status_time_str)
                        race = new_profile.get("race", "").strip()
                        resp = f"📋 Профиль сохранён!\n🧬 Раса: {race if race else '❌ Не определена'}\n"
                        if eligible:
                            resp += "\n🎭 Доступные классы:\n" + "\n".join(f"• {c}" for c in eligible)
                        else:
                            resp += "\n⚠️ Нет доступных классов по текущим статам."
                        send_message(peer_id, resp)
                    return

    fwd = msg.get('fwd_messages', [])
    if fwd:
        fwd_text = "\n".join(m.get('text', '') for m in fwd[:MAX_FWD_MESSAGES])
        is_tower = bool(re.search(r'(Вам выпало:|Камень|Древесина|Осталось ядер|Башня|Предел|Очки предела)', fwd_text))
        is_profile = bool(re.search(r'(Уровень:|Характеристики:|Здоровье:)', fwd_text))
        if is_tower:
            target_user_id = from_id
            user_profile = None
            with store._lock:
                snaps = store.profiles.get(str(target_user_id), {}).get("snapshots", [])
                if snaps: user_profile = snaps[-1]["data"]
            tower_stats = parse_tower_messages(fwd)
            tr = format_tower_report(tower_stats, user_profile)
            if tr: send_message(peer_id, tr)
            else: send_message(peer_id, "❌ Не удалось распознать данные Башни или предметы.")
            return
        elif is_profile:
            if is_chat and not is_bot_mentioned(text): pass
            else:
                ct = datetime.now().isoformat()
                np = parse_profile_text(fwd_text)
                time_match = re.search(r'(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})', fwd_text)
                status_time_str = time_match.group(1) if time_match else ""
                snaps = store.save_profile_snapshot(from_id, np, ct)
                if len(snaps) >= 2:
                    old = snaps[-2]
                    send_message(peer_id, format_diff(old["data"], np, old["timestamp"], ct))
                else:
                    eligible = check_class_eligibility(np, status_time_str)
                    race = np.get("race", "не определена")
                    resp = f"📋 Первый профиль сохранён!\n🧬 Раса: {race}\n"
                    if eligible: resp += "\n🎭 Доступные классы:\n" + "\n".join(f"• {c}" for c in eligible)
                    send_message(peer_id, resp)
                return

    if is_chat and RE_STATUS_CMD.match(extract_command(text) if is_bot_mentioned(text) else text):
        store.add_waiting_status(peer_id, from_id)
        return

    if is_chat:
        is_slash_command = text.startswith('/')
        if not is_bot_mentioned(text) and not is_slash_command: return
        if is_bot_mentioned(text): text = extract_command(text)
        if not text.startswith("/"): return
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        if cmd == "/add":
            if not args: send_message(peer_id, "❌ Укажите текст: /add Текст"); return
            res = store.add_note(from_id, args)
            if res is None: send_message(peer_id, f"❌ Текст слишком длинный (макс. {MAX_NOTE_LENGTH})")
            elif res == "limit": send_message(peer_id, f"❌ Лимит заметок ({MAX_NOTES_PER_USER})")
            else: send_message(peer_id, f"✅ Заметка #{res['id']} добавлена!")
        elif cmd == "/list":
            notes = store.get_notes(from_id)
            if not notes: send_message(peer_id, "📭 Нет заметок. /add [текст]"); return
            t = "📋 Заметки:\n\n" + "\n".join(f"#{n['id']} | {n['text']} ({n['created_at']})" for n in notes) + "\n\n/del [номер] — удалить"
            send_message(peer_id, t)
        elif cmd == "/del":
            if not args: send_message(peer_id, "❌ /del [номер]"); return
            try: nid = int(args)
            except ValueError: send_message(peer_id, "❌ Номер должен быть числом"); return
            if store.delete_note(from_id, nid): send_message(peer_id, f"✅ Заметка #{nid} удалена")
            else: send_message(peer_id, f"❌ Заметка #{nid} не найдена")
        elif cmd == "/help":
            h = "📖 Команды:\n/add [текст]\n/list\n/del [номер]\n/help\n\n🏰 Tower of Random:\n• Перешлите ядра — посчитаю\n• Перешлите статы с пределами — покажу классы\n• '@бот статус' — дождусь ответа и покажу динамику"
            if is_chat: h += "\n\n💡 Команды работают и без тега, если начинаются со слэша (/)"
            send_message(peer_id, h)
        elif cmd == "/start":
            send_message(peer_id, "👋 Привет! Напиши /help")
        else:
            send_message(peer_id, "❓ Неизвестная команда. /help")

# ==========================================
# 8. ГЛАВНЫЙ ЦИКЛ
# ==========================================
def graceful_shutdown(signum, frame):
    logger.info("⛔ Остановка...")
    store.save_notes_async()
    store.save_profiles_async()
    time.sleep(1)
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

def main():
    logger.info("🤖 Бот запущен.")
    while True:
        try:
            for event in longpoll.listen():
                logger.info(f"📩 Получено событие: {event.type}")
                if event.type == VkBotEventType.MESSAGE_NEW:
                    handle_message(event)
        except Exception as e:
            logger.error(f"⚠️ Ошибка LongPoll: {e}. Переподключение через 5с...")
            time.sleep(5)

if __name__ == "__main__":  
    main()