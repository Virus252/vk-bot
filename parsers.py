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
                profile[self.key] = self.type_cast(match.group(self.group_index))
                return True
            except (ValueError, IndexError):
                pass
        return False

PROFILE_PARSERS = [
    ProfileFieldParser("level", re.compile(r'Уровень:\s*(\d+)')),
    ProfileFieldParser("exp_current", re.compile(r'Опыт:\s*([\d.]+)кк/[\d.]+кк'), type_cast=float),
    ProfileFieldParser("exp_max", re.compile(r'Опыт:\s*[\d.]+кк/([\d.]+)кк'), type_cast=float),
    ProfileFieldParser("hp", re.compile(r'❤\s Здоровье:\s \d+/(\d+)')),
    ProfileFieldParser("mana", re.compile(r'💙\s Мана:\s \d+/(\d+)')),
    ProfileFieldParser("stamina", re.compile(r'🤍\s Стамина:\s \d+/(\d+)')),
    ProfileFieldParser("strength", re.compile(r'💪\s Сила:\s (\d+)')),
    ProfileFieldParser("intelligence", re.compile(r'🎓\s Интеллект:\s (\d+)')),
    ProfileFieldParser("agility", re.compile(r'🌀\s Ловкость:\s (\d+)')),
    ProfileFieldParser("luck", re.compile(r'🍀\s Удача:\s (\d+)')),
    ProfileFieldParser("speed", re.compile(r'⚡\s Скорость:\s (\d+)')),
    ProfileFieldParser("crit", re.compile(r'💥\s Крит:\s ([\d.]+)%'), type_cast=float),
    ProfileFieldParser("chance", re.compile(r'🎲\s Шанс:\s ([\d.]+)%'), type_cast=float),
    ProfileFieldParser("cores", re.compile(r'🔮\s Ядер:\s (\d+)')),
    ProfileFieldParser("rnd", re.compile(r'🪙\s RND:\s (\d+)')),
    ProfileFieldParser("research_points", re.compile(r'🔬\s Очки исследования:\s (\d+)/\d+')),
    ProfileFieldParser("research_max", re.compile(r'🔬\s Очки исследования:\s \d+/(\d+)')),
    ProfileFieldParser("upgrades", re.compile(r'⚡\s Доступных улучшений:\s (\d+)')),
    ProfileFieldParser("race", re.compile(r'Раса:\s*(\S+)'), type_cast=str),
    ProfileFieldParser("phys_def", re.compile(r'Физ.?\s защита:\s (\d+)')),
    ProfileFieldParser("magic_def", re.compile(r'Маг.?\s защита:\s (\d+)')),
]

def parse_profile_text(text: str) -> Dict:
    """Парсинг текста профиля"""
    profile = {
        "level": 0, "exp_current": 0.0, "exp_max": 0.0,
        "hp": 0, "mana": 0, "stamina": 0,
        "strength": 0, "intelligence": 0, "agility": 0,
        "luck": 0, "speed": 0, "crit": 0.0, "chance": 0.0,
        "min_dmg": 0, "max_dmg": 0, "min_spec": 0, "max_spec": 0,
        "cores": 0, "rnd": 0, "research_points": 0, "research_max": 0,
        "upgrades": 0,
        "race": "", "phys_def": 0, "magic_def": 0
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
        if parser.key in ["min_dmg", "max_dmg"] and dmg_match:
            continue
        parser.parse(text, profile)
    
    return profile

def parse_tower_messages(fwd: List[Dict]) -> Dict:
    """Парсинг сообщений Башни"""
    stats = {
        "stone": 0, "sharpening_stone": 0, "wood": 0,
        "strength": 0, "agility": 0, "intelligence": 0,
        "cores_left": 0, "inventory_slots": 0,
        "gold_items": 0, "red_items": 0, "black_items": 0,
        "gear_items": 0, "diamond_items": 0,
        "messages_count": len(fwd),
        "limits": {},
        "op_points": 0
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
    stats["wood"] = sum(int(x) for x in wood_paren) + sum(int(x) for x in wood_simple) + sum(int(x) for x in wood_emoji)
    
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
    
    limit_pattern = re.compile(r'(💪|🎓|🌀|❤|💙|🤍)\s*([^:]+):\s*\d+\s*\(Предел\s*(\d+)\)')
    limits_found = limit_pattern.findall(txt)
    if limits_found:
        for emoji, name, limit_val in limits_found:
            name_clean = name.strip()
            stats["limits"][name_clean] = int(limit_val)
    
    op_match = re.search(r'🧬\s*Очки предела\s*\(ОП\):\s*(\d+)', txt)
    if op_match:
        stats["op_points"] = int(op_match.group(1))
    
    return stats