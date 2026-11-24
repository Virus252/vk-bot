import re
import time
import logging
from datetime import datetime
from database import db
from parsers import parse_profile_text, parse_tower_messages, PROFILE_PARSERS
from classes import check_class_eligibility, format_diff, format_tower_report
from sets import format_category, SET_CATEGORIES
from escrow import parse_items_from_text, format_lot_display, get_user_rating_display
from utils import (check_rate_limit, validate_note_text, is_bot_mentioned,
                   extract_command, increment_metric)
from config import (MAX_NOTE_LENGTH, MAX_GLOBAL_NOTES, MAX_FWD_MESSAGES,
                    MAX_TEXT_LENGTH, STATUS_WAIT_TIMEOUT, NOTES_PER_PAGE,
                    ROLE_HIERARCHY, ROLE_NAMES_RU, ROLE_NAMES_FROM_RU,
                    BOT_OWNER_ID, MUTE_ALLOWED_ROLES, DEFAULT_MUTE_DURATION)

logger = logging.getLogger(__name__)


# ==========================================
# ОТПРАВКА СООБЩЕНИЯ (синхронная!)
# ==========================================
def send_message(vk, peer_id: int, text: str):
    try:
        vk.messages.send(peer_id=peer_id, message=text, random_id=0)
        increment_metric("messages_sent")
    except Exception as e:
        logger.error(f"Ошибка отправки в {peer_id}: {e}")
        increment_metric("send_errors")


# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def resolve_user_id(vk, raw: str):
    """Определение ID пользователя: число, @ник, ник, ссылка, [id123|Имя]"""
    raw = (raw or "").strip()
    if not raw:
        return None, "❌ Не указан пользователь"

    m = re.match(r'^\[id(\d+)\|[^\]]*\]$', raw)
    if m:
        return int(m.group(1)), None

    if re.fullmatch(r'\d+', raw):
        return int(raw), None

    screen = raw.lstrip('@')
    for prefix in ('https://vk.com/', 'http://vk.com/', 'https://m.vk.com/',
                   'http://m.vk.com/', 'vk.com/', 'm.vk.com/'):
        if screen.startswith(prefix):
            screen = screen[len(prefix):]
            break
    screen = screen.split('?')[0].strip('/')

    if screen.startswith('id') and screen[2:].isdigit():
        return int(screen[2:]), None

    if not screen:
        return None, "❌ Не удалось определить пользователя"

    try:
        res = vk.utils.resolveScreenName(screen_name=screen)
    except Exception as e:
        logger.error(f"Ошибка resolveScreenName: {e}")
        return None, f"❌ Не удалось найти пользователя: {e}"

    if not res:
        return None, f"❌ Пользователь '{screen}' не найден"
    if res.get('type') != 'user':
        return None, "❌ Это не пользователь (группа или приложение)"

    return res.get('object_id'), None


def get_display_name(vk, user_id: int) -> str:
    """Красивое имя пользователя"""
    try:
        info = vk.users.get(user_ids=user_id, fields=['screen_name'])[0]
        screen = info.get('screen_name')
        if screen:
            return f"@{screen} (ID: {user_id})"
        full = f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
        return f"{full} (ID: {user_id})" if full else f"ID: {user_id}"
    except Exception as e:
        logger.error(f"Ошибка получения имени пользователя: {e}")
        return f"ID: {user_id}"


def format_duration(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400} дн."
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ч."
    if seconds % 60 == 0:
        return f"{seconds // 60} мин."
    return f"{seconds} сек."


