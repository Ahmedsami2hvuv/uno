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
    edit_name = State()
    edit_password = State()
    register_name = State()
    register_password = State()
    login_name = State()
    login_password = State()
    complete_profile_name = State()
    complete_profile_password = State()

persistent_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🏠 القائمة الرئيسية")]],
    resize_keyboard=True,
    is_persistent=True
)

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

async def show_main_menu(message, name, user_id=None):
    uid = user_id or (message.from_user.id if hasattr(message, 'from_user') else 0)
    kb = [
        [InlineKeyboardButton(text=t(uid, "btn_random_play"), callback_data="menu_random")],
        [InlineKeyboardButton(text=t(uid, "btn_play_friends"), callback_data="menu_friends")],
        [InlineKeyboardButton(text=t(uid, "btn_calculator"), callback_data="mode_calc")],
        [InlineKeyboardButton(text=t(uid, "btn_my_account"), callback_data="my_account")],
        [InlineKeyboardButton(text=t(uid, "btn_rules"), callback_data="show_rules")],
        [InlineKeyboardButton(text=t(uid, "btn_language"), callback_data="change_lang")]
    ]
    text = t(uid, "main_menu", name=name)
    if hasattr(message, "answer"):
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split(maxsplit=1)
    deep_link = args[1] if len(args) > 1 else None
    uid = message.from_user.id

    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if not user or not user[0].get('is_registered'):
        if deep_link and deep_link.startswith("join_"):
            await state.update_data(pending_join=deep_link.split("_", 1)[1])
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇸🇦 عربي", callback_data="set_lang_ar"),
             InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en")]
        ])
        await message.answer(t(uid, "choose_lang"), reply_markup=kb)
    else:
        if deep_link and deep_link.startswith("join_"):
            await state.update_data(pending_join=deep_link.split("_", 1)[1])
        if not user[0].get('password'):
            name = user[0]['player_name']
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t(uid, "btn_yes_name"), callback_data="cp_name_ok")],
                [InlineKeyboardButton(text=t(uid, "btn_edit_name"), callback_data="cp_edit_name")]
            ])
            await message.answer(t(uid, "complete_profile", name=name), reply_markup=kb)
        else:
            if deep_link and deep_link.startswith("join_"):
                code = deep_link.split("_", 1)[1]
                await _join_room_by_code(message, code, user[0])
            else:
                await show_main_menu(message, user[0]['player_name'], uid)

@router.callback_query(F.data.startswith("set_lang_"))
async def set_lang_callback(c: types.CallbackQuery, state: FSMContext):
    lang = c.data.split("_")[-1]
    uid = c.from_user.id
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if user:
        db_query("UPDATE users SET language = %s WHERE user_id = %s", (lang, uid), commit=True)
    else:
        db_query("INSERT INTO users (user_id, username, language, is_registered) VALUES (%s, %s, %s, FALSE)", (uid, c.from_user.username or '', lang), commit=True)
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
        await message.answer(t(uid, "name_too_short"))
        return
    if len(name) > 20:
        await message.answer(t(uid, "name_too_long"))
        return
    existing = db_query("SELECT * FROM users WHERE player_name = %s AND user_id != %s", (name, uid))
    if existing:
        await message.answer(t(uid, "name_taken"))
        return
    db_query("UPDATE users SET player_name = %s WHERE user_id = %s", (name, uid), commit=True)
    await message.answer(t(uid, "ask_password"))
    await state.set_state(RoomStates.complete_profile_password)

@router.message(RoomStates.complete_profile_password)
async def complete_profile_password_handler(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    password = message.text.strip()
    if len(password) < 4:
        await message.answer(t(uid, "password_too_short"))
        return
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
    await show_main_menu(message, name, uid)

async def _join_room_by_code(message, code, user_data):
    uid = message.from_user.id
    room = db_query("SELECT * FROM rooms WHERE room_id = %s AND status = 'waiting'", (code,))
    if not room:
        await message.answer(t(uid, "room_not_found"))
        await show_main_menu(message, user_data['player_name'], uid)
        return

    existing = db_query("SELECT * FROM room_players WHERE room_id = %s AND user_id = %s", (code, uid))
    if existing:
        await message.answer(t(uid, "already_in_room"))
        return

    p_count = db_query("SELECT count(*) as count FROM room_players WHERE room_id = %s", (code,))[0]['count']
    max_p = room[0]['max_players']
    if p_count >= max_p:
        await message.answer(t(uid, "room_full"))
        await show_main_menu(message, user_data['player_name'], uid)
        return

    u_name = user_data['player_name']
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)", (code, uid, u_name), commit=True)

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
                try: await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_2p"))
                except: pass
            from handlers.room_2p import start_new_round
            await start_new_round(code, message.bot, start_turn_idx=0)
        else:
            for p in all_players:
                try: await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_multi", n=max_p))
                except: pass
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
        except: pass

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
        await message.answer(t(uid, "name_too_short"))
        return
    if len(name) > 20:
        await message.answer(t(uid, "name_too_long"))
        return
    existing = db_query("SELECT * FROM users WHERE player_name = %s", (name,))
    if existing:
        await message.answer(t(uid, "name_taken"))
        return
    await state.update_data(reg_name=name)
    await message.answer(t(uid, "ask_password"))
    await state.set_state(RoomStates.register_password)

