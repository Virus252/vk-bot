from datetime import datetime, time as dt_time
from typing import Dict, List

# Классы, привязанные к расам
RACE_CLASSES = {
    "Орк": ["Берсерк", "Шаман"],
    "Человек": ["Послушник", "Рыцарь ордена Башни"],
    "Эльф": ["Танцующий с клинками", "Друид"],
    "Гоблин": ["Трикстер", "Шулер"],
}

# Классы, доступные ЛЮБОЙ расе (универсальные)
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
    """Проверка условия для стата"""
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
    """Проверка доступных классов"""
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
    """Форматирование разницы профилей"""
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
        if val == 0:
            return None
        sign = '+' if val > 0 else ''
        abs_val = abs(val)
        if abs_val >= 1000000:
            return f"{sign}{val / 1000000:.2f}кк"
        elif abs_val >= 1000:
            return f"{sign}{val / 1000:.1f}к"
        else:
            return f"{sign}{int(round(val))}"
    
    def check_change(key, label, is_float=False, threshold=0.001):
        old_val = old_p.get(key, 0)
        new_val = new_p.get(key, 0)
        d = new_val - old_val
        if abs(d) <= threshold:
            return
        formatted_val = format_number_with_suffix(d)
        if formatted_val:
            ch.append(f"{label}: {formatted_val}")
    
    old_exp = old_p.get("exp_current", 0)
    new_exp = new_p.get("exp_current", 0)
    diff_exp_kk = new_exp - old_exp
    
    if abs(diff_exp_kk) > 0.0001:
        diff_exp_absolute = diff_exp_kk * 1000000
        sign = '+' if diff_exp_absolute > 0 else ''
        abs_val = abs(diff_exp_absolute)
        if abs_val >= 1000000:
            exp_str = f"{sign}{diff_exp_absolute / 1000000:.2f}кк"
        elif abs_val >= 1000:
            exp_str = f"{sign}{diff_exp_absolute / 1000:.1f}к"
        else:
            exp_str = f"{sign}{int(round(diff_exp_absolute))}"
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

def limits_to_profile(limits: Dict, race: str = "") -> Dict:
    """Преобразование пределов в профиль"""
    name_to_key = {
        "Сила": "strength",
        "Интеллект": "intelligence",
        "Ловкость": "agility",
        "Здоровье": "hp",
        "Мана": "mana",
        "Стамина": "stamina"
    }
    
    profile = {
        "level": 0, "exp_current": 0.0, "exp_max": 0.0,
        "hp": 0, "mana": 0, "stamina": 0,
        "strength": 0, "intelligence": 0, "agility": 0,
        "luck": 0, "speed": 0, "crit": 0.0, "chance": 0.0,
        "min_dmg": 0, "max_dmg": 0, "min_spec": 0, "max_spec": 0,
        "cores": 0, "rnd": 0, "research_points": 0, "research_max": 0,
        "upgrades": 0,
        "race": race, "phys_def": 0, "magic_def": 0
    }
    
    for name, value in limits.items():
        key = name_to_key.get(name)
        if key:
            profile[key] = value
    
    return profile

def format_tower_report(s: Dict, user_profile: Dict = None) -> str:
    """Форматирование отчёта по Башне"""
    has = any([
        s["stone"], s["sharpening_stone"], s["wood"],
        s["strength"], s["agility"], s["intelligence"],
        s["gold_items"], s["red_items"], s["black_items"],
        s["gear_items"], s["diamond_items"],
        s["limits"], s["op_points"]
    ])
    
    if not has:
        return ""
    
    r = f"🏰 Отчёт по Башне\n📨 Сообщений: {s['messages_count']}\n\n"
    
    items = []
    if s["gold_items"]: items.append(f"🟡 Легендарные: {s['gold_items']}")
    if s["red_items"]: items.append(f"🔴 Мифические: {s['red_items']}")
    if s["black_items"]: items.append(f"⚫ Проклятые: {s['black_items']}")
    if s["gear_items"]: items.append(f"⚙️ Моды: {s['gear_items']}")
    if s["diamond_items"]: items.append(f"💠 Сет: {s['diamond_items']}")
    
    if items:
        r += "🎁 Предметы:\n" + "\n".join(items) + "\n\n"
    
    mats = []
    if s["stone"]: mats.append(f"🧱 Камень: +{s['stone']}")
    if s["sharpening_stone"]: mats.append(f"🧿 Камень заточки: +{s['sharpening_stone']}")
    if s["wood"]: mats.append(f"🪵 Дерево: +{s['wood']}")
    
    if mats:
        r += "🧱 Материалы:\n" + "\n".join(mats) + "\n\n"
    
    chars = []
    for k, l in [("strength", "💪 Сила"), ("agility", "🌀 Ловк"), ("intelligence", "🎓 Инт")]:
        if s[k]: chars.append(f"{l}: {'+' if s[k]>0 else ''}{s[k]}")
    
    if chars:
        r += "✨ Характеристики:\n" + "\n".join(chars) + "\n\n"
    
    if s["cores_left"]: r += f"🔮 Ядер осталось: {s['cores_left']}\n"
    if s["inventory_slots"]: r += f"🎒 Слотов: {s['inventory_slots']}\n"
    
    if s["limits"]:
        if user_profile:
            check_profile = dict(user_profile)
            name_to_key = {
                "Сила": "strength", "Интеллект": "intelligence", "Ловкость": "agility",
                "Здоровье": "hp", "Мана": "mana", "Стамина": "stamina"
            }
            for limit_name, limit_val in s["limits"].items():
                key = name_to_key.get(limit_name)
                if key:
                    check_profile[key] = limit_val
            
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