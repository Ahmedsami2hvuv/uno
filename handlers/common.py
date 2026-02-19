from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database import db_query
from i18n import t, get_lang, set_lang, TEXTS
import random, string, json, asyncio

router = Router()

replay_data = {}
pending_invites = {}
pending_next_round = {}
next_round_ready = {}
friend_invite_selections = {}
kick_selections = {}

class RoomStates(StatesGroup):
    wait_for_code = State()
    reg_ask_username = State()
    reg_ask_password = State()
    reg_ask_name = State()
    upgrade_username = State()
    upgrade_password = State()
    search_user = State()
    edit_name = State()
    edit_password = State()
    register_name = State()
    register_password = State()
    login_name = State()
    login_password = State()
    complete_profile_name = State()
    complete_profile_password = State()

persistent_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="/start"), KeyboardButton(text="🧹 تنظيف الرسائل")]],
    resize_keyboard=True,
    persistent=True
)


async def show_main_menu(message, name, user_id=None, cleanup: bool = False):
    uid = user_id or (message.from_user.id if hasattr(message, "from_user") else 0)
    kb = [
        [InlineKeyboardButton(text=t(uid, "btn_random_play"), callback_data="random_play")],
        [InlineKeyboardButton(text=t(uid, "btn_play_friends"), callback_data="play_friends")],
        [InlineKeyboardButton(text=t(uid, "btn_friends"), callback_data="social_menu")],
        [InlineKeyboardButton(text=t(uid, "btn_my_account"), callback_data="my_account"),
         InlineKeyboardButton(text=t(uid, "btn_calculator"), callback_data="calc_start")],
        [InlineKeyboardButton(text=t(uid, "btn_rules"), callback_data="rules")],
        [InlineKeyboardButton(text=t(uid, "btn_language"), callback_data="change_lang")],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    msg_text = t(uid, "main_menu", name=name)

    async def _cleanup_last_messages(msg_obj, limit=15):
        if not cleanup:
            return
        try:
            last_id = msg_obj.message_id
            for mid in range(last_id, max(last_id - limit, 1), -1):
                try:
                    await msg_obj.bot.delete_message(msg_obj.chat.id, mid)
                except:
                    pass
        except:
            pass

    if isinstance(message, types.CallbackQuery):
        await _cleanup_last_messages(message.message, limit=15)
        try:
            await message.message.edit_text(msg_text, reply_markup=markup)
        except:
            await message.message.answer(msg_text, reply_markup=markup)
    else:
        await _cleanup_last_messages(message, limit=15)
        await message.answer(msg_text, reply_markup=markup)


@router.message(F.text == "🧹 تنظيف الرسائل")
async def clean_chat_messages(message: types.Message):
    chat_id = message.chat.id
    current_msg_id = message.message_id
    for mid in range(current_msg_id, max(current_msg_id - 200, 0), -1):
        try:
            await message.bot.delete_message(chat_id, mid)
        except:
            pass
    name = message.from_user.full_name
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    if user:
        name = user[0]['player_name']
    await show_main_menu(message, name, user_id=message.from_user.id, cleanup=False)


def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))


@router.message(F.text.in_(["ستارت", "/start"]))
async def quick_start_button(message: types.Message):
    try:
        await message.delete()
    except:
        pass
    await show_main_menu(message, message.from_user.full_name, user_id=message.from_user.id, cleanup=True)


@router.callback_query(F.data == "play_friends")
async def on_play_friends(c: types.CallbackQuery):
    uid = c.from_user.id
    text = "🎮 **اللعب مع الأصدقاء**\n\nاختر:"
    kb = [
        [InlineKeyboardButton(text="➕ إنشاء غرفة", callback_data="room_create_start")],
        [InlineKeyboardButton(text="🔑 دخول بكود", callback_data="room_join_input")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="home")]
    ]
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")


@router.message(RoomStates.upgrade_username)
async def process_username_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.text.strip().lower()
    if not username.isalnum() or len(username) < 3:
        return await message.answer("❌ اليوزر نيم يجب أن يكون أحرف إنجليزية وأرقام فقط (3 أحرف على الأقل):")
    check = db_query("SELECT user_id FROM users WHERE username_key = %s", (username,))
    if check:
        return await message.answer(t(user_id, "username_taken"))
    await state.update_data(chosen_username=username)
    await message.answer(t(user_id, "ask_password_key"))
    current_state = await state.get_state()
    if current_state == RoomStates.reg_ask_username:
        await state.set_state(RoomStates.reg_ask_password)
    else:
        await state.set_state(RoomStates.upgrade_password)