@router.message(RoomStates.register_password)
async def register_password(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    password = message.text.strip()
    if len(password) < 4:
        await message.answer(t(uid, "password_too_short"))
        return
    data = await state.get_data()
    name = data.get('reg_name', 'Player')
    lang = get_lang(uid)
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if user:
        db_query("UPDATE users SET player_name = %s, password = %s, is_registered = TRUE, language = %s WHERE user_id = %s", (name, password, lang, uid), commit=True)
    else:
        db_query("INSERT INTO users (user_id, username, player_name, password, is_registered, language) VALUES (%s, %s, %s, %s, TRUE, %s)", (uid, message.from_user.username or '', name, password, lang), commit=True)
    pending_join = data.get('pending_join')
    await state.clear()
    await message.answer(t(uid, "register_success", name=name, password=password))
    if pending_join:
        user_data = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
        if user_data:
            await _join_room_by_code(message, pending_join, user_data[0])
            return
    await show_main_menu(message, name, uid)

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
        await message.answer(t(uid, "login_fail"))
        return
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
        await message.answer(t(uid, "login_fail"))
        return
    old_id = user[0]['user_id']
    db_query("UPDATE users SET user_id = %s, username = %s, is_registered = TRUE WHERE player_name = %s", (uid, message.from_user.username or '', name), commit=True)
    data_state = await state.get_data()
    pending_join = data_state.get('pending_join')
    await state.clear()
    await message.answer(t(uid, "login_success", name=name))
    if pending_join:
        user_data = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
        if user_data:
            await _join_room_by_code(message, pending_join, user_data[0])
            return
    await show_main_menu(message, name, uid)

@router.callback_query(F.data == "menu_random")
async def menu_random(c: types.CallbackQuery):
    uid = c.from_user.id
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if not user:
        await c.answer(t(uid, "room_not_found"), show_alert=True)
        return
    waiting = db_query("SELECT r.room_id FROM rooms r WHERE r.max_players = 2 AND r.status = 'waiting' AND r.is_random = TRUE AND NOT EXISTS (SELECT 1 FROM room_players rp WHERE rp.room_id = r.room_id AND rp.user_id = %s) LIMIT 1", (uid,))
    if waiting:
        code = waiting[0]['room_id']
        await _join_room_by_code(c.message, code, user[0])
    else:
        code = generate_room_code()
        u_name = user[0]['player_name']
        db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit, status, is_random) VALUES (%s, %s, 2, 0, 'waiting', TRUE)", (code, uid), commit=True)
        db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)", (code, uid, u_name), commit=True)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
        ])
        await c.message.edit_text(t(uid, "random_waiting"), reply_markup=kb)

@router.callback_query(F.data == "menu_friends")
async def menu_friends(c: types.CallbackQuery):
    uid = c.from_user.id
    kb = [
        [InlineKeyboardButton(text=t(uid, "btn_create_room"), callback_data="room_create_start")],
        [InlineKeyboardButton(text=t(uid, "btn_join_room"), callback_data="room_join_input")],
        [InlineKeyboardButton(text=t(uid, "btn_my_rooms"), callback_data="my_open_rooms")],
        [InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="home")]
    ]
    await c.message.edit_text(t(uid, "friends_menu"), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "room_create_start")
async def room_create_menu(c: types.CallbackQuery):
    kb, row = [], []
    for i in range(2, 11):
        row.append(InlineKeyboardButton(text=f"{i} لاعبين", callback_data=f"setp_{i}"))
        if len(row) == 2: kb.append(row); row = []
    if row: kb.append(row)
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
        if row: kb.append(row)

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

    db_query("""
        INSERT INTO rooms (room_id, creator_id, max_players, score_limit, status, game_mode) 
        VALUES (%s, %s, %s, %s, 'waiting', 'friends')""", 
        (code, uid, data.get('p_count', 2), limit), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)", (code, uid, u_name), commit=True)

    friends = db_query("""
        SELECT u.user_id, u.player_name FROM friends f
        JOIN users u ON (CASE WHEN f.user_id = %s THEN f.friend_id ELSE f.user_id END) = u.user_id
        WHERE (f.user_id = %s OR f.friend_id = %s) AND f.status = 'accepted'
    """, (uid, uid, uid))

    if friends:
        kb_invite = []
        for f in friends:
            kb_invite.append([InlineKeyboardButton(text=f"👤 {f['player_name']}", callback_data=f"finv_{code}_{f['user_id']}\")])
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
        await c.answer(t(uid, "no_open_rooms"), show_alert=True)
        return
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
        await c.answer(t(uid, "room_gone"), show_alert=True)
        return
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
        await c.answer(t(uid, "room_gone"), show_alert=True)
        return
    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s AND user_id != %s", (code, uid))
    for p in players:
        try:
            await c.bot.send_message(p['user_id'], t(p['user_id'], "room_closed_notification"))
        except: pass
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
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)", (code, uid, u_name), commit=True)

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
                try: await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_2p"))
                except: pass
            from handlers.room_2p import start_new_round
            await start_new_round(code, message.bot, start_turn_idx=0)
        else:
            for p in all_players:
                try: await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_multi", n=max_p))
                except: pass
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
        except: pass
@router.callback_query(F.data == "home")
async def go_home(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = c.from_user.id
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    await show_main_menu(c.message, user[0]['player_name'] if user else "لاعب", uid)