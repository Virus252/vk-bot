import re
from typing import Dict, List
from database import db


def parse_price(price_str: str) -> int:
    """Парсинг цены только в ядрах: '700к', '80к ядер', '80к 🔮' -> 80000"""
    price_str = price_str.strip().lower()
    
    # Извлекаем число и 'к'
    num_match = re.search(r'(\d+)\s*(к)?', price_str)
    if not num_match:
        return 0
    
    num = int(num_match.group(1))
    if num_match.group(2):  
        num *= 1000
    
    return num


def parse_items_from_text(text: str) -> List[Dict]:
    """Парсинг списка товаров из сообщения"""
    items = []
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = re.match(
            r'^(?:\d+\.\s*)?'          # Опциональный номер "1. "
            r'(.+?)'                    # Название предмета (группа 1)
            r'(?:\s*(\+\d+))?'          # Опциональный уровень "+15" (группа 2)
            r'(?:\s*(\[.*?\]))?'        # Опциональные статы "[💙1508]" (группа 3)
            r'\s*-\s*'                  # Разделитель "-"
            r'(.+)$',                   # Цена "700к" или "80к 🔮" (группа 4)
            line, re.IGNORECASE
        )
        
        if match:
            name = match.group(1).strip()
            level = match.group(2) or ""
            stats = match.group(3) or ""
            price_str = match.group(4).strip()
            
            price = parse_price(price_str)
            
            if name and price > 0:
                items.append({
                    "item_name": name,
                    "item_level": level,
                    "item_stats": stats,
                    "price": price
                })
    
    return items


def format_lot_display(lot: Dict) -> str:
    """Красивый вывод лота (всегда в ядрах 🔮)"""
    parts = [f"📦 {lot['item_name']}"]
    if lot.get('item_level'):
        parts.append(lot['item_level'])
    if lot.get('item_stats'):
        parts.append(lot['item_stats'])
    
    price_str = f"{lot['price'] // 1000}к 🔮" if lot['price'] >= 1000 else f"{lot['price']} 🔮"
    parts.append(f"- {price_str}")
    
    return " ".join(parts)


async def get_user_rating_display(vk, user_id: int) -> str:
    """Получение красивого отображения рейтинга пользователя"""
    rating_data = await db.get_user_rating(user_id)
    
    try:
        user_info = vk.users.get(user_ids=user_id, fields=['screen_name'])[0]
        screen = user_info.get('screen_name')
        name = f"@{screen}" if screen else f"{user_info['first_name']} {user_info['last_name']}".strip()
    except Exception:
        name = f"ID: {user_id}"
    
    stars = "⭐" * int(rating_data['rating'])
    half_star = "✨" if rating_data['rating'] % 1 >= 0.5 else ""
    
    return (
        f"👤 {name}\n"
        f"📊 Всего сделок: {rating_data['total_deals']}\n"
        f"✅ Успешных: {rating_data['successful_deals']}\n"
        f"❌ Неудачных: {rating_data['failed_deals']}\n"
        f"🏆 Рейтинг: {rating_data['rating']:.1f}/5.0 {stars}{half_star}"
    )