@router.message(RoomStates.upgrade_password)
async def process_password_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    password = message.text.strip()
    if len(password) < 4:
        return await message.answer(t(user_id, "password_too_short"))
    data = await state.get_data()
    username = data['chosen_username']
    current_state = await state.get_state()
    if current_state == RoomStates.upgrade_password:
        db_query("UPDATE users SET username_key = %s, password_key = %s WHERE user_id = %s",
                 (username, password, user_id), commit=True)
        user_info = db_query("SELECT player_name FROM users WHERE user_id = %s", (user_id,))
        p_name = user_info[0]['player_name'] if user_info else "لاعب"
        await message.answer(t(user_id, "reg_success", name=p_name, username=username))
        await state.clear()
        await show_main_menu(message, p_name, user_id)
    else:
        await state.update_data(chosen_password=password)
        await message.answer(t(user_id, "ask_name"))
        await state.set_state(RoomStates.reg_ask_name)


@router.message(RoomStates.reg_ask_name)
async def process_final_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text.strip()[:20]
    if len(name) < 2:
        return await message.answer(t(user_id, "name_too_short"))
    data = await state.get_data()
    username = data['chosen_username']
    password = data['chosen_password']
    db_query("""INSERT INTO users (user_id, username_key, password_key, player_name, is_registered)
                VALUES (%s, %s, %s, %s, TRUE)""",
             (user_id, username, password, name), commit=True)
    await message.answer(t(user_id, "reg_success", name=name, username=username))
    await state.clear()
    await show_main_menu(message, name, user_id)


@router.callback_query(F.data.startswith("set_lang_"))
async def set_lang_callback(c: types.CallbackQuery, state: FSMContext):
    lang = c.data.split("_")[-1]
    uid = c.from_user.id
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if user:
        db_query("UPDATE users SET language = %s WHERE user_id = %s", (lang, uid), commit=True)
    else:
        db_query("INSERT INTO users (user_id, username, language, is_registered) VALUES (%s, %s, %s, FALSE)",
                 (uid, c.from_user.username or '', lang), commit=True)
    set_lang(uid, lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "btn_register"), callback_data="auth_register")],
        [InlineKeyboardButton(text=t(uid, "btn_login"), callback_data="auth_login")]
    ])
    await c.message.edit_text(t(uid, "welcome_new"), reply_markup=kb)


@router.callback_query(F.data == "cp_name_ok")
async def cp_name_ok(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    await c.message.edit_text(t(uid, "ask_password"))
    await state.set_state(RoomStates.complete_profile_password)


@router.callback_query(F.data == "cp_edit_name")
async def cp_edit_name(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    await c.message.edit_text(t(uid, "ask_name"))
    await state.set_state(RoomStates.complete_profile_name)


@router.message(RoomStates.complete_profile_name)
async def complete_profile_name_handler(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    name = message.text.strip()
    if not name or len(name) < 2:
        return await message.answer(t(uid, "name_too_short"))
    if len(name) > 20:
        return await message.answer(t(uid, "name_too_long"))
    existing = db_query("SELECT * FROM users WHERE player_name = %s AND user_id != %s", (name, uid))
    if existing:
        return await message.answer(t(uid, "name_taken"))
    db_query("UPDATE users SET player_name = %s WHERE user_id = %s", (name, uid), commit=True)
    await message.answer(t(uid, "ask_password"))
    await state.set_state(RoomStates.complete_profile_password)


@router.message(RoomStates.complete_profile_password)
async def complete_profile_password_handler(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    password = message.text.strip()
    if len(password) < 4:
        return await message.answer(t(uid, "password_too_short"))
    db_query("UPDATE users SET password = %s WHERE user_id = %s", (password, uid), commit=True)
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    name = user[0]['player_name'] if user else 'Player'
    data = await state.get_data()
    pending_join = data.get('pending_join')
    await state.clear()
    await message.answer(t(uid, "profile_complete", name=name, password=password))
    if pending_join:
        user_data = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
        if user_data:
            await _join_room_by_code(message, pending_join, user_data[0])
            return


async def _join_room_by_code(message, code, user_data):
    uid = message.from_user.id
    room = db_query("SELECT * FROM rooms WHERE room_id = %s AND status = 'waiting'", (code,))
    if not room:
        await message.answer(t(uid, "room_not_found"))
        await show_main_menu(message, user_data['player_name'], uid)
        return
    existing = db_query("SELECT * FROM room_players WHERE room_id = %s AND user_id = %s", (code, uid))
    if existing:
        return await message.answer(t(uid, "already_in_room"))
    p_count = db_query("SELECT count(*) as count FROM room_players WHERE room_id = %s", (code,))[0]['count']
    max_p = room[0]['max_players']
    if p_count >= max_p:
        await message.answer(t(uid, "room_full"))
        await show_main_menu(message, user_data['player_name'], uid)
        return
    u_name = user_data['player_name']
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)",
             (code, uid, u_name), commit=True)
    p_count += 1
    creator_id = room[0]['creator_id']
    all_in_room = db_query("SELECT user_id, player_name FROM room_players WHERE room_id = %s", (code,))
    num_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    players_list = ""
    for idx, rp in enumerate(all_in_room):
        marker = num_emojis[idx] if idx < len(num_emojis) else '👤'
        players_list += f"{marker} {rp['player_name']}\n"
    if p_count >= max_p:
        db_query("UPDATE rooms SET status = 'playing' WHERE room_id = %s", (code,), commit=True)
        all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
        if max_p == 2:
            for p in all_players:
                try:
                    await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_2p"))
                except:
                    pass
            await asyncio.sleep(0.5)
            from handlers.room_2p import start_new_round
            await start_new_round(code, message.bot, start_turn_idx=0)
        else:
            for p in all_players:
                try:
                    await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_multi", n=max_p))
                except:
                    pass
            await asyncio.sleep(0.5)
            from handlers.room_multi import start_game_multi
            await start_game_multi(code, message.bot)
    else:
        wait_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
        ])
        await message.answer(t(uid, "player_joined", name=u_name, count=p_count, max=max_p, list=players_list), reply_markup=wait_kb)
        try:
            notify_text = t(creator_id, "player_joined", name=u_name, count=p_count, max=max_p, list=players_list)
            notify_text += t(creator_id, "waiting_players", n=max_p - p_count)
            await message.bot.send_message(creator_id, notify_text, reply_markup=wait_kb)
        except:
            pass


