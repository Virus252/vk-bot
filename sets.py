from typing import Dict, List

# ==========================================
# ДАННЫЕ О СЕТАХ БРОНИ
# ==========================================

SETS_DATA = {
    "balance": {
        "name": "Сет Баланса",
        "emoji": "⚖️",
        "items": [
            {"name": "Шлем", "stats": "❤️400 💙400 🤍400 🏃20"},
            {"name": "Доспех", "stats": "❤️600 💙600 🤍600 🏃30"},
            {"name": "Поножи", "stats": "❤️500 💙500 🤍500 🏃25"},
            {"name": "Сапоги", "stats": "❤️400 💙400 🤍400 🏃20"}
        ],
        "effects": {
            2: "+10% СТ/МП +5% ХП",
            3: "+15% СТ/МП +5% ХП",
            4: "5% СТ и МП регенерации"
        }
    },
    "eternity": {
        "name": "Сет Вечности",
        "emoji": "♾️",
        "items": [
            {"name": "Забрало", "stats": "❤️600 💪75 🎓75"},
            {"name": "Кираса", "stats": "❤️900 💪100 🎓100"},
            {"name": "Поножи", "stats": "❤️700 💪85 🎓85"},
            {"name": "Сапоги", "stats": "❤️600 💪75 🎓75"}
        ],
        "effects": {
            2: "+5% ХП",
            3: "+10% ХП",
            4: "5% снижение входящего урона"
        }
    },
    "endurance": {
        "name": "Сет Выносливости",
        "emoji": "💪",
        "items": [
            {"name": "Шлем", "stats": "🤍600 🏃20 | 🤍600 💪75"},
            {"name": "Доспех", "stats": "🤍900 🏃30 | 🤍900 💪100"},
            {"name": "Поножи", "stats": "🤍700 🏃25 | 🤍700 💪85"},
            {"name": "Боты", "stats": "🤍500 🏃20 | 🤍500 💪75"}
        ],
        "effects": {
            2: "+5% Силы",
            3: "+10% Силы",
            4: "+20% СТ"
        }
    },
    "wrath": {
        "name": "Сет Гнева",
        "emoji": "🔥",
        "items": [
            {"name": "Шлем", "stats": "💪150 🏃20 | 🤍300 💪150"},
            {"name": "Доспех", "stats": "💪200 🏃30 | 🤍450 💪200"},
            {"name": "Поножи", "stats": "💪170 🏃25 | 🤍350 💪170"},
            {"name": "Боты", "stats": "💪150 🏃20 | 🤍300 💪150"}
        ],
        "effects": {
            2: "+5% Силы",
            3: "+10% Силы",
            4: "5% шанс двойного удара"
        }
    },
    "stars": {
        "name": "Сет Звёзд",
        "emoji": "⭐",
        "items": [
            {"name": "Диадема", "stats": "🎓150 🏃20 | 💙300 🎓150"},
            {"name": "Мантия", "stats": "🎓200 🏃30 | 💙450 🎓200"},
            {"name": "Поножи", "stats": "🎓170 🏃25 | 💙350 🎓170"},
            {"name": "Башмаки", "stats": "🎓150 🏃20 | 💙300 🎓150"}
        ],
        "effects": {
            2: "+5% Интеллекта",
            3: "+10% Интеллекта",
            4: "5% шанс двойного удара"
        }
    },
    "patriot": {
        "name": "Сет Патриота",
        "emoji": "🛡️",
        "items": [
            {"name": "Армет", "stats": "🤍300 🛡️150 🌟150"},
            {"name": "Кираса", "stats": "🤍450 🛡️300 🌟300"},
            {"name": "Поножи", "stats": "🤍350 🛡️225 🌟225"},
            {"name": "Сабатоны", "stats": "🤍300 🛡️150 🌟150"}
        ],
        "effects": {
            2: "+5% Физ. и Маг. защита",
            3: "+10% Физ. и Маг. защита",
            4: "5% снижения урона"
        }
    },
    "suffering": {
        "name": "Сет Страданий",
        "emoji": "💔",
        "items": [
            {"name": "Забрало", "stats": "❤️600 🌟50"},
            {"name": "Кираса", "stats": "❤️900 🛡️100"},
            {"name": "Поножи", "stats": "❤️700 🛡️75"},
            {"name": "Сапоги", "stats": "❤️600 🌟50"}
        ],
        "effects": {
            2: "+5% ХП",
            3: "+10% ХП",
            4: "2.5% реген ХП"
        }
    },
    "mysteries": {
        "name": "Сет Тайн",
        "emoji": "🔮",
        "items": [
            {"name": "Диадема", "stats": "💙600 🏃20 | 💙600 🎓75"},
            {"name": "Мантия", "stats": "💙900 🏃30 | 💙900 🎓100"},
            {"name": "Поножи", "stats": "💙700 🏃25 | 💙700 🎓85"},
            {"name": "Башмаки", "stats": "💙600 🏃20 | 💙600 🎓75"}
        ],
        "effects": {
            2: "+5% Интеллект",
            3: "+10% Интеллект",
            4: "20% МП"
        }
    },
    "shadows": {
        "name": "Сет Теней",
        "emoji": "🌑",
        "items": [
            {"name": "Капюшон", "stats": "🎓75 🌀75 🏃40 | 💪75 🌀75 🏃40"},
            {"name": "Плащ", "stats": "🎓100 🌀100 🏃60 | 💪100 🌀100 🏃60"},
            {"name": "Поножи", "stats": "🎓85 🌀85 🏃50 | 💪85 🌀85 🏃50"},
            {"name": "Ботинки", "stats": "🎓75 🌀75 🏃40 | 💪75 🌀75 🏃40"}
        ],
        "effects": {
            2: "+5% Скорость",
            3: "+10% Скорость",
            4: "200% крит урона"
        }
    },
    "storm": {
        "name": "Сет Шторма",
        "emoji": "⚡",
        "items": [
            {"name": "Диадема", "stats": "💙600 🎓75 🏃20"},
            {"name": "Мантия", "stats": "💙900 🎓100 🏃30"},
            {"name": "Поножи", "stats": "💙700 🎓85 🏃25"},
            {"name": "Башмаки", "stats": "💙600 🎓75 🏃20"}
        ],
        "effects": {
            2: "+15% МП",
            3: "5% реген МП в ход",
            4: "5% регенерация щита"
        }
    }
}

# ==========================================
# КАТЕГОРИИ СЕТОВ
# ==========================================
SET_CATEGORIES = {
    "phys": ["wrath", "endurance"],
    "mp": ["storm", "mysteries", "balance"],
    "hp": ["suffering", "eternity", "balance"],
    "magic": ["stars", "mysteries"],
    "stamina": ["endurance", "balance"],
    "def": ["patriot", "endurance"]
}


def format_set_compact(set_key: str) -> str:
    """Компактное форматирование одного сета"""
    set_data = SETS_DATA.get(set_key)
    if not set_data:
        return ""

    emoji = set_data["emoji"]
    name = set_data["name"]

    lines = [f"{emoji} {name}"]

    for item in set_data["items"]:
        lines.append(f"• {item['name']}: {item['stats']}")

    lines.append("Эффекты:")
    for count, effect in set_data["effects"].items():
        lines.append(f"  {count} вещи: {effect}")

    return "\n".join(lines)


def format_category(category_key: str) -> str:
    """Форматирование категории сетов"""
    set_keys = SET_CATEGORIES.get(category_key, [])
    if not set_keys:
        return "❌ Категория не найдена"

    formatted_sets = [format_set_compact(key) for key in set_keys]
    return "\n\n".join(formatted_sets)