# ==========================================
# ОБРАБОТКА СООБЩЕНИЙ
# ==========================================
async def handle_message(event, vk):
    msg = event.object.get('message', {})
    text = (msg.get('text') or '').strip()
    peer_id = msg.get('peer_id')
    from_id = msg.get('from_id')

    if not peer_id or not from_id:
        return

    if not check_rate_limit(from_id):
        send_message(vk, peer_id, "⚠️ Слишком много запросов. Подождите немного.")
        increment_metric("rate_limited")
        return

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]

    is_chat = peer_id > 2000000000
    await db.cleanup_waiting_states()

    # ==========================================
    # 1. Ответ игрового бота на "Статус"
    # ==========================================
    if is_chat:
        wait_info = await db.get_and_remove_waiting_status(peer_id)
        if wait_info and (time.time() - wait_info["timestamp"]) < STATUS_WAIT_TIMEOUT:
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
                        send_message(vk, peer_id, format_diff(old["data"], new_profile,
                                                             old["timestamp"], current_time_iso))
                    else:
                        eligible = check_class_eligibility(new_profile, status_time_str)
                        race = str(new_profile.get("race", "")).strip()
                        resp = f"📋 Профиль сохранён!\n🧬 Раса: {race if race else '❌ Не определена'}\n"
                        resp += f"🛡 Физ. защита: {new_profile.get('phys_def', 0)} | " \
                                f"🌟 Маг. защита: {new_profile.get('magic_def', 0)}\n"
                        if eligible:
                            resp += "\n🎭 Доступные классы:\n" + "\n".join(f"• {c}" for c in eligible)
                        else:
                            resp += "\n⚠️ Нет доступных классов по текущим статам."
                        send_message(vk, peer_id, resp)

                    increment_metric("status_parsed")
                    return

    # ==========================================
    # 2. Пересланные сообщения
    # ==========================================
    fwd = msg.get('fwd_messages', [])
    if fwd:
        fwd_text = "\n".join(m.get('text', '') for m in fwd[:MAX_FWD_MESSAGES])
        is_tower = bool(re.search(
            r'(Вам выпало:|Камень|Древесина|Осталось ядер|Вскрыто ядер|Башня|Предел|Очки предела)',
            fwd_text))
        is_profile = bool(re.search(r'(Уровень:|Характеристики:|Здоровье:)', fwd_text))

        if is_tower:
            snapshots = await db.get_profile_snapshots(from_id)
            user_profile = snapshots[0]["data"] if snapshots else None

            tower_stats = parse_tower_messages(fwd)
            tr = format_tower_report(tower_stats, user_profile)

            if tr:
                send_message(vk, peer_id, tr)
            else:
                send_message(vk, peer_id, "❌ Не удалось распознать данные Башни или предметы.")

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
                    send_message(vk, peer_id, format_diff(old["data"], np, old["timestamp"], ct))
                else:
                    eligible = check_class_eligibility(np, status_time_str)
                    race = np.get("race") or "не определена"
                    resp = f"📋 Первый профиль сохранён!\n🧬 Раса: {race}\n"
                    resp += f"🛡 Физ. защита: {np.get('phys_def', 0)} | " \
                            f"🌟 Маг. защита: {np.get('magic_def', 0)}\n"
                    if eligible:
                        resp += "\n🎭 Доступные классы:\n" + "\n".join(f"• {c}" for c in eligible)
                    send_message(vk, peer_id, resp)

                increment_metric("profile_parsed")
                return

    # ==========================================
    # 3. Команда "Статус" (тег бота)
    # ==========================================
    if is_chat and re.match(r'^статус$',
                            extract_command(text) if is_bot_mentioned(text) else text,
                            re.IGNORECASE):
        await db.add_waiting_status(peer_id, from_id)
        increment_metric("status_wait")
        return

    # ==========================================
    # 4. Команды (работают и в чатах, и в ЛС)
    # ==========================================
    clean_text = (extract_command(text) if is_bot_mentioned(text) else text).strip()

    if not clean_text.startswith("/"):
        return

    parts = clean_text.split(maxsplit=2)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    arg2 = parts[2].strip() if len(parts) > 2 else ""
    full_args = clean_text[len(parts[0]):].strip()

    # Роль пользователя
    user_role = await db.get_user_role(from_id)
    if from_id == BOT_OWNER_ID and user_role == "Private":
        await db.set_user_role(from_id, "GuildMaster")
        user_role = "GuildMaster"
    user_level = ROLE_HIERARCHY.get(user_role, 1)

    # Определение команд
    is_add_cmd = cmd in ["/add", "/добавить", "/добав", "/заметка"]
    is_list_cmd = cmd in ["/list", "/заметки", "/список", "/летопись"]
    is_del_cmd = cmd in ["/del", "/удалить", "/удал"]
    is_role_cmd = cmd in ["/role", "/роль", "/назначить", "/ранг"]
    is_roles_cmd = cmd in ["/roles", "/роли", "/списокролей", "/ранги"]
    is_mute_cmd = cmd in ["/mute", "/мут", "/заглушить"]
    is_unmute_cmd = cmd in ["/unmute", "/размут", "/снятьмут", "/разглушить"]
    is_myrole_cmd = cmd in ["/myrole", "/мояроль", "/мойранг"]

    # Команды сетов
    is_set_phys_cmd = cmd in ["/сетфиз", "/сетфизический", "/setphys"]
    is_set_mp_cmd = cmd in ["/сетмп", "/сетмана", "/setmp"]
    is_set_hp_cmd = cmd in ["/сехп", "/сетздоровье", "/sethp"]
    is_set_magic_cmd = cmd in ["/сетмаг", "/сетмагический", "/setmagic"]
    is_set_st_cmd = cmd in ["/сетст", "/сетстамина", "/setst"]
    is_set_def_cmd = cmd in ["/сетдеф", "/сетзащита", "/setdef"]

    # === КОМАНДЫ ГАРАНТА ===
    is_sell_cmd = cmd in ["/продажа", "/sell", "/продать"]
    is_lots_cmd = cmd in ["/лоты", "/lots", "/товары"]
    is_buy_cmd = cmd in ["/купить", "/buy"]
    is_inspect_cmd = cmd in ["/осмотр", "/inspect", "/профиль"]
    is_accept_cmd = cmd in ["/принять", "/accept"]
    is_transfer_cmd = cmd in ["/передать", "/transfer"]
    is_pay_cmd = cmd in ["/оплатить", "/pay"]

    is_help_cmd = cmd in ["/help", "/помощь", "/справка"]
    is_start_cmd = cmd in ["/start", "/старт", "/начать"]

    # ========== ГИЛЬДИЯ ==========
    if is_add_cmd:
        if user_level < ROLE_HIERARCHY["Captain"]:
            send_message(vk, peer_id, "❌ Только Капитаны и выше могут оставлять записи в летописи гильдии.")
            return

        if not full_args:
            send_message(vk, peer_id, "❌ Укажите текст: /добавить Текст")
            return
        if not validate_note_text(full_args):
            send_message(vk, peer_id, "❌ Некорректный текст заметки (недопустимые символы)")
            return

        res = await db.add_note_global(from_id, full_args, user_role)
        if res is None:
            send_message(vk, peer_id, f"❌ Текст слишком длинный (макс. {MAX_NOTE_LENGTH})")
        elif res == "limit":
            send_message(vk, peer_id, f"❌ Летопись переполнена (лимит {MAX_GLOBAL_NOTES} записей)")
        else:
            send_message(vk, peer_id, f"✅ Запись #{res['id']} внесена в летопись гильдии!")
            increment_metric("notes_added")

    elif is_list_cmd:
        notes = await db.get_all_notes()
        if not notes:
            send_message(vk, peer_id, "📭 Летопись гильдии пуста. Будьте первым, кто оставит след!")
            return

        t = f"📜 Летопись гильдии ({len(notes)} записей):\n\n"
        for n in notes[:NOTES_PER_PAGE]:
            author_role_name = ROLE_NAMES_RU.get(n['role'], n['role'])
            short_text = n['text'][:50] + "..." if len(n['text']) > 50 else n['text']
            t += f"#{n['id']} | {author_role_name}: {short_text}\n"

        if len(notes) > NOTES_PER_PAGE:
            t += f"\n…и ещё {len(notes) - NOTES_PER_PAGE} записей\n"

        t += "\n💡 /удалить [номер] — удалить запись (если есть права)"
        send_message(vk, peer_id, t)
        increment_metric("notes_listed")

    elif is_del_cmd:
        if user_level < ROLE_HIERARCHY["Deputy"]:
            send_message(vk, peer_id, "❌ Только Зам главы и Глава гильдии могут удалять записи из летописи.")
            return

        if not args:
            send_message(vk, peer_id, "❌ /удалить [номер]")
            return
        try:
            nid = int(args)
        except ValueError:
            send_message(vk, peer_id, "❌ Номер должен быть числом")
            return

        note_info = await db.get_note_by_id(nid)
        if not note_info:
            send_message(vk, peer_id, f"❌ Запись #{nid} не найдена в летописи")
            return

        note_author_level = ROLE_HIERARCHY.get(note_info['role'], 1)

        can_delete = False
        if user_role == "GuildMaster":
            can_delete = True
        elif user_role == "Deputy" and note_author_level < ROLE_HIERARCHY["Deputy"]:
            can_delete = True
        elif note_info['author_id'] == from_id:
            can_delete = True

        if can_delete:
            if await db.delete_note_global(nid):
                send_message(vk, peer_id, f"✅ Страница #{nid} вырвана из летописи")
                increment_metric("notes_deleted")
            else:
                send_message(vk, peer_id, "❌ Ошибка удаления")
        else:
            send_message(vk, peer_id, "❌ У вас нет прав удалять записи этого ранга.")

    elif is_role_cmd:
        if user_role != "GuildMaster":
            send_message(vk, peer_id, "❌ Только Глава гильдии может назначать ранги.")
            return

        if not args or not arg2:
            send_message(vk, peer_id,
                         "❌ Использование: /роль [@ник или id] [ранг]\n"
                         "Примеры:\n"
                         "• /роль 123456789 Капитан\n"
                         "• /роль @wodyano1 Капитан\n"
                         "• /роль vodyano1 Зам главы\n\n"
                         "Ранги: Глава, Зам, Кардинал, Капитан, Лейтенант, Рядовой")
            return

        target_id, err = resolve_user_id(vk, args)
        if err:
            send_message(vk, peer_id, err)
            return

        new_role = ROLE_NAMES_FROM_RU.get(arg2.lower())
        if not new_role:
            send_message(vk, peer_id,
                         "❌ Неизвестный ранг. Доступны: Глава, Зам, Кардинал, Капитан, Лейтенант, Рядовой")
            return

        await db.set_user_role(target_id, new_role)
        ru_role = ROLE_NAMES_RU.get(new_role, new_role)
        send_message(vk, peer_id,
                     f"✅ Пользователю {get_display_name(vk, target_id)} присвоен ранг: {ru_role}")
        increment_metric("roles_assigned")

    elif is_roles_cmd:
        all_roles = await db.get_all_roles()

        if not all_roles:
            send_message(vk, peer_id,
                         "📋 В гильдии пока нет назначенных ролей.\n\n"
                         "💡 Все пользователи по умолчанию — 🪖 Рядовые.\n"
                         "Используйте /роль [@ник] [ранг] для назначения (только Глава).")
            return

        roles_by_rank = {role: [] for role in ROLE_HIERARCHY.keys()}
        for entry in all_roles:
            role = entry['role']
            if role in roles_by_rank:
                roles_by_rank[role].append(entry['user_id'])

        all_user_ids = [uid for uids in roles_by_rank.values() for uid in uids]
        user_names = {}

        if all_user_ids:
            try:
                batch_size = 500
                for i in range(0, len(all_user_ids), batch_size):
                    batch = all_user_ids[i:i + batch_size]
                    users_info = vk.users.get(user_ids=batch, fields=['screen_name'])
                    for u in users_info:
                        uid = u['id']
                        screen = u.get('screen_name')
                        if screen:
                            user_names[uid] = f"@{screen}"
                        else:
                            user_names[uid] = f"{u['first_name']} {u['last_name']}".strip()
            except Exception as e:
                logger.error(f"Ошибка получения имён пользователей: {e}")

        t = "📋 Роли гильдии:\n\n"

        for role_key in ["GuildMaster", "Deputy", "Cardinal", "Captain", "Lieutenant", "Private"]:
            role_name = ROLE_NAMES_RU.get(role_key, role_key)
            users = roles_by_rank.get(role_key, [])

            if users:
                t += f"{role_name} ({len(users)}):\n"
                for uid in users:
                    name = user_names.get(uid, f"ID: {uid}")
                    t += f"  • {name} (ID: {uid})\n"
                t += "\n"

        t += "💡 Все остальные пользователи по умолчанию — 🪖 Рядовые"

        send_message(vk, peer_id, t)
        increment_metric("roles_listed")

    elif is_myrole_cmd:
        ru_role = ROLE_NAMES_RU.get(user_role, user_role)
        send_message(vk, peer_id, f"🎖 Ваш ранг в гильдии: {ru_role}")

    elif is_mute_cmd:
        if not is_chat:
            send_message(vk, peer_id, "❌ Мут работает только в беседах")
            return

        if user_role not in MUTE_ALLOWED_ROLES:
            send_message(vk, peer_id, "❌ Только Глава, Зам главы и Кардинал могут мутить пользователей")
            return

        target_id = None
        reason = ""
        
        # Сначала проверяем, есть ли ответ на сообщение
        reply_msg = msg.get('reply_message')
        if reply_msg:
            target_id = reply_msg.get('from_id')
            reason = full_args.strip()  # Весь текст после команды = причина
        elif args:
            # Старый способ: ID/ник + причина
            target_id, err = resolve_user_id(vk, args)
            if err:
                send_message(vk, peer_id, err)
                return
            reason = arg2.strip()
        else:
            send_message(vk, peer_id,
                         "❌ Укажите пользователя:\n"
                         "• Ответьте на сообщение командой /мут [причина]\n"
                         "• Или: /мут [@ник или id] [причина]\n"
                         f"⏳ Длительность по умолчанию: {format_duration(DEFAULT_MUTE_DURATION)}")
            return

        if not target_id:
            send_message(vk, peer_id, "❌ Не удалось определить пользователя")
            return

        if target_id == from_id:
            send_message(vk, peer_id, "❌ Нельзя мутить себя")
            return

        target_role = await db.get_user_role(target_id)
        target_level = ROLE_HIERARCHY.get(target_role, 1)

        if target_level >= user_level:
            send_message(vk, peer_id, "❌ Нельзя мутить пользователей с равным или высшим рангом")
            return

        try:
            end_date = int(time.time()) + DEFAULT_MUTE_DURATION
            vk.messages.ban(
                peer_id=peer_id,
                owner_id=target_id,
                reason=reason if reason else "Нарушение правил",
                end_date=end_date
            )

            reason_text = f"\n📄 Причина: {reason}" if reason else ""
            send_message(vk, peer_id,
                         f"🔇 Пользователь {get_display_name(vk, target_id)} заглушен "
                         f"на {format_duration(DEFAULT_MUTE_DURATION)}{reason_text}")
            increment_metric("users_muted")

        except Exception as e:
            logger.error(f"Ошибка мута: {e}")
            if "already banned" in str(e).lower():
                send_message(vk, peer_id, "❌ Пользователь уже заглушен")
            else:
                send_message(vk, peer_id,
                             f"❌ Ошибка мута: {e}\n\n"
                             "Убедитесь, что бот — администратор беседы с правом управления участниками")

    elif is_unmute_cmd:
        if not is_chat:
            send_message(vk, peer_id, "❌ Размут работает только в беседах")
            return

        if user_role not in MUTE_ALLOWED_ROLES:
            send_message(vk, peer_id, "❌ Только Глава, Зам главы и Кардинал могут снимать мут")
            return

        target_id = None
        
        # Сначала проверяем, есть ли ответ на сообщение
        reply_msg = msg.get('reply_message')
        if reply_msg:
            target_id = reply_msg.get('from_id')
        elif args:
            target_id, err = resolve_user_id(vk, args)
            if err:
                send_message(vk, peer_id, err)
                return
        else:
            send_message(vk, peer_id,
                         "❌ Укажите пользователя:\n"
                         "• Ответьте на сообщение командой /размут\n"
                         "• Или: /размут [@ник или id]")
            return

        if not target_id:
            send_message(vk, peer_id, "❌ Не удалось определить пользователя")
            return

        try:
            vk.messages.unban(peer_id=peer_id, owner_id=target_id)
            send_message(vk, peer_id, f"🔊 Пользователь {get_display_name(vk, target_id)} разглушен")
            increment_metric("users_unmuted")
        except Exception as e:
            logger.error(f"Ошибка размута: {e}")
            if "not banned" in str(e).lower():
                send_message(vk, peer_id, "❌ Пользователь не заглушен")
            else:
                send_message(vk, peer_id, f"❌ Ошибка размута: {e}")

    # ========== СЕТЫ ==========
    elif is_set_phys_cmd:
        send_message(vk, peer_id, f"🔥 Сеты для физического урона:\n\n{format_category('phys')}")
        increment_metric("sets_viewed")

    elif is_set_mp_cmd:
        send_message(vk, peer_id, f"💙 Сеты для маны:\n\n{format_category('mp')}")
        increment_metric("sets_viewed")

    elif is_set_hp_cmd:
        send_message(vk, peer_id, f"❤️ Сеты для здоровья:\n\n{format_category('hp')}")
        increment_metric("sets_viewed")

    elif is_set_magic_cmd:
        send_message(vk, peer_id, f"🔮 Сеты для магического урона:\n\n{format_category('magic')}")
        increment_metric("sets_viewed")

    elif is_set_st_cmd:
        send_message(vk, peer_id, f"🤍 Сеты для стамины:\n\n{format_category('stamina')}")
        increment_metric("sets_viewed")

    elif is_set_def_cmd:
        send_message(vk, peer_id, f"🛡️ Сеты для защиты:\n\n{format_category('def')}")
        increment_metric("sets_viewed")

    # ========== ГАРАНТОР ==========
    elif is_sell_cmd:
        if not full_args:
            send_message(vk, peer_id,
                         "❌ Укажите товары для продажи. Пример:\n\n"
                         "/продажа\n"
                         "1. 🥼 💠 Мантия Тайн +15 [💙1508 🤍51]-700к\n"
                         "2. ⚙️ Мозговой чип-80к 🔮")
            return

        items = parse_items_from_text(full_args)
        if not items:
            send_message(vk, peer_id, "❌ Не удалось распознать товары. Проверьте формат (Название - Цена).")
            return

        created_ids = []
        for item in items:
            lot_id = await db.create_lot(
                from_id, item['item_name'], item['item_level'],
                item['item_stats'], item['price']
            )
            created_ids.append(lot_id)

        resp = f"✅ Создано {len(created_ids)} лот(ов):\n\n"
        for lot_id in created_ids:
            lot = await db.get_lot_by_id(lot_id)
            resp += f"🆔 {lot['id']} | {format_lot_display(lot)}\n"
        resp += "\n💡 /лоты — посмотреть свои товары\n💡 Другие игроки: /купить [ID]"
        send_message(vk, peer_id, resp)
        increment_metric("lots_created")

    elif is_lots_cmd:
        lots = await db.get_active_lots(from_id)
        if not lots:
            send_message(vk, peer_id, "📭 У вас нет активных лотов. Создайте через /продажа")
            return
        msg = "📦 Ваши активные лоты:\n\n"
        for lot in lots:
            msg += f"🆔 {lot['id']} | {format_lot_display(lot)}\n"
        msg += "\n💡 Для покупки другой игрок должен написать: /купить [ID_лота]"
        send_message(vk, peer_id, msg)
        increment_metric("lots_viewed")

    elif is_buy_cmd:
        if not args:
            send_message(vk, peer_id, "❌ Укажите ID лота. Пример: /купить 5")
            return
        try:
            lot_id = int(args)
        except ValueError:
            send_message(vk, peer_id, "❌ ID лота должен быть числом.")
            return

        lot = await db.get_lot_by_id(lot_id)
        if not lot or lot['status'] != 'active':
            send_message(vk, peer_id, "❌ Лот не найден или уже продан.")
            return
        if lot['seller_id'] == from_id:
            send_message(vk, peer_id, "❌ Нельзя купить свой собственный лот.")
            return

        deal_id = await db.create_deal(lot['seller_id'], from_id)
        await db.link_lot_to_deal(lot_id, deal_id)

        price_str = f"{lot['price'] // 1000}к 🔮" if lot['price'] >= 1000 else f"{lot['price']} 🔮"

        msg = (f"🤝 Сделка #{deal_id} создана!\n\n"
               f"📦 Товар: {lot['item_name']} {lot['item_level']} {lot['item_stats']}\n"
               f"💰 Цена: {price_str}\n"
               f"👤 Продавец: ID {lot['seller_id']}\n"
               f"👤 Покупатель: ID {from_id}\n\n"
               f"Команды:\n"
               f"• /осмотр [ID] — проверить рейтинг\n"
               f"• /принять {deal_id} — согласиться (для обеих сторон)\n"
               f"• /отмена — отменить сделку")
        send_message(vk, peer_id, msg)
        increment_metric("deals_created")

    elif is_inspect_cmd:
        target_id = None
        
        # Сначала проверяем, есть ли ответ на сообщение
        reply_msg = msg.get('reply_message')
        if reply_msg:
            target_id = reply_msg.get('from_id')
        
        # Если ответа нет — пробуем ID из аргументов
        if not target_id:
            if not args:
                send_message(vk, peer_id, 
                            "❌ Укажите пользователя:\n"
                            "• Ответьте на сообщение командой /осмотр\n"
                            "• Или: /осмотр 123456789\n"
                            "• Или: /осмотр @wodyano1")
                return
            
            target_id, err = resolve_user_id(vk, args)
            if err:
                send_message(vk, peer_id, err)
                return
        
        if not target_id:
            send_message(vk, peer_id, "❌ Не удалось определить пользователя")
            return
        
        rating_msg = await get_user_rating_display(vk, target_id)
        send_message(vk, peer_id, rating_msg)
        increment_metric("users_inspected")

    elif is_accept_cmd:
        if not args:
            send_message(vk, peer_id, "❌ Укажите ID сделки. Пример: /принять 15")
            return
        try:
            deal_id = int(args)
        except ValueError:
            send_message(vk, peer_id, "❌ ID сделки должен быть числом.")
            return

        deal = await db.get_deal_by_id(deal_id)
        if not deal:
            send_message(vk, peer_id, "❌ Сделка не найдена.")
            return
        if from_id not in [deal['seller_id'], deal['buyer_id']]:
            send_message(vk, peer_id, "❌ Вы не участвуете в этой сделке.")
            return

        if deal['status'] == 'pending':
            await db.update_deal_status(deal_id, 'accepted')
            send_message(vk, peer_id,
                         f"✅ Вы подтвердили сделку #{deal_id}. Ожидается подтверждение второй стороны.\n\n"
                         f"После принятия обоими:\n"
                         f"• Продавец: /передать {deal_id}\n"
                         f"• Покупатель: /оплатить {deal_id}")
        elif deal['status'] == 'accepted':
            send_message(vk, peer_id,
                         f"⏳ Сделка #{deal_id} уже ожидает действий:\n"
                         f"• Продавец: /передать {deal_id}\n"
                         f"• Покупатель: /оплатить {deal_id}")
        else:
            send_message(vk, peer_id, f"❌ Сделка #{deal_id} уже завершена или отменена.")

    elif is_transfer_cmd:
        if not args:
            send_message(vk, peer_id, "❌ Укажите ID сделки.")
            return
        try:
            deal_id = int(args)
        except ValueError:
            send_message(vk, peer_id, "❌ ID должен быть числом.")
            return

        deal = await db.get_deal_by_id(deal_id)
        if not deal or from_id != deal['seller_id']:
            send_message(vk, peer_id, "❌ Только продавец может использовать эту команду для этой сделки.")
            return

        if deal['status'] == 'accepted':
            await db.update_deal_status(deal_id, 'transferred')
            send_message(vk, peer_id,
                         f"✅ Вы подтвердили передачу товара в сделке #{deal_id}.\n"
                         f"Ожидается оплата от покупателя: /оплатить {deal_id}")
        elif deal['status'] == 'paid':
            await db.update_deal_status(deal_id, 'completed')
            await db.update_user_rating(deal['seller_id'], True)
            await db.update_user_rating(deal['buyer_id'], True)
            send_message(vk, peer_id,
                         f"🎉 Сделка #{deal_id} успешно завершена!\n"
                         f"Товар передан, оплата получена.\n"
                         f"Ваш рейтинг обновлён.")
        else:
            send_message(vk, peer_id, f"❌ Неверный статус сделки #{deal_id} для этой команды.")

    elif is_pay_cmd:
        if not args:
            send_message(vk, peer_id, "❌ Укажите ID сделки.")
            return
        try:
            deal_id = int(args)
        except ValueError:
            send_message(vk, peer_id, "❌ ID должен быть числом.")
            return

        deal = await db.get_deal_by_id(deal_id)
        if not deal or from_id != deal['buyer_id']:
            send_message(vk, peer_id, "❌ Только покупатель может использовать эту команду для этой сделки.")
            return

        if deal['status'] == 'accepted':
            await db.update_deal_status(deal_id, 'paid')
            send_message(vk, peer_id,
                         f"✅ Вы подтвердили оплату в сделке #{deal_id}.\n"
                         f"Ожидается подтверждение передачи товара от продавца: /передать {deal_id}")
        elif deal['status'] == 'transferred':
            await db.update_deal_status(deal_id, 'completed')
            await db.update_user_rating(deal['seller_id'], True)
            await db.update_user_rating(deal['buyer_id'], True)
            send_message(vk, peer_id,
                         f"🎉 Сделка #{deal_id} успешно завершена!\n"
                         f"Товар передан, оплата получена.\n"
                         f"Ваш рейтинг обновлён.")
        else:
            send_message(vk, peer_id, f"❌ Неверный статус сделки #{deal_id} для этой команды.")

    # ========== СПРАВКА ==========
    elif is_help_cmd:
        h = ("📖 Команды гильдии:\n"
             "/добавить [текст] — внести запись (Капитан+)\n"
             "/заметки — читать летопись (Все)\n"
             "/удалить [номер] — удалить запись (Зам главы+)\n"
             "/роль [@ник или id] [ранг] — назначить ранг (Глава)\n"
             "/роли — посмотреть всех с ролями (Все)\n"
             "/мояроль — показать свой ранг\n"
             "/мут — заглушить пользователя (ответьте на сообщение)\n"
             "/мут [@ник или id] [причина] — заглушить вручную (Глава/Зам/Кардинал)\n"
             "/размут — снять заглушение (ответьте на сообщение)\n"
             "/размут [@ник или id] — снять заглушение вручную (Глава/Зам/Кардинал)\n\n"
             "🎖 Ранги: 👑 Глава → ⚔️ Зам → 📿 Кардинал → "
             "🛡️ Капитан → 🎖️ Лейтенант → 🪖 Рядовой\n\n"
             "🏰 Tower of Random:\n"
             "• Перешлите ядра — посчитаю\n"
             "• Перешлите статы — покажу классы\n"
             "• '@бот статус' — динамика профиля\n\n"
             "⚔️ Сеты брони:\n"
             "• /сетФиз, /сетМп, /сетХп, /сетМаг, /сетСт, /сетДеф\n\n"
             "🤝 Гарант сделок:\n"
             "• /продажа [список] — выставить товары\n"
             "• /лоты — мои товары\n"
             "• /купить [ID] — купить лот\n"
             "• /осмотр — рейтинг пользователя\n"
             "• /принять [ID] — согласиться на сделку\n"
             "• /передать [ID] — продавец подтверждает передачу\n"
             "• /оплатить [ID] — покупатель подтверждает оплату\n\n"
             "💡 Все цены в ядрах 🔮")
        send_message(vk, peer_id, h)
        increment_metric("help_shown")

    elif is_start_cmd:
        send_message(vk, peer_id, "👋 Приветствую в гильдии! Напиши /помощь для списка команд")
        increment_metric("start_shown")

    else:
        send_message(vk, peer_id, "❓ Неизвестная команда. Напиши /помощь")