@router.callback_query(F.data == "auth_register")
async def auth_register(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    await c.message.edit_text(t(uid, "ask_name"))
    await state.set_state(RoomStates.register_name)


@router.message(RoomStates.register_name)
async def register_name(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    name = message.text.strip()
    if not name or len(name) < 2:
        return await message.answer(t(uid, "name_too_short"))
    if len(name) > 20:
        return await message.answer(t(uid, "name_too_long"))
    existing = db_query("SELECT * FROM users WHERE player_name = %s", (name,))
    if existing:
        return await message.answer(t(uid, "name_taken"))
    await state.update_data(reg_name=name)
    await message.answer(t(uid, "ask_password"))
    await state.set_state(RoomStates.register_password)


@router.message(RoomStates.register_password)
async def register_password(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    password = message.text.strip()
    if len(password) < 4:
        return await message.answer(t(uid, "password_too_short"))
    data = await state.get_data()
    name = data.get('reg_name', 'Player')
    lang = get_lang(uid)
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if user:
        db_query("UPDATE users SET player_name = %s, password = %s, is_registered = TRUE, language = %s WHERE user_id = %s",
                 (name, password, lang, uid), commit=True)
    else:
        db_query("INSERT INTO users (user_id, username, player_name, password, is_registered, language) VALUES (%s, %s, %s, %s, TRUE, %s)",
                 (uid, message.from_user.username or '', name, password, lang), commit=True)
    pending_join = data.get('pending_join')
    await state.clear()
    await message.answer(t(uid, "register_success", name=name, password=password))
    if pending_join:
        user_data = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
        if user_data:
            await _join_room_by_code(message, pending_join, user_data[0])
            return


@router.callback_query(F.data == "auth_login")
async def auth_login(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    await c.message.edit_text(t(uid, "login_ask_name"))
    await state.set_state(RoomStates.login_name)


@router.message(RoomStates.login_name)
async def login_name(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    name = message.text.strip()
    user = db_query("SELECT * FROM users WHERE player_name = %s", (name,))
    if not user:
        return await message.answer(t(uid, "login_fail"))
    if not user[0].get('password'):
        await message.answer(t(uid, "login_fail"))
        await state.clear()
        return
    await state.update_data(login_target_name=name)
    await message.answer(t(uid, "login_ask_password"))
    await state.set_state(RoomStates.login_password)


@router.message(RoomStates.login_password)
async def login_password(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()
    name = data.get('login_target_name')
    user = db_query("SELECT * FROM users WHERE player_name = %s", (name,))
    if not user:
        await message.answer(t(uid, "login_fail"))
        await state.clear()
        return
    if message.text.strip() != user[0].get('password', ''):
        return await message.answer(t(uid, "login_fail"))
    db_query("UPDATE users SET user_id = %s, username = %s, is_registered = TRUE WHERE player_name = %s",
             (uid, message.from_user.username or '', name), commit=True)
    data_state = await state.get_data()
    pending_join = data_state.get('pending_join')
    await state.clear()
    await message.answer(t(uid, "login_success", name=name))
    if pending_join:
        user_data = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
        if user_data:
            await _join_room_by_code(message, pending_join, user_data[0])
            return
    await show_main_menu(message, name, user_id=uid)


@router.callback_query(F.data == "random_play")
async def menu_random(c: types.CallbackQuery):
    uid = c.from_user.id
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if not user:
        return await c.answer(t(uid, "room_not_found"), show_alert=True)
    waiting = db_query("""
        SELECT r.room_id FROM rooms r
        WHERE r.max_players = 2
        AND r.status = 'waiting'
        AND r.is_random = TRUE
        AND NOT EXISTS (SELECT 1 FROM room_players rp WHERE rp.room_id = r.room_id AND rp.user_id = %s)
        LIMIT 1""", (uid,))
    if waiting:
        code = waiting[0]['room_id']
        u_name = user[0]['player_name']
        db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)",
                 (code, uid, u_name), commit=True)
        db_query("UPDATE rooms SET status = 'playing' WHERE room_id = %s", (code,), commit=True)
        all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
        for p in all_players:
            try:
                await c.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_2p"))
            except:
                pass
        from handlers.room_2p import start_new_round
        await start_new_round(code, c.bot, start_turn_idx=0)
    else:
        code = generate_room_code()
        u_name = user[0]['player_name']
        db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit, status, is_random) VALUES (%s, %s, 2, 0, 'waiting', TRUE)",
                 (code, uid), commit=True)
        db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)",
                 (code, uid, u_name), commit=True)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
        ])
        await c.message.edit_text(t(uid, "random_waiting"), reply_markup=kb)


