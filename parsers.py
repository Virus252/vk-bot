import re
from typing import Dict, List
from config import MAX_FWD_MESSAGES


class ProfileFieldParser:
    def __init__(self, key: str, pattern: re.Pattern, group_index: int = 1, type_cast: type = int):
        self.key = key
        self.pattern = pattern
        self.group_index = group_index
        self.type_cast = type_cast

    def parse(self, text: str, profile: Dict) -> bool:
        match = self.pattern.search(text)
        if match:
            try:
                value = match.group(self.group_index)
                if self.type_cast is str:
                    profile[self.key] = str(value).strip()
                else:
                    profile[self.key] = self.type_cast(value)
                return True
            except (ValueError, IndexError):
                pass
        return False


PROFILE_PARSERS = [
    ProfileFieldParser("level", re.compile(r'Уровень:\s*(\d+)')),
    ProfileFieldParser("exp_current", re.compile(r'Опыт:\s*([\d.]+)кк/[\d.]+кк'), type_cast=float),
    ProfileFieldParser("exp_max", re.compile(r'Опыт:\s*[\d.]+кк/([\d.]+)кк'), type_cast=float),

    ProfileFieldParser("hp", re.compile(r'❤(?:\s*Здоровье)?\s*:\s*\d+/(\d+)')),
    ProfileFieldParser("mana", re.compile(r'💙(?:\s*Мана)?\s*:\s*\d+/(\d+)')),
    ProfileFieldParser("stamina", re.compile(r'🤍(?:\s*Стамина)?\s*:\s*\d+/(\d+)')),

    ProfileFieldParser("strength", re.compile(r'💪\s*Сила:\s*(\d+)')),
    ProfileFieldParser("intelligence", re.compile(r'🎓\s*Интеллект:\s*(\d+)')),
    ProfileFieldParser("agility", re.compile(r'🌀\s*Ловкость:\s*(\d+)')),
    ProfileFieldParser("luck", re.compile(r'🍀\s*Удача:\s*(\d+)')),
    ProfileFieldParser("speed", re.compile(r'(?:⚡|🏃)\s*Скорость:\s*(\d+)')),

   ProfileFieldParser("crit", re.compile(r'(?:💥(?:\s(?:[Кк]рит(?:\.?\sурон)?|[Уу]рон))?|[Кк]рит\.?\sурон)\s:?\s([\d.]+)\s%?'), type_cast=float),
    ProfileFieldParser("chance", re.compile(r'(?:🎲(?:\s(?:[Кк]рит\.?\sшанс|[Шш]анс(?:\sкрита)?|[Шш]анс))?|[Кк]рит\.?\sшанс|[Шш]анс\sкрита)\s:?\s([\d.]+)\s%?'), type_cast=float),

    ProfileFieldParser("cores", re.compile(r'🔮\s*Ядер:\s*(\d+)')),
    ProfileFieldParser("rnd", re.compile(r'🪙\s*RND:\s*(\d+)')),
    ProfileFieldParser("research_points", re.compile(r'[🔎🔬]\s*Очки исследования:\s*(\d+)/\d+')),
    ProfileFieldParser("research_max", re.compile(r'[🔎🔬]\s*Очки исследования:\s*\d+/(\d+)')),
    ProfileFieldParser("upgrades", re.compile(r'⚡\s*Доступных улучшений:\s*(\d+)')),

    ProfileFieldParser("race", re.compile(r'🔹\s*([А-ЯЁа-яёA-Za-z]+)\s*\|'), type_cast=str),

    ProfileFieldParser("phys_def", re.compile(r'Физ\.?\s*защита:\s*(\d+)')),
    ProfileFieldParser("magic_def", re.compile(r'Маг\.?\s*защита:\s*(\d+)')),

    ProfileFieldParser("deaths", re.compile(r'Смерти:\s*(\d+)')),
    ProfileFieldParser("kills", re.compile(r'Убийства:\s*(\d+)')),
    ProfileFieldParser("cores_embodied", re.compile(r'Воплощено ядер:\s*(\d+)')),
    ProfileFieldParser("oi_spent", re.compile(r'Количество потраченных ОИ:\s*(\d+)')),
    ProfileFieldParser("fisher_level", re.compile(r'🎣\s*Уровень рыбака:\s*(\d+)')),
    ProfileFieldParser("fish_caught", re.compile(r'🐟\s*Всего поймано рыб:\s*(\d+)')),
]


