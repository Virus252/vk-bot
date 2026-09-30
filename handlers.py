import re
import logging
from datetime import datetime
from typing import Dict, List
from database import db
from parsers import parse_profile_text, parse_tower_messages
from classes import check_class_eligibility, format_diff, format_tower_report
from utils import check_rate_limit, validate_note_text, is_bot_mentioned, extract_command, increment_metric
from config import MAX_NOTES_PER_USER, MAX_NOTE_LENGTH, MAX_FWD_MESSAGES, MAX_TEXT_LENGTH, STATUS_WAIT_TIMEOUT

logger = logging.getLogger(__name__)

async def send_message(vk, peer_id: int, text: str):
    """Отправка сообщения"""
    try:
        await vk.messages.send(peer_id=peer_id, message=text, random_id=0)
        increment_metric("messages_sent")
    except Exception as e:
        logger.error(f"Ошибка отправки в {peer_id}: {e}")
        increment_metric("send_errors")

async def handle_message(event, vk):
    """Обработка входящего сообщения"""
    msg = event.object.get('message', {})
    text = msg.get('text', '').strip()
    peer_id = msg.get('peer_id')
    from_id = msg.get('from_id')
    
    if not peer_id or not from_id:
        return
    
    # Rate limiting
    if not check_rate_limit(from_id):
        await send_message(vk, peer_id, "⚠️ Слишком много запросов. Подождите немного.")
        increment_metric("rate_limited")
        return
    
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
    
    is_chat = peer_id > 2000000000
    
    await db.cleanup_waiting_states()
    
    # 1. Ответ игрового бота на "Статус" (в чате)
    if is_chat:
        wait_info = await db.get_and_remove_waiting_status(peer_id)
        if wait_info and (datetime.now().timestamp() - wait_info["timestamp"]) < STATUS_WAIT_TIMEOUT:
            from parsers import PROFILE_PARSERS
            has_level = any(p.key == "level" and p.pattern.search(text) for p in PROFILE_PARSERS)
            has_stats = any(p.key in ["strength", "hp"] and p.pattern.search(text) for p in PROFILE_PARSERS)
            
            if has_level and has_stats:
                time_match = re.search(r'(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})', text)
                status_time_str = time_match.group(1) if time_match else ""
                current_time_iso = datetime.now().isoformat()
                
                new_profile = parse_profile_text(text)
                
                if new_profile["level"] > 0:
                    await db.save_profile_snapshot(wait_info["user_id"], new_profile, current_time_iso)
                    snapshots = await db.get_profile_snapshots(wait_info["user_id"])
                    
                    if len(snapshots) >= 2:
                        old = snapshots[1]
                        await send_message(vk, peer_id, format_diff(old["data"], new_profile, old["timestamp"], current_time_iso))
                    else:
                        eligible = check_class_eligibility(new_profile, status_time_str)
                        race = new_profile.get("race", "").strip()
                        resp = f"📋 Профиль сохранён!\n🧬 Раса: {race if race else '❌ Не определена'}\n"
                        if eligible:
                            resp += "\n🎭 Доступные классы:\n"
                            resp += "\n".join(f"• {c}" for c in eligible)
                        else:
                            resp += "\n⚠️ Нет доступных классов по текущим статам."
                        await send_message(vk, peer_id, resp)
                    
                    increment_metric("status_parsed")
                    return
    
    # 2. Пересланные сообщения
    fwd = msg.get('fwd_messages', [])
    if fwd:
        fwd_text = "\n".join(m.get('text', '') for m in fwd[:MAX_FWD_MESSAGES])
        is_tower = bool(re.search(r'(Вам выпало:|Камень|Древесина|Осталось ядер|Башня|Предел|Очки предела)', fwd_text))
        is_profile = bool(re.search(r'(Уровень:|Характеристики:|Здоровье:)', fwd_text))
        
        if is_tower:
            target_user_id = from_id
            snapshots = await db.get_profile_snapshots(target_user_id)
            user_profile = snapshots[0]["data"] if snapshots else None
            
            tower_stats = parse_tower_messages(fwd)
            tr = format_tower_report(tower_stats, user_profile)
            
            if tr:
                await send_message(vk, peer_id, tr)
            else:
                await send_message(vk, peer_id, "❌ Не удалось распознать данные Башни или предметы.")
            
            increment_metric("tower_parsed")
            return
        
        elif is_profile:
            if is_chat and not is_bot_mentioned(text):
                pass
            else:
                ct = datetime.now().isoformat()
                np = parse_profile_text(fwd_text)
                time_match = re.search(r'(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})', fwd_text)
                status_time_str = time_match.group(1) if time_match else ""
                
                await db.save_profile_snapshot(from_id, np, ct)
                snapshots = await db.get_profile_snapshots(from_id)
                
                if len(snapshots) >= 2:
                    old = snapshots[1]
                    await send_message(vk, peer_id, format_diff(old["data"], np, old["timestamp"], ct))
                else:
                    eligible = check_class_eligibility(np, status_time_str)
                    race = np.get("race", "не определена")
                    resp = f"📋 Первый профиль сохранён!\n🧬 Раса: {race}\n"
                    if eligible:
                        resp += "\n🎭 Доступные классы:\n"
                        resp += "\n".join(f"• {c}" for c in eligible)
                    await send_message(vk, peer_id, resp)
                
                increment_metric("profile_parsed")
                return
    
    # 3. Команда "Статус" (тег бота)
    if is_chat and re.match(r'^статус$', extract_command(text) if is_bot_mentioned(text) else text, re.IGNORECASE):
        await db.add_waiting_status(peer_id, from_id)
        increment_metric("status_wait")
        return
    
    # 4. Обычные команды
    if is_chat:
        is_slash_command = text.startswith('/')
        if not is_bot_mentioned(text) and not is_slash_command:
            return
        
        if is_bot_mentioned(text):
            text = extract_command(text)
        
        if not text.startswith("/"):
            return
        
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        
        if cmd == "/add":
            if not args:
                await send_message(vk, peer_id, "❌ Укажите текст: /add Текст")
                return
            
            if not validate_note_text(args):
                await send_message(vk, peer_id, "❌ Некорректный текст заметки")
                return
            
            res = await db.add_note(from_id, args)
            if res is None:
                await send_message(vk, peer_id, f"❌ Текст слишком длинный (макс. {MAX_NOTE_LENGTH})")
            elif res == "limit":
                await send_message(vk, peer_id, f"❌ Лимит заметок ({MAX_NOTES_PER_USER})")
            else:
                await send_message(vk, peer_id, f"✅ Заметка #{res['id']} добавлена!")
                increment_metric("notes_added")
        
        elif cmd == "/list":
            notes = await db.get_notes(from_id)
            if not notes:
                await send_message(vk, peer_id, "📭 Нет заметок. /add [текст]")
                return
            
            t = "📋 Заметки:\n\n"
            for n in notes:
                t += f"#{n['id']} | {n['text']} ({n['created_at']})\n"
            t += "\n/del [номер] — удалить"
            await send_message(vk, peer_id, t)
            increment_metric("notes_listed")
        
        elif cmd == "/del":
            if not args:
                await send_message(vk, peer_id, "❌ /del [номер]")
                return
            
            try:
                nid = int(args)
            except ValueError:
                await send_message(vk, peer_id, "❌ Номер должен быть числом")
                return
            
            if await db.delete_note(from_id, nid):
                await send_message(vk, peer_id, f"✅ Заметка #{nid} удалена")
                increment_metric("notes_deleted")
            else:
                await send_message(vk, peer_id, f"❌ Заметка #{nid} не найдена")
        
        elif cmd == "/help":
            h = ("📖 Команды:\n/add [текст]\n/list\n/del [номер]\n/help\n\n"
                 "🏰 Tower of Random:\n• Перешлите ядра — посчитаю (тегать не надо)\n"
                 "• Перешлите статы с пределами — покажу доступные классы\n"
                 "• '@бот статус' — дождусь ответа и покажу динамику")
            if is_chat:
                h += "\n\n💡 Команды работают и без тега, если начинаются со слэша (/)"
            await send_message(vk, peer_id, h)
            increment_metric("help_shown")
        
        elif cmd == "/start":
            await send_message(vk, peer_id, "👋 Привет! Напиши /help")
            increment_metric("start_shown")
        
        else:
            await send_message(vk, peer_id, "❓ Неизвестная команда. /help")