@router.callback_query(F.data == "menu_friends")
async def menu_friends(c: types.CallbackQuery):
    uid = c.from_user.id
    kb = [
        [InlineKeyboardButton(text="➕ إنشاء غرفة", callback_data="room_create_start")],
        [InlineKeyboardButton(text="🚪 انضمام لغرفة", callback_data="room_join_input")],
        [InlineKeyboardButton(text="الغرف المفتوحة", callback_data="my_open_rooms")],
        [InlineKeyboardButton(text="الرجوع", callback_data="home")]
    ]
    await c.message.edit_text(t(uid, "friends_menu"), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data == "room_create_start")
async def room_create_menu(c: types.CallbackQuery):
    kb, row = [], []
    for i in range(2, 11):
        row.append(InlineKeyboardButton(text=f"{i} لاعبين", callback_data=f"setp_{i}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="menu_friends")])
    await c.message.edit_text("👥 اختر عدد اللاعبين:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("setp_"))
async def ask_score_limit(c: types.CallbackQuery, state: FSMContext):
    p_count = int(c.data.split("_")[1])
    await state.update_data(p_count=p_count)
    limits = [100, 150, 200, 250, 300, 350, 400, 450, 500]
    kb = []
    row = []
    for val in limits:
        row.append(InlineKeyboardButton(text=f"🎯 {val}", callback_data=f"limit_{val}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton(text="🃏 جولة واحدة", callback_data="limit_0")])
    kb.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="room_create_start")])
    await c.message.edit_text(
        f"🔢 الغرفة لـ {p_count} لاعبين.\nحدد سقف النقاط للفوز (Score Limit):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("limit_"))
async def finalize_room(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    limit = int(c.data.split("_")[1])
    code = generate_room_code()
    uid = c.from_user.id
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))[0]['player_name']
    db_query("""INSERT INTO rooms (room_id, creator_id, max_players, score_limit, status, game_mode)
                VALUES (%s, %s, %s, %s, 'waiting', 'friends')""",
             (code, uid, data.get('p_count', 2), limit), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)",
             (code, uid, u_name), commit=True)
    friends = db_query("""
        SELECT u.user_id, u.player_name FROM friends f
        JOIN users u ON (CASE WHEN f.user_id = %s THEN f.friend_id ELSE f.user_id END) = u.user_id
        WHERE (f.user_id = %s OR f.friend_id = %s) AND f.status = 'accepted'
    """, (uid, uid, uid))
    if friends:
        kb_invite = []
        for f in friends:
            kb_invite.append([InlineKeyboardButton(text=f"👤 {f['player_name']}", callback_data=f"finv_{code}_{f['user_id']}")])
        kb_invite.append([InlineKeyboardButton(text="📨 إرسال الدعوات", callback_data=f"finvsend_{code}")])
        kb_invite.append([InlineKeyboardButton(text="🔗 الحصول على رابط فقط", callback_data=f"finvskip_{code}")])
        kb_invite.append([InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")])
        if code not in friend_invite_selections:
            friend_invite_selections[code] = set()
        await c.message.edit_text(t(uid, "room_created_invite"), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_invite))
    else:
        bot_info = await c.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=join_{code}"
        await c.message.edit_text(t(uid, "room_created_msg1"))
        kb_link = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
        ])
        await c.message.answer(t(uid, "room_created_msg2", link=link), reply_markup=kb_link)
    await state.clear()