def parse_profile_text(text: str) -> Dict:
    profile = {
        "level": 0, "exp_current": 0.0, "exp_max": 0.0,
        "hp": 0, "mana": 0, "stamina": 0,
        "strength": 0, "intelligence": 0, "agility": 0,
        "luck": 0, "speed": 0, "crit": 0.0, "crit_dmg": 0.0, "chance": 0.0, "crit_chance": 0.0,
        "min_dmg": 0, "max_dmg": 0, "phys_dmg": 0,
        "min_spec": 0, "max_spec": 0, "mag_dmg": 0,
        "cores": 0, "rnd": 0, "research_points": 0, "research_max": 0,
        "upgrades": 0,
        "race": "", "phys_def": 0, "magic_def": 0,
        "deaths": 0, "kills": 0, "cores_embodied": 0,
        "oi_spent": 0, "fisher_level": 0, "fish_caught": 0
    }

    m_phys = re.search(r'🗡(?:\s(?:[Фф]из\.?\sурон|[Уу]рон|[Аа]така))?\s:?\s(\d+)(?:\s[-–—]\s(\d+))?', text)
    if not m_phys:
        m_phys = re.search(r'(?:[Фф]из\.?\sурон|[Аа]така)\s:?\s(\d+)(?:\s[-–—]\s*(\d+))?', text)
    if not m_phys:
        for line in text.splitlines():
            if 'маг' not in line.lower() and 'спец' not in line.lower():
                m = re.search(r'[Уу]рон\s:?\s(\d+)(?:\s[-–—]\s(\d+))?', line)
                if m:
                    m_phys = m
                    break

    if m_phys:
        v1 = int(m_phys.group(1))
        v2 = int(m_phys.group(2)) if m_phys.group(2) else v1
        profile["min_dmg"] = min(v1, v2)
        profile["max_dmg"] = max(v1, v2)
        profile["phys_dmg"] = profile["max_dmg"]
        
    m_mag = re.search(r'✨(?:\s(?:[Мм]аг\.?\sурон|[Сс]пец\.?\sурон|[Сс]пец\.?|[Сс]пециальный))?\s:?\s(\d+)(?:\s[-–—]\s*(\d+))?', text)
    if not m_mag:
        m_mag = re.search(r'(?:[Мм]аг\.?\sурон|[Сс]пец\.?\sурон|[Сс]пец\.?|[Сс]пециальный)\s:?\s(\d+)(?:\s[-–—]\s(\d+))?', text)

    if m_mag:
        v1 = int(m_mag.group(1))
        v2 = int(m_mag.group(2)) if m_mag.group(2) else v1
        profile["min_spec"] = min(v1, v2)
        profile["max_spec"] = max(v1, v2)
        profile["mag_dmg"] = profile["max_spec"]

    for parser in PROFILE_PARSERS:
        parser.parse(text, profile)

    if profile.get("crit"):
        profile["crit_dmg"] = profile["crit"]
    if profile.get("chance"):
        profile["crit_chance"] = profile["chance"]

    return profile

    for parser in PROFILE_PARSERS:
        parser.parse(text, profile)

    return profile


def parse_tower_messages(fwd: List[Dict]) -> Dict:
    stats = {
        "stone": 0, "sharpening_stone": 0, "wood": 0,
        "strength": 0, "agility": 0, "intelligence": 0,
        "cores_left": 0, "inventory_slots": 0,
        "gold_items": 0, "red_items": 0, "black_items": 0,
        "gear_items": 0, "diamond_items": 0,
        "messages_count": len(fwd),
        "limits": {},
        "op_points": 0,
        "cores_opened": 0
    }

    limited_fwd = fwd[:MAX_FWD_MESSAGES]
    txt = "\n".join(m.get('text', '') for m in limited_fwd)

    if not txt:
        return stats

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
    if sharpening_matches:
        stats["sharpening_stone"] = sum(int(x) for x in sharpening_matches)

    stone_simple = re.findall(r'(?<!заточки )[Кк]амень\s*[xхX](\d+)', txt)
    stone_emoji = re.findall(r'🧱.*?[xх\(]\s*(\d+)', txt)
    stats["stone"] = sum(int(x) for x in stone_simple) + sum(int(x) for x in stone_emoji)

    wood_paren = re.findall(r'[Дд]ревесина\s*\(х(\d+)\)', txt)
    wood_simple = re.findall(r'[Дд]ревесина\s*[xхX](\d+)', txt)
    wood_emoji = re.findall(r'🪵.*?[xх\(]\s*(\d+)', txt)
    stats["wood"] = (sum(int(x) for x in wood_paren)
                     + sum(int(x) for x in wood_simple)
                     + sum(int(x) for x in wood_emoji))

    char_map = {
        "strength": ["💪", "Сила"],
        "agility": ["🌀", "Ловкость"],
        "intelligence": ["🎓", "Интеллект"]
    }

    for stat_key, identifiers in char_map.items():
        emoji, name_ru = identifiers
        for line in lines:
            if emoji in line or name_ru in line:
                val_match = re.search(r'на\s+(\d+)', line)
                count_match = re.search(r'\(х(\d+)\)', line)
                if val_match and count_match:
                    total = int(val_match.group(1)) * int(count_match.group(1))
                    if 'уменьшена' in line.lower() or '⬇️' in line:
                        stats[stat_key] -= total
                    elif 'увеличена' in line.lower() or '⬆️' in line:
                        stats[stat_key] += total

    if cm := re.search(r'🔮\s*Осталось ядер:\s*(\d+)', txt):
        stats["cores_left"] = int(cm.group(1))

    if sl := re.search(r'🎒\s*Свободных слотов инвентаря:\s*(\d+)', txt):
        stats["inventory_slots"] = int(sl.group(1))

    # ВСКРЫТО ЯДЕР
    opened_patterns = [
        r'Вскрыто ядер:\s*(\d+)',
        r'Ядер вскрыто:\s*(\d+)',
        r'Всего вскрыто(?: ядер)?:\s*(\d+)',
        r'🔮\s*Вскрыто:\s*(\d+)',
    ]
    for pattern in opened_patterns:
        matches = re.findall(pattern, txt, re.IGNORECASE)
        if matches:
            stats["cores_opened"] = max(int(x) for x in matches)
            break

    if not stats["cores_opened"]:
        cnt = len(re.findall(r'(?:Вы вскрыли ядро|Вскрытие ядра)', txt, re.IGNORECASE))
        if cnt:
            stats["cores_opened"] = cnt

    limit_pattern = re.compile(r'(💪|🎓|🌀|❤|💙|🤍)\s*([^:]+):\s*\d+\s*\(Предел\s*(\d+)\)')
    for emoji, name, limit_val in limit_pattern.findall(txt):
        stats["limits"][name.strip()] = int(limit_val)

    if op_match := re.search(r'🧬\s*Очки предела\s*\(ОП\):\s*(\d+)', txt):
        stats["op_points"] = int(op_match.group(1))

    return stats