@router.callback_query(F.data == "my_open_rooms")
async def my_open_rooms(c: types.CallbackQuery):
    uid = c.from_user.id
    rooms = db_query("""
        SELECT r.room_id, r.max_players, r.status,
               (SELECT count(*) FROM room_players rp WHERE rp.room_id = r.room_id) as p_count
        FROM rooms r
        WHERE r.creator_id = %s AND r.status = 'waiting'
        ORDER BY r.room_id
    """, (uid,))
    if not rooms:
        return await c.answer(t(uid, "no_open_rooms"), show_alert=True)
    kb = []
    for r in rooms:
        label = f"🎮 {r['room_id']} ({r['p_count']}/{r['max_players']})"
        kb.append([
            InlineKeyboardButton(text=label, callback_data=f"viewroom_{r['room_id']}"),
            InlineKeyboardButton(text="❌", callback_data=f"closeroom_{r['room_id']}")
        ])
    kb.append([InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="menu_friends")])
    await c.message.edit_text(t(uid, "open_rooms_list"), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("viewroom_"))
async def view_room(c: types.CallbackQuery):
    uid = c.from_user.id
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s AND creator_id = %s", (code, uid))
    if not room:
        return await c.answer(t(uid, "room_gone"), show_alert=True)
    players = db_query("SELECT player_name FROM room_players WHERE room_id = %s", (code,))
    num_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    plist = ""
    for idx, p in enumerate(players):
        marker = num_emojis[idx] if idx < len(num_emojis) else '👤'
        plist += f"{marker} {p['player_name']}\n"
    bot_info = await c.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=join_{code}"
    text = t(uid, "room_detail", code=code, count=len(players), max=room[0]['max_players'], players=plist, link=link)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "btn_close_room"), callback_data=f"closeroom_{code}")],
        [InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="my_open_rooms")]
    ])
    await c.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("closeroom_"))
async def close_room(c: types.CallbackQuery):
    uid = c.from_user.id
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s AND creator_id = %s AND status = 'waiting'", (code, uid))
    if not room:
        return await c.answer(t(uid, "room_gone"), show_alert=True)
    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s AND user_id != %s", (code, uid))
    for p in players:
        try:
            await c.bot.send_message(p['user_id'], t(p['user_id'], "room_closed_notification"))
        except:
            pass
    db_query("DELETE FROM room_players WHERE room_id = %s", (code,), commit=True)
    db_query("DELETE FROM rooms WHERE room_id = %s", (code,), commit=True)
    await c.answer(t(uid, "room_closed"), show_alert=True)
    remaining = db_query("SELECT room_id FROM rooms WHERE creator_id = %s AND status = 'waiting'", (uid,))
    if remaining:
        await my_open_rooms(c)
    else:
        await c.message.edit_text(t(uid, "no_open_rooms_text"), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="menu_friends")]
        ]))


@router.callback_query(F.data == "room_join_input")
async def join_input(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
    ])
    await c.message.edit_text(t(uid, "send_room_code"), reply_markup=kb)
    await state.set_state(RoomStates.wait_for_code)


@router.message(RoomStates.wait_for_code)
async def process_join(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    code = message.text.strip().upper()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s AND status = 'waiting'", (code,))
    if not room:
        return await message.answer(t(uid, "room_not_found"))
    existing = db_query("SELECT * FROM room_players WHERE room_id = %s AND user_id = %s", (code, uid))
    if existing:
        await state.clear()
        return await message.answer(t(uid, "already_in_room"))
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))[0]['player_name']
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)",
             (code, uid, u_name), commit=True)
    p_count = db_query("SELECT count(*) as count FROM room_players WHERE room_id = %s", (code,))[0]['count']
    max_p = room[0]['max_players']
    creator_id = room[0]['creator_id']
    all_in_room = db_query("SELECT user_id, player_name FROM room_players WHERE room_id = %s", (code,))
    num_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    players_list = ""
    for idx, rp in enumerate(all_in_room):
        marker = num_emojis[idx] if idx < len(num_emojis) else '👤'
        players_list += f"{marker} {rp['player_name']}\n"
    await state.clear()
    if p_count >= max_p:
        db_query("UPDATE rooms SET status = 'playing' WHERE room_id = %s", (code,), commit=True)
        all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
        if max_p == 2:
            for p in all_players:
                try:
                    await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_2p"))
                except:
                    pass
            from handlers.room_2p import start_new_round
            await start_new_round(code, message.bot, start_turn_idx=0)
        else:
            for p in all_players:
                try:
                    await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_multi", n=max_p))
                except:
                    pass
            from handlers.room_multi import start_game_multi
            await start_game_multi(code, message.bot)
    else:
        wait_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
        ])
        await message.answer(t(uid, "player_joined", name=u_name, count=p_count, max=max_p, list=players_list), reply_markup=wait_kb)
        try:
            notify_text = t(creator_id, "player_joined", name=u_name, count=p_count, max=max_p, list=players_list)
            notify_text += t(creator_id, "waiting_players", n=max_p - p_count)
            notify_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ إعدادات الغرفة", callback_data=f"rsettings_{code}")],
                [InlineKeyboardButton(text=t(creator_id, "btn_home"), callback_data="home")]
            ])
            await message.bot.send_message(creator_id, notify_text, reply_markup=notify_kb)
        except:
            pass


async def process_user_search_by_id(c: types.CallbackQuery, target_id: int):
    uid = c.from_user.id
    target = db_query("SELECT * FROM users WHERE user_id = %s", (target_id,))
    if not target:
        return await c.answer("❌ اللاعب غير موجود.", show_alert=True)
    t_user = target[0]
    is_following = db_query("SELECT 1 FROM follows WHERE follower_id = %s AND following_id = %s", (uid, target_id))
    from datetime import datetime, timedelta
    last_seen = t_user.get("last_seen")
    if last_seen:
        online = (datetime.now() - last_seen < timedelta(minutes=5))
        status = t(uid, "status_online") if online else t(uid, "status_offline", time=last_seen.strftime("%H:%M"))
    else:
        status = t(uid, "status_offline", time="--:--")
    text = t(uid, "profile_title",
             name=t_user.get("player_name", "لاعب"),
             username=t_user.get("username_key", "---"),
             points=t_user.get("online_points", 0),
             status=status)
    follow_btn_text = t(uid, "btn_unfollow") if is_following else t(uid, "btn_follow")
    follow_callback = f"unfollow_{target_id}" if is_following else f"follow_{target_id}"
    kb = [
        [InlineKeyboardButton(text=follow_btn_text, callback_data=follow_callback)],
        [InlineKeyboardButton(text=t(uid, "btn_invite_play"), callback_data=f"invite_{target_id}")],
        [InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="social_menu")]
    ]
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("view_profile_"))
async def view_profile_handler(c: types.CallbackQuery):
    try:
        target_id = int(c.data.split("_")[2])
        await process_user_search_by_id(c, target_id)
    except Exception as e:
        print(f"view_profile_handler error: {e}")
        await c.answer("⚠️ فشل فتح بروفايل اللاعب.", show_alert=True)


@router.callback_query(F.data == "home")
async def go_home(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = c.from_user.id
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    name = user[0]["player_name"] if user else (c.from_user.full_name or "لاعب")
    await show_main_menu(c, name, user_id=uid, cleanup=True)


@router.callback_query(F.data == "change_lang")
async def change_lang_menu(c: types.CallbackQuery):
    uid = c.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇸🇦 عربي", callback_data="switch_lang_ar"),
         InlineKeyboardButton(text="🇬🇧 English", callback_data="switch_lang_en")],
        [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
    ])
    await c.message.edit_text(t(uid, "choose_lang"), reply_markup=kb)


@router.callback_query(F.data.startswith("switch_lang_"))
async def switch_lang(c: types.CallbackQuery):
    uid = c.from_user.id
    lang = c.data.split("_")[-1]
    db_query("UPDATE users SET language = %s WHERE user_id = %s", (lang, uid), commit=True)
    set_lang(uid, lang)
    await c.answer(t(uid, "lang_changed"), show_alert=True)
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    name = user[0]['player_name'] if user else 'Player'
    await show_main_menu(c, name, uid)


@router.callback_query(F.data.startswith("nextround_"))
async def next_round_go(c: types.CallbackQuery):
    room_id = c.data.split("_", 1)[1]
    nr = pending_next_round.get(room_id)
    if not nr:
        return await c.answer("⚠️ انتهت صلاحية هذا الخيار.", show_alert=True)
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    uid = c.from_user.id
    if room_id not in next_round_ready:
        next_round_ready[room_id] = set()
    if uid in next_round_ready[room_id]:
        return await c.answer("✅ سبق وأكدت! بانتظار البقية...", show_alert=True)
    next_round_ready[room_id].add(uid)
    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (room_id,))
    total = len(players)
    ready_count = len(next_round_ready[room_id])
    try:
        await c.message.edit_text(f"✅ جاهز! ({ready_count}/{total}) بانتظار البقية...")
    except:
        pass
    if ready_count >= total:
        await _start_next_round(room_id, c.bot)


async def _start_next_round(room_id, bot):
    nr = pending_next_round.pop(room_id, None)
    next_round_ready.pop(room_id, None)
    if not nr:
        return
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
    if not room:
        return
    if nr['mode'] == '2p':
        from handlers.room_2p import start_new_round
        await start_new_round(room_id, bot, start_turn_idx=nr.get('start_turn', 0))
    else:
        from handlers.room_multi import start_game_multi
        await start_game_multi(room_id, bot, start_turn_idx=nr.get('start_turn', 0))


async def _next_round_timeout(room_id, bot):
    await asyncio.sleep(20)
    if room_id in pending_next_round:
        await _start_next_round(room_id, bot)


@router.callback_query(F.data.startswith("addfrnd_"))
async def add_friend(c: types.CallbackQuery):
    target_id = int(c.data.split("_")[1])
    uid = c.from_user.id
    if target_id == uid:
        return await c.answer("❌ ما تقدر تضيف نفسك!", show_alert=True)
    existing = db_query("SELECT * FROM friends WHERE (user_id = %s AND friend_id = %s) OR (user_id = %s AND friend_id = %s)",
                        (uid, target_id, target_id, uid))
    if existing:
        st = existing[0]['status']
        if st == 'accepted':
            return await c.answer("✅ هذا اللاعب أصلاً صديقك!", show_alert=True)
        else:
            return await c.answer("⏳ يوجد طلب صداقة معلق بالفعل.", show_alert=True)
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    u_name = u_name[0]['player_name'] if u_name else "لاعب"
    db_query("INSERT INTO friends (user_id, friend_id, status) VALUES (%s, %s, 'pending')", (uid, target_id), commit=True)
    await c.answer("✅ تم إرسال طلب الصداقة!", show_alert=True)
    try:
        frnd_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ قبول", callback_data=f"frndy_{uid}"),
             InlineKeyboardButton(text="❌ رفض", callback_data=f"frndn_{uid}")]
        ])
        await c.bot.send_message(target_id, f"📨 {u_name} يريد إضافتك كصديق!", reply_markup=frnd_kb)
    except:
        pass


@router.callback_query(F.data.startswith("frndy_"))
async def accept_friend(c: types.CallbackQuery):
    sender_id = int(c.data.split("_")[1])
    uid = c.from_user.id
    req = db_query("SELECT * FROM friends WHERE user_id = %s AND friend_id = %s AND status = 'pending'", (sender_id, uid))
    if not req:
        return await c.answer("⚠️ لا يوجد طلب صداقة.", show_alert=True)
    db_query("UPDATE friends SET status = 'accepted' WHERE user_id = %s AND friend_id = %s", (sender_id, uid), commit=True)
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    u_name = u_name[0]['player_name'] if u_name else "لاعب"
    sender_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (sender_id,))
    sender_name = sender_name[0]['player_name'] if sender_name else "لاعب"
    await c.message.edit_text(f"✅ تم قبول صداقة {sender_name}!")
    try:
        await c.bot.send_message(sender_id, f"✅ {u_name} قبل طلب صداقتك!")
    except:
        pass


@router.callback_query(F.data.startswith("frndn_"))
async def reject_friend(c: types.CallbackQuery):
    sender_id = int(c.data.split("_")[1])
    uid = c.from_user.id
    db_query("DELETE FROM friends WHERE user_id = %s AND friend_id = %s", (sender_id, uid), commit=True)
    await c.message.edit_text("❌ تم رفض طلب الصداقة.")


@router.callback_query(F.data.startswith("finv_"))
async def toggle_friend_invite(c: types.CallbackQuery):
    parts = c.data.split("_")
    code = parts[1]
    friend_id = int(parts[2])
    if code not in friend_invite_selections:
        friend_invite_selections[code] = set()
    sel = friend_invite_selections[code]
    if friend_id in sel:
        sel.discard(friend_id)
    else:
        sel.add(friend_id)
    friends = db_query("""
        SELECT u.user_id, u.player_name FROM friends f
        JOIN users u ON (CASE WHEN f.user_id = %s THEN f.friend_id ELSE f.user_id END) = u.user_id
        WHERE (f.user_id = %s OR f.friend_id = %s) AND f.status = 'accepted'
    """, (c.from_user.id, c.from_user.id, c.from_user.id))
    kb_invite = []
    for f in friends:
        check = "✅" if f['user_id'] in sel else "👤"
        kb_invite.append([InlineKeyboardButton(text=f"{check} {f['player_name']}", callback_data=f"finv_{code}_{f['user_id']}")])
    kb_invite.append([InlineKeyboardButton(text=f"📨 إرسال الدعوات ({len(sel)})", callback_data=f"finvsend_{code}")])
    kb_invite.append([InlineKeyboardButton(text="🔗 الحصول على رابط فقط", callback_data=f"finvskip_{code}")])
    kb_invite.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")])
    await c.message.edit_text("✅ تم إنشاء الغرفة!\n\n👥 اختر الأصدقاء اللي تبي تدعوهم:",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_invite))


@router.callback_query(F.data.startswith("finvsend_"))
async def send_friend_invites(c: types.CallbackQuery):
    code = c.data.split("_")[1]
    sel = friend_invite_selections.pop(code, set())
    if not sel:
        return await c.answer("⚠️ لم تختر أي صديق!", show_alert=True)
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    max_p = room[0]['max_players'] if room else 10
    bot_info = await c.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=join_{code}"
    sent = 0
    for fid in sel:
        try:
            inv_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ موافق", callback_data=f"invy_{code}"),
                 InlineKeyboardButton(text="❌ رفض", callback_data=f"invn_{code}")]
            ])
            await c.bot.send_message(fid, f"📨 {u_name} يدعوك للعب!\n\n⏳ عندك 30 ثانية للرد\nهل تريد الانضمام?", reply_markup=inv_kb)
            sent += 1
        except:
            pass
    pending_invites[code] = {
        'creator': c.from_user.id,
        'creator_name': u_name,
        'invited': {fid: '' for fid in sel},
        'accepted': set(),
        'rejected': set(),
        'max_players': max_p,
        'score_limit': room[0].get('score_limit', 0) if room else 0,
        'mode': '2p' if max_p == 2 else 'multi'
    }
    wait_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
    ])
    await c.message.edit_text(f"📨 تم إرسال {sent} دعوة!\n⏳ بانتظار الردود...\n\n🎮 رابط الدخول:\n{link}", reply_markup=wait_kb)
    asyncio.create_task(_invite_auto_check(code, c.bot))


@router.callback_query(F.data.startswith("finvskip_"))
async def skip_friend_invite(c: types.CallbackQuery):
    code = c.data.split("_")[1]
    friend_invite_selections.pop(code, None)
    bot_info = await c.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=join_{code}"
    kb_code = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
    ])
    await c.message.edit_text(f"🎮 رابط الدخول للعبة:\n{link}", reply_markup=kb_code)


@router.callback_query(F.data.startswith("rsettings_"))
async def room_settings(c: types.CallbackQuery):
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['creator_id'] != c.from_user.id:
        return await c.answer("⚠️ فقط صاحب الغرفة يقدر يدخل الإعدادات!", show_alert=True)
    score_text = f"🎯 {room[0]['score_limit']}" if room[0]['score_limit'] > 0 else "🃏 جولة واحدة"
    players = db_query("SELECT user_id, player_name FROM room_players WHERE room_id = %s", (code,))
    p_count = len(players)
    kb = [
        [InlineKeyboardButton(text="🚫 طرد لاعبين", callback_data=f"rkicklist_{code}")],
        [InlineKeyboardButton(text=f"🔢 تغيير سقف اللعب ({score_text})", callback_data=f"rchglimit_{code}")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data=f"rsetback_{code}")]
    ]
    await c.message.edit_text(
        f"⚙️ إعدادات الغرفة\n\n👥 عدد اللاعبين: {p_count}/{room[0]['max_players']}\n📊 سقف النقاط: {score_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("rsetback_"))
async def room_settings_back(c: types.CallbackQuery):
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['status'] == 'playing':
        await c.message.edit_text("🔄 جاري العودة للعبة...")
        p_count = len(db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,)))
        if p_count == 2:
            from handlers.room_2p import refresh_ui
            await refresh_ui(code, c.bot)
        else:
            from handlers.room_multi import refresh_ui_multi
            await refresh_ui_multi(code, c.bot)
        return
    players = db_query("SELECT user_id, player_name FROM room_players WHERE room_id = %s", (code,))
    num_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    players_list = ""
    for idx, rp in enumerate(players):
        marker = num_emojis[idx] if idx < len(num_emojis) else '👤'
        players_list += f"{marker} {rp['player_name']}\n"
    p_count = len(players)
    max_p = room[0]['max_players']
    txt = f"👥 اللاعبين ({p_count}/{max_p}):\n{players_list}"
    if p_count < max_p:
        txt += f"\n⏳ بانتظار {max_p - p_count} لاعب آخر..."
    else:
        txt += "\n✅ اكتمل العدد!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ إعدادات الغرفة", callback_data=
