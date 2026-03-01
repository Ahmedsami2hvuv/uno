import os
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database import db_query
from i18n import t, get_lang, set_lang, TEXTS
import random, string, json, asyncio
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

router = Router()

# --- اشتراك القناة (CHANNEL_ID) ---
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip() or None  # مثال: @ko_kseb أو -100xxxx

async def is_channel_member(bot, user_id: int) -> bool:
    if not CHANNEL_ID:
        return True
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False

def _channel_subscribe_kb():
    if not CHANNEL_ID:
        return None
    s = str(CHANNEL_ID).strip()
    if s.startswith("@"):
        username = s.lstrip("@")
        url = f"https://t.me/{username}"
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 اشترك في القناة", url=url)]])
    if s.startswith("-"):
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 القناة", url="https://t.me/")]])
    url = f"https://t.me/{s}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 اشترك في القناة", url=url)]])

async def channel_subscribe_message_middleware(handler, event: types.Message, data: dict):
    if not CHANNEL_ID:
        return await handler(event, data)
    user_id = event.from_user.id if event.from_user else None
    if not user_id:
        return await handler(event, data)
    if await is_channel_member(event.bot, user_id):
        return await handler(event, data)
    kb = _channel_subscribe_kb()
    if kb and kb.inline_keyboard:
        kb.inline_keyboard.append([InlineKeyboardButton(text="✅ تحقق", callback_data="check_channel_sub")])
    await event.answer("⛔ يجب الاشتراك في القناة أولاً لاستخدام البوت.\n\nاشترك ثم اضغط «تحقق».", reply_markup=kb)
    return

async def channel_subscribe_callback_middleware(handler, event: types.CallbackQuery, data: dict):
    if not CHANNEL_ID:
        return await handler(event, data)
    user_id = event.from_user.id if event.from_user else None
    if not user_id:
        return await handler(event, data)
    if await is_channel_member(event.bot, user_id):
        return await handler(event, data)
    try:
        await event.answer()
    except Exception:
        pass
    kb = _channel_subscribe_kb()
    if kb and kb.inline_keyboard:
        kb.inline_keyboard.append([InlineKeyboardButton(text="✅ تحقق", callback_data="check_channel_sub")])
    await event.message.edit_text("⛔ يجب الاشتراك في القناة أولاً لاستخدام البوت.\n\nاشترك ثم اضغط «تحقق».", reply_markup=kb)
    return

router.message.middleware(channel_subscribe_message_middleware)
router.callback_query.middleware(channel_subscribe_callback_middleware)

    
replay_data = {}
pending_invites = {}
pending_next_round = {}
next_round_ready = {}
friend_invite_selections = {}
kick_selections = {}
# كتم دعوات اللعب: (muter_id, muted_id) -> muted_until (datetime أو None للابد)
invite_mutes = {}
# تعليم تفاعلي: كاش في الذاكرة حتى لو عمود seen_tutorial غير موجود في DB
_tutorial_done_cache = set()

# --- إنجازات وبادجات (يُستدعى فتحها من room_2p عند الفوز/نهاية الجولة) ---
ACHIEVEMENTS = {
    "first_win": {"ar": "أول فوز", "en": "First win", "fa": "اولین برد", "emoji": "🏆"},
    "wins_10": {"ar": "10 انتصارات", "en": "10 wins", "fa": "۱۰ برد", "emoji": "🔥"},
    "wins_50": {"ar": "50 انتصاراً", "en": "50 wins", "fa": "۵۰ برد", "emoji": "⭐"},
    "plus4_win": {"ar": "فوز بـ +4", "en": "Won with +4", "fa": "برد با +۴", "emoji": "🌈"},
    "uno_perfect": {"ar": "أونو مثالي", "en": "Perfect Uno", "fa": "اوونوی کامل", "emoji": "🎯"},
}
def get_user_achievements(user_id: int):
    try:
        r = db_query("SELECT achievement_id FROM user_achievements WHERE user_id = %s", (user_id,))
        return [row["achievement_id"] for row in r] if r else []
    except Exception:
        return []
def unlock_achievement(user_id: int, achievement_id: str):
    if achievement_id not in ACHIEVEMENTS:
        return
    try:
        db_query(
            "INSERT INTO user_achievements (user_id, achievement_id) VALUES (%s, %s) ON CONFLICT (user_id, achievement_id) DO NOTHING",
            (user_id, achievement_id), commit=True
        )
    except Exception:
        pass
def format_achievements_badges(uid: int, achievement_ids: list) -> str:
    if not achievement_ids:
        return ""
    parts = []
    for aid in achievement_ids[:10]:
        a = ACHIEVEMENTS.get(aid)
        if not a:
            continue
        lang = get_lang(uid)
        title = a.get(lang) or a.get("ar") or aid
        parts.append(f"{a.get('emoji', '🏅')} {title}")
    return "\n🏅 " + " | ".join(parts) if parts else ""

# --- سجل المباريات وعرض سريع للجولة (للاستدعاء من room_2p / room_multi) ---
def save_round_result(room_id: str, winner_id: int, scores_dict: dict, round_num: int = 1):
    """احفظ نتيجة الجولة في match_results (للسجل والإحصائيات)."""
    try:
        db_query(
            "INSERT INTO match_results (room_id, round_num, winner_id, scores_json) VALUES (%s, %s, %s, %s)",
            (room_id, round_num, json.dumps(scores_dict) if isinstance(scores_dict, dict) else str(scores_dict), winner_id),
            commit=True
        )
    except Exception:
        pass

def get_round_summary_text(uid: int, winner_name: str, scores_list: list) -> str:
    """نص ملخص الجولة: من فاز ونقاط الجميع. scores_list = [(name, points), ...]"""
    lines = [f"🏆 {winner_name} " + t(uid, "round_summary_won")]
    for name, pts in (scores_list or [])[:10]:
        lines.append(f"  • {name}: {pts}")
    return "\n".join(lines)

def prepare_replay_after_game(room_id: str, creator_id: int, max_players: int, score_limit: int, player_ids: list) -> tuple:
    """لإعادة اللعب السريع: يخزن بيانات الغرفة ويُرجع (replay_id, message_text, InlineKeyboardMarkup) لإرساله لكل لاعب."""
    replay_id = f"{room_id}_{creator_id}_{int(__import__('time').time())}"
    replay_data[replay_id] = {
        "creator_id": creator_id,
        "max_players": max_players,
        "score_limit": score_limit,
        "player_ids": list(player_ids) if player_ids else [],
    }
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 لعب مرة أخرى", callback_data=f"replay_{replay_id}")],
        [InlineKeyboardButton(text=t(creator_id, "btn_home"), callback_data="home")]
    ])
    msg = "🏁 انتهت الجولة! اضغط «لعب مرة أخرى» لدعوة نفس الفريق."
    return replay_id, msg, kb

# مشاهدون الغرفة (للوضع مشاهدة: room_id -> set(user_id))
room_spectators = {}

class RoomStates(StatesGroup):
    wait_for_code = State()
    # الحالات الجديدة للتسجيل المطور والترقية
    reg_ask_username = State()
    reg_ask_password = State()
    reg_ask_name = State()
    upgrade_username = State()
    upgrade_password = State()
    search_user = State()
    # ابقينا القديمة لضمان عدم تعطل أي كود مرتبط بها حالياً
    edit_name = State()
    edit_username = State()
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


@router.message(F.text == "🧹 تنظيف الرسائل")
async def clean_chat_messages(message: types.Message):
    """يمسح جميع رسائل البوت في المحادثة (تنظيف سجل الرسائل)"""
    chat_id = message.chat.id
    current_msg_id = message.message_id
    deleted_count = 0
    
    for mid in range(current_msg_id, max(current_msg_id - 200, 0), -1):
        try:
            await message.bot.delete_message(chat_id, mid)
            deleted_count += 1
        except Exception:
            pass

    name = message.from_user.full_name
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    if user:
        name = user[0]['player_name']
    
    await show_main_menu(message, name, user_id=message.from_user.id, cleanup=False)

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))


@router.message(Command("start"))
async def cmd_start_with_deeplink(message: types.Message, state: FSMContext):
    """معالجة /start مع رابط الدعوة: /start join_ROOMCODE"""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) >= 2 and parts[1].startswith("join_"):
        code = parts[1][5:].strip()
        if code:
            user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
            if user and user[0].get("is_registered"):
                await _join_room_by_code(message, code, user[0])
                return
            if not user:
                db_query(
                    "INSERT INTO users (user_id, username, is_registered) VALUES (%s, %s, FALSE)",
                    (message.from_user.id, message.from_user.username or ""),
                    commit=True,
                )
                await state.update_data(pending_join=code)
                uid = message.from_user.id
                lang = get_lang(uid)
                set_lang(uid, lang)
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=t(uid, "btn_register"), callback_data="auth_register")],
                        [InlineKeyboardButton(text=t(uid, "btn_login"), callback_data="auth_login")],
                    ]
                )
                welcome = t(uid, "welcome_new") + "\n\n" + t(uid, "invite_pending_room")
                await message.answer(welcome, reply_markup=kb)
                return
    try:
        await message.delete()
    except Exception:
        pass
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    name = user[0]["player_name"] if user else message.from_user.full_name
    await show_main_menu(message, name, user_id=message.from_user.id, state=state)


@router.message(F.text == "ستارت")
async def quick_start_button(message: types.Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    name = user[0]["player_name"] if user else message.from_user.full_name
    await show_main_menu(message, name, user_id=message.from_user.id, state=state)

@router.message(RoomStates.upgrade_username)
async def process_upgrade_username(message: types.Message, state: FSMContext):
    new_username = message.text.strip().lower()

    # التأكد من الطول وشكل اليوزر
    if len(new_username) < 3 or not new_username.isalnum():
        return await message.answer("❌ اليوزر نيم يجب أن يكون 3 أحرف أو أكثر (إنجليزي وأرقام فقط):")

    # التأكد إذا اليوزر محجوز لغير لاعب
    check = db_query("SELECT user_id FROM users WHERE username_key = %s", (new_username,))
    if check:
        return await message.answer("❌ هذا اليوزر نيم محجوز لشخص آخر، اختر غيره:")

    # حفظ اليوزر مؤقتاً بالـ state والانتقال لطلب كلمة السر
    await state.update_data(temp_username=new_username)
    await message.answer("✅ يوزر رائع! الآن أرسل كلمة السر التي تريدها (4 أحرف أو أكثر):")
    await state.set_state(RoomStates.upgrade_password)

@router.message(RoomStates.upgrade_password)
async def process_upgrade_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if len(password) < 4:
        return await message.answer("❌ كلمة السر ضعيفة، أرسل 4 أحرف أو أكثر:")

    data = await state.get_data()
    username = data.get('temp_username')

    # تحديث قاعدة البيانات بشكل نهائي
    db_query(
        "UPDATE users SET username_key = %s, password_key = %s WHERE user_id = %s",
        (username, password, message.from_user.id),
        commit=True,
    )

    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    name = user[0]['player_name'] if user else message.from_user.full_name

    await message.answer(f"🎉 مبارك! تم تحديث حسابك بنجاح.\n👤 يوزرك: @{username}\n🔑 كلمة السر: {password}")
    
    # نرجعه للمنيو الرئيسي
    await show_main_menu(message, name, user_id=message.from_user.id, state=state)


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
    print("DEBUG: وصلت رسالة اليوزر نيم")
    user_id = message.from_user.id
    username = message.text.strip().lower()

    # التحقق من شروط اليوزرنيم
    if not username.isalnum() or len(username) < 3:
        await message.answer("✍️ يرجى إدخال اسم مستخدم (يوزر نيم) خاص بك (حروف إنجليزية وأرقام فقط، 3 أحرف على الأقل):")
        return

    check = db_query("SELECT user_id FROM users WHERE username_key = %s", (username,))
    if check:
        await message.answer("❌ هذا اليوزر نيم مستخدم من قبل، اختر غيره.")
        return

    db_query("UPDATE users SET username_key = %s WHERE user_id = %s", (username, user_id), commit=True)
    user_info = db_query("SELECT player_name FROM users WHERE user_id = %s", (user_id,))
    p_name = user_info[0]['player_name'] if user_info else "لاعب"

    await message.answer(f"✅ تم اختيار اليوزر: {username}\n🎉 تم تفعيل حسابك!")
    await state.clear()
    await show_main_menu(message, p_name, user_id=user_id, state=state)

@router.message(RoomStates.upgrade_password)
async def process_password_step(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    password = message.text.strip()
    
    # التأكد من طول الباسورد
    if len(password) < 4:
        return await message.answer(t(user_id, "password_too_short"))

    data = await state.get_data()
    username = data['chosen_username']
    current_state = await state.get_state()
    
    if current_state == RoomStates.upgrade_password:
        # حالة الترقية: اللاعب مسجل أصلاً بس ينقصه يوزر وباسورد جديد
        db_query(
            "UPDATE users SET username_key = %s, password_key = %s WHERE user_id = %s",
            (username, password, user_id),
            commit=True,
        )
        user_info = db_query("SELECT player_name FROM users WHERE user_id = %s", (user_id,))
        p_name = user_info[0]['player_name'] if user_info else "لاعب"
        await message.answer(t(user_id, "reg_success", name=p_name, username=username))
        await state.clear()
        await show_main_menu(message, p_name, user_id=user_id, state=state)
    else:
        # حالة التسجيل الجديد: نحفظ اليوزر والباسورد مؤقتاً ونطلب "الاسم"
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
    
    # حفظ اللاعب الجديد كلياً في القاعدة
    db_query("""INSERT INTO users (user_id, username_key, password_key, player_name, is_registered) 
    VALUES (%s, %s, %s, %s, TRUE)""", 
    (user_id, username, password, name), commit=True)
    
    await message.answer(t(user_id, "reg_success", name=name, username=username))
    await state.clear()
    await (message, name, user_id)
    


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
    db_query(
        "UPDATE users SET password_key = %s WHERE user_id = %s",
        (password, uid),
        commit=True,
    )
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
                try:
                    await message.bot.send_message(p['user_id'], t(p['user_id'], "🎮 بدأت اللعبة! استعد..."))
                except Exception:
                    pass
            await asyncio.sleep(0.5)
            from handlers.room_2p import start_new_round
            await start_new_round(code, message.bot, start_turn_idx=0)
        else:
            for p in all_players:
                try:
                    await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_multi", n=max_p))
                except Exception:
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
        except Exception:
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
        db_query("UPDATE users SET player_name = %s, password_key = %s, is_registered = TRUE, language = %s WHERE user_id = %s", (name, password, lang, uid), commit=True)
    else:
        db_query("INSERT INTO users (user_id, username, player_name, password_key, is_registered, language) VALUES (%s, %s, %s, %s, TRUE, %s)", (uid, message.from_user.username or '', name, password, lang), commit=True)
    await state.clear()
    await message.answer(t(uid, "register_success", name=name, password=password))
    await message.answer("يرجى إدخال اسم مستخدم (يوزر نيم) خاص بك (حروف إنجليزية وأرقام فقط، 3 أحرف على الأقل):")
    await state.set_state(RoomStates.upgrade_username)
    

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
    if not user[0].get('password') and not user[0].get('password_key'):
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
    pwd = user[0].get('password_key') or user[0].get('password', '')
    if message.text.strip() != pwd:
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
    await show_main_menu(message, name, user_id=uid)

@router.callback_query(F.data == "random_play")
async def menu_random(c: types.CallbackQuery):
    uid = c.from_user.id
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if not user:
        await c.answer(t(uid, "room_not_found"), show_alert=True)
        return

    # البحث عن غرفة عشوائية تنتظر لاعب ثانٍ
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
            except Exception:
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
        await c.message.edit_text(t(uid, "🤌🏻اصبر شوي "), reply_markup=kb)


@router.callback_query(F.data == "menu_friends")
async def menu_friends(c: types.CallbackQuery):
    uid = c.from_user.id
    kb = [
        [InlineKeyboardButton(text=t(uid, "➕ إنشاء غرفة"), callback_data="room_create_start")],
        [InlineKeyboardButton(text=t(uid, "🚪 انضمام لغرفة"), callback_data="room_join_input")],
        [InlineKeyboardButton(text=t(uid, "الغرف المفتوحة"), callback_data="my_open_rooms")],
        [InlineKeyboardButton(text=t(uid, "btn_public_rooms"), callback_data="public_rooms")],
        [InlineKeyboardButton(text=t(uid, "الرجوع"), callback_data="home")]
    ]
    await c.message.edit_text(t(uid, "friends_menu"), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "random_play")
async def random_play(c: types.CallbackQuery):
    uid = c.from_user.id
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if not user:
        await c.answer(t(uid, "room_not_found"), show_alert=True)
        return
    kb = [
        [InlineKeyboardButton(text="✅ نعم، ابحث عن خصم", callback_data="random_search_confirm")],
        [InlineKeyboardButton(text="❌ لا، رجوع", callback_data="home")]
    ]
    await c.message.edit_text(
        "🎮 **اللعب العشوائي**\n\n"
        "سيتم البحث عن خصم مناسب لك.\n"
        "هل أنت متأكد من البدء؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@router.callback_query(F.data == "random_search_confirm")
async def random_search_confirm(c: types.CallbackQuery):
    uid = c.from_user.id
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if not user:
        await c.answer(t(uid, "room_not_found"), show_alert=True)
        return
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
                await c.bot.send_message(p['user_id'], "🎮 بدأت اللعبة! استعد...")
            except Exception:
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
            [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
        ])
        await c.message.edit_text("⏳ جاري البحث عن خصم... يرجى الانتظار", reply_markup=kb)
    
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




# --- زر تعديل حسابي داخل خانة حسابي ---
def _get_follow_counts(user_id):
    """عدد المتابعين (الذين يتابعونه) وعدد من يتابع (الذي يتابعهم)"""
    fol = db_query("SELECT COUNT(*) AS c FROM follows WHERE following_id = %s", (user_id,))
    ing = db_query("SELECT COUNT(*) AS c FROM follows WHERE follower_id = %s", (user_id,))
    return (fol[0]['c'] if fol else 0), (ing[0]['c'] if ing else 0)

@router.callback_query(F.data == "my_account")
async def show_profile(c: types.CallbackQuery):
    user_data = db_query("SELECT * FROM users WHERE user_id = %s", (c.from_user.id,))
    if not user_data: return await c.answer("⚠️ حسابك غير مسجل.")
    
    user = user_data[0]
    uid = c.from_user.id
    followers_count, following_count = _get_follow_counts(uid)
    txt = (
    f"👤 **معلومات حسابك**\n\n"
    f"📛 اسم اللاعب: {user['player_name']}\n"
    f"🔑 الرمز السري: `{user.get('password_key') or user.get('password') or 'لا يوجد'}`\n"
    f"🆔 اليوزر نيم: @{user.get('username_key') or '---'}\n"
    f"⭐ عدد النقاط: {user.get('online_points', 0)}\n"
    f"📈 عدد المتابعين (الذين يتابعونك): {followers_count}\n"
    f"📉 عدد من تتابعهم: {following_count}"
    )
    kb = [
        [InlineKeyboardButton(text="✏️ تعديل بيانات الحساب", callback_data="edit_account"), InlineKeyboardButton(text="⚙️ الإعدادات", callback_data="my_settings")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="home")]
    ]
    await c.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- إنشاء غرفة وإعطاء "رابط" بدل الكود ---
@router.callback_query(F.data.startswith("roomset_"))
async def create_friends_room(c: types.CallbackQuery, state: FSMContext):
    limit = int(c.data.split("_")[1])
    data = await state.get_data()
    p_count = data.get("p_count", 2)
    
    import random, string
    room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # حفظ الغرفة في الداتابيز
    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit) VALUES (%s, %s, %s, %s)", 
    (room_id, c.from_user.id, p_count, limit), commit=True)
    
    # إضافة المنشئ
    user_db = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    p_name = user_db[0]['player_name'] if user_db else c.from_user.full_name
    db_query("INSERT INTO room_players (room_id, user_id, player_name, join_order) VALUES (%s, %s, %s, %s)",
    (room_id, c.from_user.id, p_name, 1), commit=True)
    
    # إنشاء الرابط (تلقائياً باستخدام يوزر البوت)
    bot_info = await c.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=join_{room_id}"
    
    text = (
    f"✅ **تم إنشاء الغرفة بنجاح!**\n\n"
    f"🎯 السقف: {limit}\n"
    f"👥 اللاعبين: {p_count}\n\n"
    f"🔗 **رابط الدعوة المباشر:**\n`{invite_link}`\n\n"
    f"أرسل الرابط لصديقك، وبمجرد الضغط عليه سيدخل للعبة فوراً!"
    )
    kb = [[InlineKeyboardButton(text="공 مشاركة الرابط", url=f"https://t.me/share/url?url={invite_link}&text=تعال العب وياي اونو!")] ,
    [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="home")]]
    
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# 2. دالة عرض أزرار السقف (للعب مع الأصدقاء)
@router.callback_query(F.data.startswith("setp_"))
async def ask_score_limit(c: types.CallbackQuery, state: FSMContext):
    p_count = int(c.data.split("_")[1])
    await state.update_data(p_count=p_count)
    
    limits = [100, 150, 200, 250, 300, 400, 500]
    kb = []
    row = []
    for val in limits:
        row.append(InlineKeyboardButton(text=f"🎯 {val}", callback_data=f"roomset_{val}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton(text="🃏 جولة واحدة", callback_data="roomset_0")])
    kb.append([InlineKeyboardButton(text="🏆 بطولة 3 جولات", callback_data="roomset_tournament_3")])
    kb.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="home")])
    await c.message.edit_text(
        f"🔢 الغرفة لـ {p_count} لاعبين.\nحدد سقف النقاط لإنهاء اللعبة:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

# 3. دالة إنشاء الغرفة (تشتغل فوراً بعد ما اللاعب يختار السقف)
@router.callback_query(F.data.startswith("roomset_"))
async def create_friends_room(c: types.CallbackQuery, state: FSMContext):
    parts = c.data.split("_")
    if len(parts) >= 3 and parts[1] == "tournament":
        limit = 0
        tournament_rounds = int(parts[2]) if parts[2].isdigit() else 3
        is_tournament = True
    else:
        limit = int(parts[1]) if parts[1].isdigit() else 0
        tournament_rounds = 0
        is_tournament = False
    data = await state.get_data()
    p_count = data.get("p_count", 2)
    
    import random, string
    room_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    try:
        db_query("""INSERT INTO rooms (room_id, creator_id, max_players, score_limit, is_tournament, tournament_rounds, tournament_current_round)
        VALUES (%s, %s, %s, %s, %s, %s, 1)""",
            (room_id, c.from_user.id, p_count, limit, is_tournament, tournament_rounds), commit=True)
    except Exception:
        db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit) VALUES (%s, %s, %s, %s)",
            (room_id, c.from_user.id, p_count, limit), commit=True)
    
    # إضافة المنشئ للغرفة
    user_db = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    p_name = user_db[0]['player_name'] if user_db else c.from_user.full_name
    db_query("INSERT INTO room_players (room_id, user_id, player_name, join_order) VALUES (%s, %s, %s, %s)",
    (room_id, c.from_user.id, p_name, 1), commit=True)
    
    if is_tournament:
        text = f"✅ **تم إنشاء بطولة مصغرة!**\n\n🔢 الكود: `{room_id}`\n👥 العدد: {p_count}\n🏆 الجولات: {tournament_rounds}\n\nأرسل الكود لأصدقائك للانضمام. الفائز يُحدد بعد {tournament_rounds} جولات."
    else:
        text = f"✅ **تم إنشاء الغرفة بنجاح!**\n\n🔢 الكود: `{room_id}`\n👥 العدد: {p_count}\n🎯 السقف: {limit}\n\nأرسل الكود لأصدقائك للانضمام."
    kb = [[InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="home")]]
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    

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
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)", (code, uid, u_name), commit=True)

    followed = db_query("""
    SELECT u.user_id, u.player_name FROM follows f
    JOIN users u ON f.following_id = u.user_id
    WHERE f.follower_id = %s
    ORDER BY u.player_name
    """, (uid,))
    bot_info = await c.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=join_{code}"

    kb_invite = []
    if followed:
        for f in followed:
            kb_invite.append([InlineKeyboardButton(text=f"👤 {f['player_name']}", callback_data=f"finv_{code}_{f['user_id']}")])
        kb_invite.append([InlineKeyboardButton(text="📨 إرسال الدعوات", callback_data=f"finvsend_{code}")])
    kb_invite.append([InlineKeyboardButton(text="🔗 رابط الدعوة (أرسله لأي لاعب)", callback_data=f"finvskip_{code}")])
    kb_invite.append([InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")])
    if code not in friend_invite_selections:
        friend_invite_selections[code] = set()

    msg = f"✅ تم إنشاء الغرفة!\n\n👥 اختر اللاعبين الذين تتابعهم لإرسال دعوة، أو استخدم الرابط لأي لاعب:\n{link}"
    await c.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_invite))
    await state.clear()

@router.callback_query(F.data == "public_rooms")
async def list_public_rooms(c: types.CallbackQuery):
    uid = c.from_user.id
    try:
        rooms = db_query("""
            SELECT r.room_id, r.max_players,
                   (SELECT count(*) FROM room_players rp WHERE rp.room_id = r.room_id) as p_count
            FROM rooms r
            WHERE r.status = 'waiting'
            ORDER BY r.room_id DESC LIMIT 20
        """)
    except Exception:
        rooms = []
    if not rooms:
        text = t(uid, "public_rooms_title") + "\n\n" + t(uid, "public_rooms_none")
        kb = [[InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="menu_friends")]]
    else:
        text = t(uid, "public_rooms_title")
        kb = []
        for r in rooms:
            code = r.get("room_id", "")
            cur = r.get("p_count") or 0
            mx = r.get("max_players") or 2
            if cur >= mx:
                continue
            kb.append([InlineKeyboardButton(
                text=t(uid, "public_room_row", code=code, current=cur, max=mx),
                callback_data=f"join_public_{code}"
            )])
        kb.append([InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="menu_friends")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await c.answer()

@router.callback_query(F.data.startswith("join_public_"))
async def join_public_room(c: types.CallbackQuery):
    code = c.data.replace("join_public_", "", 1)
    uid = c.from_user.id
    room = db_query("SELECT * FROM rooms WHERE room_id = %s AND status = 'waiting'", (code,))
    if not room:
        return await c.answer(t(uid, "room_gone"), show_alert=True)
    existing = db_query("SELECT 1 FROM room_players WHERE room_id = %s AND user_id = %s", (code, uid))
    if existing:
        return await c.answer(t(uid, "already_in_room"), show_alert=True)
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    u_name = u_name[0]["player_name"] if u_name else c.from_user.full_name
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)", (code, uid, u_name), commit=True)
    p_count = db_query("SELECT count(*) as count FROM room_players WHERE room_id = %s", (code,))[0]["count"]
    max_p = room[0]["max_players"]
    if p_count >= max_p:
        db_query("UPDATE rooms SET status = 'playing' WHERE room_id = %s", (code,), commit=True)
        all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
        for p in all_players:
            try:
                await c.bot.send_message(p["user_id"], t(p["user_id"], "game_starting_multi", n=max_p))
            except Exception:
                pass
        from handlers.room_multi import start_game_multi
        await start_game_multi(code, c.bot)
    else:
        players = db_query("SELECT player_name FROM room_players WHERE room_id = %s", (code,))
        plist = ", ".join([p["player_name"] for p in players])
        await c.message.edit_text(t(uid, "player_joined", name=u_name, count=p_count, max=max_p, list=plist) + t(uid, "waiting_players", n=max_p - p_count))
    await c.answer()

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
        except Exception:
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
                try:
                    await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_2p"))
                except Exception:
                    pass
            from handlers.room_2p import start_new_round
            await start_new_round(code, message.bot, start_turn_idx=0)
        else:
            for p in all_players:
                try:
                    await message.bot.send_message(p['user_id'], t(p['user_id'], "game_starting_multi", n=max_p))
                except Exception:
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
        except Exception:
            pass

@router.callback_query(F.data.startswith("view_profile_"))
async def view_profile_handler(c: types.CallbackQuery):
    try:
        target_id = int(c.data.split("_")[-1])
        await process_user_search_by_id(c, target_id)
    except Exception as e:
        print(f"view_profile_handler error: {e}")
        await c.answer("⚠️ فشل فتح بروفايل اللاعب.", show_alert=True)


async def process_user_search_by_id(c: types.CallbackQuery, target_id: int):
    uid = c.from_user.id

    # جلب اللاعب المطلوب
    target = db_query("SELECT * FROM users WHERE user_id = %s", (target_id,))
    if not target:
        return await c.answer("❌ اللاعب غير موجود.", show_alert=True)

    t_user = target[0]

    # هل أنت متابعه؟
    is_following = db_query(
    "SELECT 1 FROM follows WHERE follower_id = %s AND following_id = %s",
    (uid, target_id)
    )

    # حالة الأونلاين
    from datetime import datetime, timedelta
    last_seen = t_user.get("last_seen")
    if last_seen:
        online = (datetime.now() - last_seen < timedelta(minutes=5))
        status = t(uid, "status_online") if online else t(uid, "status_offline", time=last_seen.strftime("%H:%M"))
    else:
        status = t(uid, "status_offline", time="--:--")

    # نص البروفايل + إنجازات
    text = t(
        uid,
        "profile_title",
        name=t_user.get("player_name", "لاعب"),
        username=t_user.get("username_key", "---"),
        points=t_user.get("online_points", 0),
        status=status
    )
    badges = get_user_achievements(target_id)
    if badges:
        text += format_achievements_badges(uid, badges)

    follow_btn_text = t(uid, "btn_unfollow") if is_following else t(uid, "btn_follow")
    follow_callback = f"unfollow_{target_id}" if is_following else f"follow_{target_id}"

    kb = [
        [InlineKeyboardButton(text=follow_btn_text, callback_data=follow_callback)],
        [InlineKeyboardButton(text=t(uid, "btn_invite_play"), callback_data=f"invite_{target_id}")],
    ]
    if (uid, target_id) in invite_mutes:
        kb.append([InlineKeyboardButton(text="✏️ تعديل الكتم", callback_data=f"mute_inv_{target_id}")])
    kb.append([InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="social_menu")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    

async def show_main_menu(message, name, user_id, cleanup=False, state=None):
    # 1. تنظيف الحالة
    if state:
        await state.clear()
    # 2. جلب بيانات المستخدم
    user_rows = db_query("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if not user_rows:
        return
    uid = user_id
    # 3. شرط اليوزر نيم
    if not user_rows[0].get('username_key'):
        target_msg = message.message if isinstance(message, types.CallbackQuery) else message
        await target_msg.answer("⚠️ يرجى إدخال اسم مستخدم (يوزر نيم) خاص بك (حروف إنجليزية وأرقام فقط):")
        if state:
            await state.set_state(RoomStates.upgrade_username)
        return
    # 3.5 تعليم تفاعلي (أول استخدام)
    try:
        seen = (user_id in _tutorial_done_cache) or (user_rows[0].get('seen_tutorial') in (True, 1, 't', 'true'))
    except Exception:
        seen = user_id in _tutorial_done_cache
    if not seen:
        target_msg = message.message if isinstance(message, types.CallbackQuery) else message
        txt = t(uid, "tutorial_title") + "\n\n" + t(uid, "tutorial_body")
        kb_tut = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(uid, "tutorial_btn"), callback_data="tutorial_done")]])
        try:
            await target_msg.answer(txt, reply_markup=kb_tut, parse_mode="Markdown")
        except Exception:
            pass
        return
    # 4. بناء الكيبورد
    kb = [
        [InlineKeyboardButton(text=t(uid, "btn_random_play"), callback_data="random_play")],
        [InlineKeyboardButton(text=t(uid, "btn_play_friends"), callback_data="play_friends")],
        [InlineKeyboardButton(text=t(uid, "btn_friends"), callback_data="social_menu")],
        [InlineKeyboardButton(text=t(uid, "btn_my_account"), callback_data="my_account"),
         InlineKeyboardButton(text=t(uid, "btn_calc"), callback_data="mode_calc")],
        [InlineKeyboardButton(text=t(uid, "btn_rules"), callback_data="rules")],
        [InlineKeyboardButton(text=t(uid, "btn_leaderboard"), callback_data="leaderboard")],
        [InlineKeyboardButton(text=t(uid, "btn_change_lang"), callback_data="change_lang")],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    
    msg_text = t(uid, "main_menu", name=name)

    # 5. وظيفة تنظيف الرسائل
    async def _cleanup_last_messages(msg_obj, limit=15):
        if not cleanup:
            return
        try:
            last_id = msg_obj.message_id
            for mid in range(last_id, max(last_id - limit, 1), -1):
                try:
                    await msg_obj.bot.delete_message(msg_obj.chat.id, mid)
                except Exception:
                    pass
        except Exception:
            pass
    # 6. إرسال الرسالة النهائية
    if isinstance(message, types.CallbackQuery):
        await _cleanup_last_messages(message.message, limit=15)
        try:
            await message.message.edit_text(msg_text, reply_markup=markup)
        except Exception:
            await message.message.answer(msg_text, reply_markup=markup)
        await message.answer(t(uid, "menu_updated"))
    else:
        await _cleanup_last_messages(message, limit=15)
        await message.answer(msg_text, reply_markup=markup)

@router.callback_query(F.data == "tutorial_done")
async def tutorial_done(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    _tutorial_done_cache.add(uid)
    try:
        db_query("UPDATE users SET seen_tutorial = TRUE WHERE user_id = %s", (uid,), commit=True)
    except Exception:
        pass
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    name = user[0]['player_name'] if user else c.from_user.full_name
    await c.answer()
    await show_main_menu(c.message, name, uid, state=state)

@router.callback_query(F.data == "change_lang")
async def change_lang_menu(c: types.CallbackQuery):
    """عرض قائمة اختيار اللغة عند الضغط على زر تغيير اللغة"""
    uid = c.from_user.id
    text = t(uid, "choose_language")
    kb = [
        [InlineKeyboardButton(text="🇮🇶 العربية", callback_data="switch_lang_ar")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="switch_lang_en")],
        [InlineKeyboardButton(text="🇮🇷 فارسی", callback_data="switch_lang_fa")],
        [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
    ]
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await c.answer()

@router.callback_query(F.data.startswith("switch_lang_"))
async def switch_lang(c: types.CallbackQuery):
    uid = c.from_user.id
    lang = c.data.split("_")[-1]
    db_query("UPDATE users SET language = %s WHERE user_id = %s", (lang, uid), commit=True)
    set_lang(uid, lang)
    await c.answer(t(uid, "lang_changed"), show_alert=True)
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (uid,))
    name = user[0]['player_name'] if user else 'Player'
    await show_main_menu(c.message, name, uid)

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
    except Exception:
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

# طلب الصداقة أُزيل: نستخدم المتابعة الفورية فقط. لو وُجد زر قديم addfrnd_ نحوّله لمتابعة
@router.callback_query(F.data.startswith("addfrnd_"))
async def add_friend_as_follow(c: types.CallbackQuery):
    target_id = int(c.data.split("_")[1])
    uid = c.from_user.id
    if uid == target_id:
        return await c.answer("🧐 لا يمكنك متابعة نفسك!", show_alert=True)
    try:
        db_query("INSERT INTO follows (follower_id, following_id) VALUES (%s, %s)", (uid, target_id), commit=True)
        await c.answer("✅ تمت المتابعة بنجاح!")
    except Exception:
        await c.answer("⚠️ أنت تتابع هذا اللاعب بالفعل.", show_alert=True)
    await process_user_search_by_id(c, target_id)

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
    followed = db_query("""
    SELECT u.user_id, u.player_name FROM follows f
    JOIN users u ON f.following_id = u.user_id
    WHERE f.follower_id = %s
    ORDER BY u.player_name
    """, (c.from_user.id,))
    kb_invite = []
    for f in followed:
        check = "✅" if f['user_id'] in sel else "👤"
        kb_invite.append([InlineKeyboardButton(text=f"{check} {f['player_name']}", callback_data=f"finv_{code}_{f['user_id']}")])
    kb_invite.append([InlineKeyboardButton(text=f"📨 إرسال الدعوات ({len(sel)})", callback_data=f"finvsend_{code}")])
    kb_invite.append([InlineKeyboardButton(text="🔗 رابط الدعوة (أرسله لأي لاعب)", callback_data=f"finvskip_{code}")])
    kb_invite.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")])
    bot_info = await c.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=join_{code}"
    await c.message.edit_text(f"✅ تم إنشاء الغرفة!\n\n👥 اختر اللاعبين الذين تتابعهم (اضغط على الاسم لتحديده)، أو أرسل الرابط لأي لاعب:\n{link}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_invite))

@router.callback_query(F.data.startswith("finvsend_"))
async def send_friend_invites(c: types.CallbackQuery):
    code = c.data.split("_")[1]
    sel = friend_invite_selections.pop(code, set())
    if not sel:
        return await c.answer("⚠️ لم تختر أي لاعب! أو استخدم رابط الدعوة لأي شخص.", show_alert=True)
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
            await c.bot.send_message(fid, f"📨 {u_name} يدعوك للعب!\n\n⏳ عندك 30 ثانية للرد\nهل تريد الانضمام؟", reply_markup=inv_kb)
            sent += 1
        except Exception:
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
    await c.message.edit_text(f"📨 تم إرسال {sent} دعوة!\n⏳ بانتظار الردود...\n\n🎮 هذا رابط الدخول للعبة، انقر الرابط للدخول:\n{link}", reply_markup=wait_kb)
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
    await c.message.edit_text(f"🎮 هذا رابط الدخول للعبة، انقر الرابط للدخول:\n{link}", reply_markup=kb_code)

@router.callback_query(F.data.startswith("rsettings_"))
async def room_settings(c: types.CallbackQuery):
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['creator_id'] != c.from_user.id:
        return await c.answer("⚠️ فقط صاحب الغرفة يقدر يدخل الإعدادات!", show_alert=True)
    is_playing = room[0]['status'] == 'playing'
    score_text = f"🎯 {room[0]['score_limit']}" if room[0]['score_limit'] > 0 else "🃏 جولة واحدة"
    players = db_query("SELECT user_id, player_name FROM room_players WHERE room_id = %s", (code,))
    p_count = len(players)
    kb = [
        [InlineKeyboardButton(text="🚫 طرد لاعبين", callback_data=f"rkicklist_{code}")],
        [InlineKeyboardButton(text=f"🔢 تغيير سقف اللعب ({score_text})", callback_data=f"rchglimit_{code}")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data=f"rsetback_{code}")]
    ]
    await c.message.edit_text(f"⚙️ إعدادات الغرفة\n\n👥 عدد اللاعبين: {p_count}/{room[0]['max_players']}\n📊 سقف النقاط: {score_text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

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
        [InlineKeyboardButton(text="⚙️ إعدادات الغرفة", callback_data=f"rsettings_{code}")],
        [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
    ])
    await c.message.edit_text(txt, reply_markup=kb)

@router.callback_query(F.data.startswith("rkicklist_"))
async def kick_player_list(c: types.CallbackQuery):
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['creator_id'] != c.from_user.id:
        return await c.answer("⚠️ فقط صاحب الغرفة يقدر يطرد!", show_alert=True)
    players = db_query("SELECT user_id, player_name FROM room_players WHERE room_id = %s AND user_id != %s", (code, c.from_user.id))
    if not players:
        return await c.answer("⚠️ ما في لاعبين ثانيين في الغرفة!", show_alert=True)
    if code not in kick_selections:
        kick_selections[code] = set()
    existing_ids = {p['user_id'] for p in players}
    kick_selections[code] = kick_selections[code] & existing_ids
    kb = []
    for p in players:
        selected = p['user_id'] in kick_selections[code]
        mark = "✅" if selected else "⬜"
        kb.append([InlineKeyboardButton(text=f"{mark} {p['player_name']}", callback_data=f"rkickp_{code}_{p['user_id']}")])
    selected_count = len(kick_selections[code])
    if selected_count > 0:
        kb.append([InlineKeyboardButton(text=f"🚫 طرد المحددين ({selected_count})", callback_data=f"rkickgo_{code}")])
    kb.append([InlineKeyboardButton(text="🔙 رجوع", callback_data=f"rsettings_{code}")])
    await c.message.edit_text("🚫 حدد اللاعبين اللي تبي تطردهم:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("rkickp_"))
async def kick_player_toggle(c: types.CallbackQuery):
    parts = c.data.split("_")
    code = parts[1]
    target_id = int(parts[2])
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['creator_id'] != c.from_user.id:
        return await c.answer("⚠️ فقط صاحب الغرفة يقدر يطرد!", show_alert=True)
    if code not in kick_selections:
        kick_selections[code] = set()
    if target_id in kick_selections[code]:
        kick_selections[code].discard(target_id)
    else:
        kick_selections[code].add(target_id)
    c.data = f"rkicklist_{code}"
    await kick_player_list(c)

@router.callback_query(F.data.startswith("rkickgo_"))
async def kick_player_confirm(c: types.CallbackQuery):
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['creator_id'] != c.from_user.id:
        return await c.answer("⚠️ فقط صاحب الغرفة يقدر يطرد!", show_alert=True)
    selected = kick_selections.get(code, set())
    if not selected:
        return await c.answer("⚠️ ما حددت أحد!", show_alert=True)
    names = []
    for uid in selected:
        p = db_query("SELECT player_name FROM room_players WHERE room_id = %s AND user_id = %s", (code, uid))
        if p:
            names.append(p[0]['player_name'])
    names_text = "، ".join(names)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ نعم، اطردهم", callback_data=f"rkickyes_{code}"),
         InlineKeyboardButton(text="❌ لا", callback_data=f"rkicklist_{code}")]
    ])
    await c.message.edit_text(f"⚠️ هل أنت متأكد من طرد:\n{names_text}؟", reply_markup=kb)

@router.callback_query(F.data.startswith("rkickyes_"))
async def kick_player_execute(c: types.CallbackQuery):
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['creator_id'] != c.from_user.id:
        return await c.answer("⚠️ فقط صاحب الغرفة يقدر يطرد!", show_alert=True)
    selected = kick_selections.pop(code, set())
    if not selected:
        return await c.answer("⚠️ ما حددت أحد!", show_alert=True)
    kicked_names = []
    for target_id in selected:
        target = db_query("SELECT player_name FROM room_players WHERE room_id = %s AND user_id = %s", (code, target_id))
        if target:
            kicked_names.append(target[0]['player_name'])
        db_query("DELETE FROM room_players WHERE room_id = %s AND user_id = %s", (code, target_id), commit=True)
        try:
            await c.bot.send_message(target_id, "🚫 تم طردك من الغرفة بواسطة صاحب الغرفة.")
        except Exception:
            pass
    await c.answer(f"✅ تم طرد {len(kicked_names)} لاعب!", show_alert=True)
    c.data = f"rsettings_{code}"
    await room_settings(c)

@router.callback_query(F.data.startswith("rchglimit_"))
async def change_score_limit(c: types.CallbackQuery):
    code = c.data.split("_", 1)[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['creator_id'] != c.from_user.id:
        return await c.answer("⚠️ فقط صاحب الغرفة يقدر يغير السقف!", show_alert=True)
    limits = [100, 150, 200, 250, 300, 350, 400, 450, 500]
    current = room[0]['score_limit']
    kb = []
    row = []
    for val in limits:
        label = f"✅ {val}" if val == current else f"🎯 {val}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"rnewlimit_{code}_{val}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    one_round_label = "✅ جولة واحدة" if current == 0 else "🃏 جولة واحدة"
    kb.append([InlineKeyboardButton(text=one_round_label, callback_data=f"rnewlimit_{code}_0")])
    kb.append([InlineKeyboardButton(text="🔙 رجوع", callback_data=f"rsettings_{code}")])
    await c.message.edit_text(f"🔢 اختر سقف النقاط الجديد:\n\n📊 السقف الحالي: {current if current > 0 else 'جولة واحدة'}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("rnewlimit_"))
async def set_new_score_limit(c: types.CallbackQuery):
    parts = c.data.split("_")
    code = parts[1]
    new_limit = int(parts[2])
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room:
        return await c.message.edit_text("⚠️ الغرفة لم تعد موجودة.")
    if room[0]['creator_id'] != c.from_user.id:
        return await c.answer("⚠️ فقط صاحب الغرفة يقدر يغير السقف!", show_alert=True)
    db_query("UPDATE rooms SET score_limit = %s WHERE room_id = %s", (new_limit, code), commit=True)
    limit_text = f"🎯 {new_limit}" if new_limit > 0 else "🃏 جولة واحدة"
    await c.answer(f"✅ تم تغيير سقف النقاط إلى: {limit_text}", show_alert=True)
    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s AND user_id != %s", (code, c.from_user.id))
    for p in players:
        try:
            await c.bot.send_message(p['user_id'], f"📢 صاحب الغرفة غيّر سقف النقاط إلى: {limit_text}")
        except Exception:
            pass
    c.data = f"rsettings_{code}"
    await room_settings(c)

@router.callback_query(F.data == "my_account")
async def process_my_account_callback(c: types.CallbackQuery):
    uid = c.from_user.id
    user_data = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if not user_data:
        return await c.answer("⚠️ حسابك غير موجود.")
    user = user_data[0]
    name = user.get('player_name', 'لاعب')
    username = user.get('username_key') or "---"
    points = user.get('online_points', 0)
    password = user.get('password_key') or user.get('password', '----')
    followers_count, following_count = _get_follow_counts(uid)
    text = (
        f"👤 **حسابي**\n\n"
        f"📛 اسم اللاعب: {name}\n"
        f"🔑 الرمز السري: `{password}`\n"
        f"🆔 اليوزر نيم: @{username}\n"
        f"⭐ عدد النقاط: {points}\n"
        f"📈 عدد المتابعين (الذين يتابعونك): {followers_count}\n"
        f"📉 عدد من تتابعهم: {following_count}"
    )
    kb = [
        [InlineKeyboardButton(text="✏️ تعديل حسابي", callback_data="edit_account"), InlineKeyboardButton(text="⚙️ الإعدادات", callback_data="my_settings")],
        [InlineKeyboardButton(text="📜 سجل المباريات", callback_data="match_history")],
        [InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="home")]
    ]
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "match_history")
async def show_match_history(c: types.CallbackQuery):
    uid = c.from_user.id
    try:
        rows = db_query(
            "SELECT room_id, round_num, created_at FROM match_results WHERE winner_id = %s ORDER BY created_at DESC LIMIT 15",
            (uid,)
        )
    except Exception:
        rows = []
    if not rows:
        text = t(uid, "match_history_title") + "\n\n" + t(uid, "match_history_none")
    else:
        lines = [t(uid, "match_history_title") + "\n"]
        for r in rows:
            lines.append(t(uid, "match_history_row", round=r.get("round_num", 1), room=r.get("room_id", "—")))
        text = "\n".join(lines)
    kb = [[InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="my_account")]]
    try:
        await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except Exception:
        await c.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()

@router.callback_query(F.data == "my_settings")
async def my_settings_menu(c: types.CallbackQuery):
    uid = c.from_user.id
    text = "⚙️ **الإعدادات**"
    kb = [
        [InlineKeyboardButton(text="📩 استقبال الدعوات", callback_data="settings_invites")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="my_account")]
    ]
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await c.answer()

def _get_invite_from(uid):
    """من يمكنه إرسال دعوة لعب له: all / following / followers"""
    row = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if not row:
        return "all"
    return row[0].get("invite_from") or "all"

@router.callback_query(F.data == "settings_invites")
async def settings_invites_ui(c: types.CallbackQuery):
    uid = c.from_user.id
    current = _get_invite_from(uid)
    check = "✅"
    cross = "❌"
    kb = [
        [InlineKeyboardButton(text=f"من الجميع {check if current == 'all' else cross}", callback_data="set_invite_from_all")],
        [InlineKeyboardButton(text=f"من الذين أتابعهم فقط {check if current == 'following' else cross}", callback_data="set_invite_from_following")],
        [InlineKeyboardButton(text=f"من الذين يتابعونني فقط {check if current == 'followers' else cross}", callback_data="set_invite_from_followers")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="my_settings")]
    ]
    text = (
        "📩 **استقبال الدعوات**\n\n"
        "اختر من يمكنه إرسال دعوة لعب لك:\n"
        "• **من الجميع:** أي شخص يمكنه دعوتك.\n"
        "• **من الذين أتابعهم:** فقط من تتابعهم يمكنهم دعوتك.\n"
        "• **من الذين يتابعونني:** فقط من يتابعونك يمكنهم دعوتك."
    )
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await c.answer()

@router.callback_query(F.data.startswith("set_invite_from_"))
async def set_invite_from(c: types.CallbackQuery):
    uid = c.from_user.id
    value = c.data.replace("set_invite_from_", "")
    if value not in ("all", "following", "followers"):
        await c.answer("⚠️ خطأ.", show_alert=True)
        return
    try:
        db_query("UPDATE users SET invite_from = %s WHERE user_id = %s", (value, uid), commit=True)
    except Exception:
        await c.answer("⚠️ تعذر حفظ الإعداد. (قد تحتاج إضافة عمود invite_from لجدول users)", show_alert=True)
        return
    await c.answer("✅ تم الحفظ.", show_alert=True)
    await settings_invites_ui(c)

@router.callback_query(F.data == "edit_account")
async def edit_account_menu(c: types.CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="📛 تغيير الاسم", callback_data="change_name")],
        [InlineKeyboardButton(text="🆔 تغيير اليوزر نيم", callback_data="change_username")],
        [InlineKeyboardButton(text="🔑 تغيير الرمز السري", callback_data="change_password")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="my_account")]
    ]
    await c.message.edit_text("✏️ ماذا تريد تعديله؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "change_name")
async def ask_new_name(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("📛 أرسل الاسم الجديد:")
    await state.set_state(RoomStates.edit_name)

@router.message(RoomStates.edit_name)
async def process_new_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if len(new_name) < 1 or len(new_name) > 30:
        return await message.answer("❌ الاسم لازم يكون بين 1 و 30 حرف. حاول مرة ثانية:")
    db_query("UPDATE users SET player_name = %s WHERE user_id = %s", (new_name, message.from_user.id), commit=True)
    await state.clear()
    await message.answer(f"✅ تم تغيير الاسم إلى: {new_name}")
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    if user:
        u = user[0]
        uid = message.from_user.id
        fc, ing = _get_follow_counts(uid)
        txt = f"👤 حسابي\n\n📛 اسم اللاعب: {u['player_name']}\n🔑 الرمز السري: {u.get('password_key') or 'لا يوجد'}\n🆔 اليوزر نيم: @{u.get('username_key') or '---'}\n⭐ النقاط: {u.get('online_points', 0)}\n📈 المتابعون: {fc}\n📉 من تتابع: {ing}"
        kb = [
            [InlineKeyboardButton(text="✏️ تعديل الحساب", callback_data="edit_account")],
            [InlineKeyboardButton(text="🚪 تسجيل الخروج", callback_data="logout_confirm")],
            [InlineKeyboardButton(text="🔙 رجوع", callback_data="home")]
        ]
        await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "change_username")
async def ask_new_username(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("🆔 أرسل اليوزر نيم الجديد (حروف إنجليزية وأرقام فقط، 3 أحرف على الأقل):")
    await state.set_state(RoomStates.edit_username)

@router.message(RoomStates.edit_username)
async def process_new_username(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    new_username = message.text.strip().lower().replace("@", "")
    if len(new_username) < 3 or not new_username.isalnum():
        return await message.answer("❌ اليوزر نيم لازم 3 أحرف أو أكثر (إنجليزي وأرقام فقط). حاول مرة ثانية:")
    existing = db_query("SELECT user_id FROM users WHERE username_key = %s AND user_id != %s", (new_username, uid))
    if existing:
        return await message.answer("❌ هذا اليوزر نيم محجوز لشخص آخر. اختر غيره:")
    db_query("UPDATE users SET username_key = %s WHERE user_id = %s", (new_username, uid), commit=True)
    await state.clear()
    await message.answer(f"✅ تم تغيير اليوزر نيم إلى: @{new_username}")
    user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
    if user:
        u = user[0]
        fc, ing = _get_follow_counts(uid)
        txt = f"👤 حسابي\n\n📛 اسم اللاعب: {u['player_name']}\n🔑 الرمز السري: {u.get('password_key') or 'لا يوجد'}\n🆔 اليوزر نيم: @{u.get('username_key') or '---'}\n⭐ النقاط: {u.get('online_points', 0)}\n📈 المتابعون: {fc}\n📉 من تتابع: {ing}"
        kb = [
            [InlineKeyboardButton(text="✏️ تعديل الحساب", callback_data="edit_account")],
            [InlineKeyboardButton(text="🚪 تسجيل الخروج", callback_data="logout_confirm")],
            [InlineKeyboardButton(text="🔙 رجوع", callback_data="home")]
        ]
        await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "change_password")
async def ask_new_password(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("🔑 أرسل الرمز السري الجديد:")
    await state.set_state(RoomStates.edit_password)

@router.message(RoomStates.edit_password)
async def process_new_password(message: types.Message, state: FSMContext):
    new_pass = message.text.strip()
    if len(new_pass) < 1 or len(new_pass) > 30:
        return await message.answer("❌ الرمز لازم يكون بين 1 و 30 حرف. حاول مرة ثانية:")
    db_query("UPDATE users SET password_key = %s WHERE user_id = %s", (new_pass, message.from_user.id), commit=True)
    await state.clear()
    await message.answer("✅ تم تغيير الرمز السري بنجاح!")
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    if user:
        u = user[0]
        uid = message.from_user.id
        fc, ing = _get_follow_counts(uid)
        txt = f"👤 حسابي\n\n📛 اسم اللاعب: {u['player_name']}\n🔑 الرمز السري: {u.get('password_key') or 'لا يوجد'}\n🆔 اليوزر نيم: @{u.get('username_key') or '---'}\n⭐ النقاط: {u.get('online_points', 0)}\n📈 المتابعون: {fc}\n📉 من تتابع: {ing}"
        kb = [
            [InlineKeyboardButton(text="✏️ تعديل الحساب", callback_data="edit_account")],
            [InlineKeyboardButton(text="🚪 تسجيل الخروج", callback_data="logout_confirm")],
            [InlineKeyboardButton(text="🔙 رجوع", callback_data="home")]
        ]
        await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "logout_confirm")
async def logout_confirm(c: types.CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="✅ نعم، خروج", callback_data="logout_yes")],
        [InlineKeyboardButton(text="❌ لا، رجوع", callback_data="my_account")]
    ]
    await c.message.edit_text("🚪 هل أنت متأكد من تسجيل الخروج؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "logout_yes")
async def logout_yes(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    db_query("UPDATE users SET is_registered = FALSE WHERE user_id = %s", (c.from_user.id,), commit=True)
    await c.message.edit_text("👋 تم تسجيل الخروج بنجاح!\nأرسل /start للتسجيل مرة أخرى.")

@router.callback_query(F.data.startswith("replay_"))
async def replay_menu(c: types.CallbackQuery):
    replay_id = c.data.split("_", 1)[1]
    rdata = replay_data.get(replay_id)
    kb = []
    if rdata and rdata.get('creator_id') == c.from_user.id:
        kb.append([InlineKeyboardButton(text="👥 اللعب مع نفس الفريق", callback_data=f"sameteam_{replay_id}")])
    kb.append([InlineKeyboardButton(text="➕ إنشاء غرفة", callback_data="room_create_start")])
    kb.append([InlineKeyboardButton(text="🚪 انضمام لغرفة", callback_data="room_join_input")])
    kb.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")])
    await c.message.edit_text("🔄 اختر طريقة اللعب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sameteam_"))
async def same_team_invite(c: types.CallbackQuery):
    replay_id = c.data.split("_", 1)[1]
    rdata = replay_data.pop(replay_id, None)
    if not rdata:
        return await c.answer("⚠️ انتهت صلاحية هذا الخيار.", show_alert=True)

    creator_id = c.from_user.id
    other_players = [(uid, uname) for uid, uname in rdata['players'] if uid != creator_id]
    if not other_players:
        return await c.answer("⚠️ لا يوجد لاعبين آخرين للدعوة.", show_alert=True)

    code = generate_room_code()
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    db_query("""INSERT INTO rooms (room_id, creator_id, max_players, score_limit, status, game_mode) 
    VALUES (%s, %s, %s, %s, 'waiting', 'friends')""",
    (code, creator_id, rdata['max_players'], rdata['score_limit']), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", (code, creator_id, u_name), commit=True)

    pending_invites[code] = {
        'creator': creator_id,
        'creator_name': u_name,
        'invited': {uid: uname for uid, uname in other_players},
        'accepted': set(),
        'rejected': set(),
        'max_players': rdata['max_players'],
        'score_limit': rdata['score_limit'],
        'mode': rdata['mode'],
        'replay_id': replay_id
    }
    inv_wait_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
    ])
    await c.message.edit_text(f"📨 تم إرسال الدعوات لـ {len(other_players)} لاعب...\n⏳ بانتظار الردود...", reply_markup=inv_wait_kb)

    for uid, uname in other_players:
        try:
            inv_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ موافق", callback_data=f"invy_{code}"),
                 InlineKeyboardButton(text="❌ رفض", callback_data=f"invn_{code}")]
            ])
            await c.bot.send_message(uid, f"📨 {u_name} يدعوك للعب مرة أخرى مع نفس الفريق!\n\n⏳ عندك 30 ثانية للرد\nهل تريد الانضمام؟", reply_markup=inv_kb)
        except Exception as e:
            print(f"Invite send error to {uid}: {e}")
            pending_invites[code]['rejected'].add(uid)

    asyncio.create_task(_invite_auto_check(code, c.bot))

async def _invite_auto_check(room_id, bot):
    try:
        reminder_sent = False
        for step in range(30):
            await asyncio.sleep(1)
            inv = pending_invites.get(room_id)
            if not inv:
                return
            total_invited = len(inv['invited'])
            total_responded = len(inv['accepted']) + len(inv['rejected'])
            if total_responded >= total_invited:
                break
            # تذكير بعد 15 ثانية لمن لم يرد بعد
            if step == 14 and not reminder_sent:
                reminder_sent = True
                for fid in inv['invited']:
                    if fid in inv['accepted'] or fid in inv['rejected']:
                        continue
                    try:
                        await bot.send_message(fid, t(fid, "invite_reminder"))
                    except Exception:
                        pass
        inv = pending_invites.pop(room_id, None)
        if not inv:
            return
        room_check = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_check or room_check[0]['status'] != 'waiting':
            return
        accepted_names = [inv['invited'][uid] for uid in inv['accepted']]
        rejected_uids = set(inv['invited'].keys()) - inv['accepted']
        for uid in rejected_uids:
            inv['rejected'].add(uid)
        rejected_names = [inv['invited'][uid] for uid in inv['rejected'] if uid in inv['invited']]
        total_players = 1 + len(inv['accepted'])
        if total_players < 2:
            db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
            end_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ إنشاء غرفة", callback_data="room_create_start")],
                [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
            ])
            msg = "❌ لم يقبل أحد الدعوة."
            if rejected_names:
                msg += f"\n\n🚫 رفضوا: {', '.join(rejected_names)}"
            await bot.send_message(inv['creator'], msg, reply_markup=end_kb)
            return
        db_query("UPDATE rooms SET max_players = %s, status = 'playing' WHERE room_id = %s", (total_players, room_id), commit=True)
        status_msg = f"🎮 بدء اللعب مع {total_players} لاعبين!"
        if rejected_names:
            status_msg += f"\n🚫 رفضوا الانضمام: {', '.join(rejected_names)}"
        if accepted_names:
            status_msg += f"\n✅ انضموا: {', '.join(accepted_names)}"
        all_player_ids = [inv['creator']] + list(inv['accepted'])
        for pid in all_player_ids:
            try:
                await bot.send_message(pid, status_msg)
            except Exception:
                pass
        if total_players == 2:
            from handlers.room_2p import start_new_round
            await start_new_round(room_id, bot, start_turn_idx=0)
        else:
            from handlers.room_multi import start_game_multi
            await start_game_multi(room_id, bot)
    except Exception as e:
        print(f"Auto check invite error: {e}")

@router.callback_query(F.data.startswith("invy_"))
async def accept_invite(c: types.CallbackQuery):
    room_id = c.data.split("_", 1)[1]
    inv = pending_invites.get(room_id)
    if not inv:
        return await c.answer("⚠️ انتهت صلاحية الدعوة.", show_alert=True)
    if c.from_user.id not in inv['invited']:
        return await c.answer("⚠️ هذه الدعوة ليست لك.", show_alert=True)
    if c.from_user.id in inv['accepted'] or c.from_user.id in inv['rejected']:
        return await c.answer("⚠️ سبق ورديت على الدعوة.", show_alert=True)
    inv['accepted'].add(c.from_user.id)
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", (room_id, c.from_user.id, u_name), commit=True)

    accept_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
    ])
    await c.message.edit_text("✅ قبلت الدعوة! بانتظار بقية اللاعبين...", reply_markup=accept_kb)
    try:
        await c.bot.send_message(inv['creator'], f"✅ {u_name} قبل الدعوة!")
    except Exception:
        pass

@router.callback_query(F.data.startswith("invn_"))
async def reject_invite(c: types.CallbackQuery):
    room_id = c.data.split("_", 1)[1]
    inv = pending_invites.get(room_id)
    if not inv:
        return await c.answer("⚠️ انتهت صلاحية الدعوة.", show_alert=True)
    if c.from_user.id not in inv['invited']:
        return await c.answer("⚠️ هذه الدعوة ليست لك.", show_alert=True)
    if c.from_user.id in inv['accepted'] or c.from_user.id in inv['rejected']:
        return await c.answer("⚠️ سبق ورديت على الدعوة.", show_alert=True)
    inv['rejected'].add(c.from_user.id)
    p_name = inv['invited'].get(c.from_user.id, "لاعب")
    await c.message.edit_text("❌ رفضت الدعوة.")
    try:
        await c.bot.send_message(inv['creator'], f"❌ {p_name} رفض الدعوة.")
    except Exception:
        pass

# 1. دالة عرض القائمة الاجتماعية (عند الضغط على زر الأصدقاء)
@router.callback_query(F.data == "social_menu")
async def show_social_menu(c: types.CallbackQuery):
    uid = c.from_user.id
    
    # نجلب الأعداد من قاعدة البيانات
    followers = db_query("SELECT COUNT(*) as count FROM follows WHERE following_id = %s", (uid,))[0]['count']
    following = db_query("SELECT COUNT(*) as count FROM follows WHERE follower_id = %s", (uid,))[0]['count']
    
    text = (f"👥 **القائمة الاجتماعية**\n\n"
    f"📈 يتابعونني: {followers}\n"
    f"📉 أتابعهم: {following}\n\n"
    "ابحث عن لاعب وتابعه لتصلك إشعارات عندما يلعب!")
    
    kb = [
    [InlineKeyboardButton(text="🔍 البحث عن لاعب", callback_data="search_user")],
    [InlineKeyboardButton(text=t(uid, "btn_followers_list"), callback_data="list_followers"),
    InlineKeyboardButton(text=t(uid, "btn_following_list"), callback_data="list_following")],
    [InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="home")]
    ]
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 2. دالة بدء البحث (تغير حالة البوت وتطلب اليوزر نيم)
@router.callback_query(F.data == "search_user")
async def start_search_user(c: types.CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    await c.message.answer("✍️ أرسل الآن اسم المستخدم (اليوزر نيم) للشخص الذي تبحث عنه:")
    await state.set_state(RoomStates.search_user) # هنا البوت ينتظر نص من المستخدم

# 3. معالج البحث (هذه الدالة اللي سألت عنها، توضع هنا)
@router.message(RoomStates.search_user)
async def process_user_search(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    target_username = message.text.strip().lower().replace("@", "") # تنظيف النص من @
    
    target = db_query("SELECT * FROM users WHERE username_key = %s", (target_username,))
    
    if not target:
        return await message.answer("❌ لا يوجد لاعب بهذا اليوزر. تأكد من الحروف وأرسله مرة ثانية:")

    t_user = target[0]
    t_uid = t_user['user_id']
    
    # فحص إذا كنت تتابعه حالياً
    is_following = db_query("SELECT 1 FROM follows WHERE follower_id = %s AND following_id = %s", (uid, t_uid))
    
    # بناء حالة الأونلاين
    from datetime import datetime, timedelta
    status = t(uid, "status_online") if (datetime.now() - t_user['last_seen'] < timedelta(minutes=5)) else t(uid, "status_offline", time=t_user['last_seen'].strftime("%H:%M"))

    text = t(uid, "profile_title", name=t_user['player_name'], username=t_user['username_key'], points=t_user['online_points'], status=status)
    
    kb = []
    # زر المتابعة أو الإلغاء
    follow_btn_text = t(uid, "btn_unfollow") if is_following else t(uid, "btn_follow")
    follow_callback = f"unfollow_{t_uid}" if is_following else f"follow_{t_uid}"
    
    kb.append([InlineKeyboardButton(text=follow_btn_text, callback_data=follow_callback)])
    kb.append([InlineKeyboardButton(text=t(uid, "btn_invite_play"), callback_data=f"invite_{t_uid}")])
    if (uid, t_uid) in invite_mutes:
        kb.append([InlineKeyboardButton(text="✏️ تعديل الكتم", callback_data=f"mute_inv_{t_uid}")])
    kb.append([InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="social_menu")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear() # إنهاء حالة البحث

# --- تنفيذ المتابعة ---
@router.callback_query(F.data.startswith("follow_"))
async def process_follow(c: types.CallbackQuery):
    uid = c.from_user.id
    target_id = int(c.data.split("_")[1])
    
    if uid == target_id:
        return await c.answer("🧐 لا يمكنك متابعة نفسك!", show_alert=True)

    # إضافة المتابعة للقاعدة
    try:
        db_query("INSERT INTO follows (follower_id, following_id) VALUES (%s, %s)", (uid, target_id), commit=True)
        await c.answer("✅ تمت المتابعة بنجاح!")
    except Exception:
        await c.answer("⚠️ أنت تتابع هذا اللاعب بالفعل.")

    # تحديث واجهة البروفايل فوراً (إظهار زر إلغاء المتابعة بدلاً من متابعة)
    await process_user_search_by_id(c, target_id)

# --- تنفيذ إلغاء المتابعة ---
@router.callback_query(F.data.startswith("unfollow_"))
async def process_unfollow(c: types.CallbackQuery):
    uid = c.from_user.id
    target_id = int(c.data.split("_")[1])
    
    db_query("SELECT 1 FROM follows WHERE follower_id = %s AND following_id = %s", (uid, target_id))
    db_query("DELETE FROM follows WHERE follower_id = %s AND following_id = %s", (uid, target_id), commit=True)
    
    await c.answer("❌ تم إلغاء المتابعة.")
    # تحديث واجهة البروفايل فوراً
    await process_user_search_by_id(c, target_id)


# --- دالة جديدة: تشغيل حاسبة الأونو (إصلاح الزر) ---
@router.callback_query(F.data == "calc_start")
async def start_calculator(c: types.CallbackQuery):
    uid = c.from_user.id
    text = "🧮 **حاسبة نقاط أونو**\n\nكم عدد اللاعبين؟"
    
    # توزيع الأزرار بشكل مرتب لـ 10 لاعبين
    kb = [
    [InlineKeyboardButton(text="2", callback_data="calc_players_2"), InlineKeyboardButton(text="3", callback_data="calc_players_3"), InlineKeyboardButton(text="4", callback_data="calc_players_4")],
    [InlineKeyboardButton(text="5", callback_data="calc_players_5"), InlineKeyboardButton(text="6", callback_data="calc_players_6"), InlineKeyboardButton(text="7", callback_data="calc_players_7")],
    [InlineKeyboardButton(text="8", callback_data="calc_players_8"), InlineKeyboardButton(text="9", callback_data="calc_players_9"), InlineKeyboardButton(text="10", callback_data="calc_players_10")],
    [InlineKeyboardButton(text="🔙 رجوع", callback_data="home")]
    ]
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("calc_players_"))
async def calc_choose_players(c: types.CallbackQuery, state: FSMContext):
    n = int(c.data.split("_")[-1])
    await state.update_data(calc_players=n)
    kb = [[InlineKeyboardButton(text="🔙 رجوع", callback_data="calc_start")],
    [InlineKeyboardButton(text="🏠 الرئيسية", callback_data="home")]]
    await c.message.edit_text(f"✅ تم اختيار عدد اللاعبين: {n}\n\n(هنا نكمل خطوات الحاسبة بعدين)", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


# 2. تعديل قائمة المتابعين (حذف None وإصلاح الدخول للاعب)
@router.callback_query(F.data == "list_following")
async def show_following_list(c: types.CallbackQuery):
    uid = c.from_user.id
    following = db_query("""
    SELECT u.user_id, u.player_name, u.last_seen 
    FROM follows f 
    JOIN users u ON f.following_id = u.user_id 
    WHERE f.follower_id = %s
    """, (uid,))

    if not following:
        return await c.answer("📉 أنت لا تتابع أحداً حالياً.", show_alert=True)

    text = "📉 **أتابعهم:**\n(اضغط على الاسم لفتح البروفايل)"
    kb = []
    from datetime import datetime, timedelta
    
    for user in following:
        last_seen = user['last_seen'] if user['last_seen'] else datetime.min
        is_online = (datetime.now() - last_seen < timedelta(minutes=5))
        status_icon = "🟢" if is_online else "⚪"
        display_name = user['player_name'] if user['player_name'] else "لاعب"
        kb.append([InlineKeyboardButton(
            text=f"{status_icon} {display_name}",
            callback_data=f"view_profile_{user['user_id']}"
        )])

    kb.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="social_menu")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- دالة جديدة: عرض قائمة "المتابعون" ---
@router.callback_query(F.data == "list_followers")
async def show_followers_list(c: types.CallbackQuery):
    uid = c.from_user.id
    # جلب الأشخاص الذين يتابعون المستخدم
    followers = db_query("""
    SELECT u.user_id, u.player_name, u.username_key 
    FROM follows f 
    JOIN users u ON f.follower_id = u.user_id 
    WHERE f.following_id = %s
    """, (uid,))

    if not followers:
        return await c.answer("📈 لا يوجد متابعون لحسابك حالياً.", show_alert=True)

    text = "📈 **يتابعونني:**\n\n"
    kb = []
    for user in followers:
        kb.append([InlineKeyboardButton(
            text=f"👤 {user['player_name']} (@{user['username_key']})",
            callback_data=f"view_profile_{user['user_id']}"
        )])

    kb.append([InlineKeyboardButton(text=t(uid, "btn_back"), callback_data="social_menu")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# --- دالة تفعيل/تعطيل تنبيهات بدء اللعب (🔔) ---
@router.callback_query(F.data.startswith("game_notify_"))
async def toggle_game_notify(c: types.CallbackQuery):
    target_id = int(c.data.split("_")[2])
    uid = c.from_user.id
    
    # فحص الحالة الحالية من جدول المتابعة (سنستخدم عمود notify_games)
    # ملاحظة: إذا لم تكن قد أضفت العمود بعد، سأعطيك أمر SQL لاحقاً
    current = db_query("SELECT notify_games FROM follows WHERE follower_id = %s AND following_id = %s", (uid, target_id))
    
    if not current:
        return await c.answer("⚠️ يجب أن تتابع اللاعب أولاً لتفعيل التنبيهات!", show_alert=True)
    
    new_status = 0 if current[0]['notify_games'] else 1
    db_query("UPDATE follows SET notify_games = %s WHERE follower_id = %s AND following_id = %s", (new_status, uid, target_id), commit=True)
    
    await c.answer("✅ تم تحديث إعدادات التنبيه" if new_status else "❌ تم إيقاف التنبيه")
    # تحديث واجهة البروفايل لإظهار العلامة الجديدة
    await process_user_search_by_id(c, target_id)
    
    # هنا التحكم يكون بخصوصية اللاعب نفسه (هل يسمح للآخرين بدعوته)
    if uid != target_id:
        return await c.answer("🧐 يمكنك تعديل إعداداتك فقط من 'حسابي'.", show_alert=True)
    current = db_query("SELECT allow_invites FROM users WHERE user_id = %s", (uid,))
    new_status = 0 if current[0]['allow_invites'] else 1
    db_query("UPDATE users SET allow_invites = %s WHERE user_id = %s", (new_status, uid), commit=True)
    
    await c.answer("✅ تم السماح بالطلبات" if new_status else "❌ تم قفل الطلبات")
    await process_user_search_by_id(c, target_id)

# وضعه في نهاية ملف room_multi.py
async def notify_followers_game_started(player_id, player_name, bot):
    # جلب المتابعين الذين فعلوا التنبيه
    followers = db_query("SELECT follower_id FROM follows WHERE following_id = %s AND notify_games = 1", (player_id,))
    
    for f in followers:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👁 مشاهدة اللعبة", callback_data=f"spectate_{player_id}")]
            ])
            await bot.send_message(
                f['follower_id'],
                f"🚀 صديقك {player_name} بدأ لعبة أونو الآن! هل تريد المشاهدة؟",
                reply_markup=kb
            )
        except Exception:
            continue


@router.callback_query(F.data == "rules")
async def show_rules(c: types.CallbackQuery):
    uid = c.from_user.id
    rules_text = t(uid, "rules_text")
    kb = [[InlineKeyboardButton(text=t(uid, "btn_back_short"), callback_data="home")]]
    
    try:
        await c.message.edit_text(
            text=rules_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="Markdown"
        )
    except Exception:
        pass
    
    await c.answer()

@router.callback_query(F.data == "leaderboard")
@router.callback_query(F.data == "leaderboard_global")
@router.callback_query(F.data == "leaderboard_friends")
async def show_leaderboard(c: types.CallbackQuery):
    uid = c.from_user.id
    friends_only = c.data == "leaderboard_friends"
    if friends_only:
        friend_ids = {uid}
        rows = db_query(
            "SELECT following_id AS id FROM follows WHERE follower_id = %s UNION SELECT follower_id AS id FROM follows WHERE following_id = %s",
            (uid, uid)
        )
        if rows:
            for r in rows:
                friend_ids.add(r.get('id'))
        if len(friend_ids) < 2:
            await c.answer(t(uid, "leaderboard_empty"), show_alert=True)
            return
        placeholders = ",".join(["%s"] * len(friend_ids))
        rows = db_query(
            f"SELECT user_id, player_name, COALESCE(online_points, 0) as online_points FROM users WHERE user_id IN ({placeholders}) AND (is_registered = TRUE OR online_points > 0) ORDER BY online_points DESC LIMIT 30",
            tuple(friend_ids)
        )
    else:
        rows = db_query(
            "SELECT user_id, player_name, COALESCE(online_points, 0) as online_points FROM users WHERE (is_registered = TRUE OR online_points > 0) ORDER BY online_points DESC LIMIT 50"
        )
    if not rows:
        text = t(uid, "leaderboard_title") + "\n\n" + t(uid, "leaderboard_empty")
    else:
        lines = []
        for i, r in enumerate(rows, 1):
            name = (r.get("player_name") or "—")[:20]
            pts = r.get("online_points") or 0
            lines.append(t(uid, "leaderboard_row", rank=i, name=name, points=pts))
        text = t(uid, "leaderboard_title") + "\n\n" + "\n".join(lines)
    kb = [
        [InlineKeyboardButton(text=t(uid, "leaderboard_friends"), callback_data="leaderboard_friends"),
         InlineKeyboardButton(text=t(uid, "leaderboard_global"), callback_data="leaderboard_global")],
        [InlineKeyboardButton(text=t(uid, "btn_home"), callback_data="home")]
    ]
    try:
        await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except Exception:
        await c.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await c.answer()

# --- دالة إرسال دعوة اللعب من بروفايل اللاعب ---
def _is_invite_muted(muter_id, muted_id):
    import datetime
    key = (muter_id, muted_id)
    if key not in invite_mutes:
        return None
    until = invite_mutes[key]
    if until is None:
        return "للأبد"
    if datetime.datetime.now() > until:
        del invite_mutes[key]
        return None
    delta = until - datetime.datetime.now()
    mins = int(delta.total_seconds() // 60)
    if mins >= 60:
        return f"{mins // 60} ساعة"
    return f"{mins} دقيقة"

@router.callback_query(F.data.startswith("invite_"))
async def send_game_invite(c: types.CallbackQuery):
    import datetime
    sender_id = c.from_user.id
    try:
        target_id = int(c.data.split("_")[1])
    except (IndexError, ValueError):
        await c.answer("⚠️ خطأ في البيانات.", show_alert=True)
        return

    if sender_id == target_id:
        await c.answer("🚫 لا يمكنك دعوة نفسك!", show_alert=True)
        return

    sender_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (sender_id,))
    sender_name = sender_data[0]["player_name"] if sender_data else c.from_user.full_name or "لاعب"

    muted_remaining = _is_invite_muted(target_id, sender_id)
    if muted_remaining:
        await c.answer(f"⛔ أنت مكتوم من إرسال دعوات لهذا اللاعب خلال: {muted_remaining}", show_alert=True)
        return

    invite_from = _get_invite_from(target_id)
    if invite_from == "following":
        row = db_query("SELECT 1 FROM follows WHERE follower_id = %s AND following_id = %s", (target_id, sender_id))
        if not row:
            await c.answer("⛔ هذا اللاعب يستقبل الدعوات فقط من الذين يتابعهم. أنت لست من قائمة متابعاته.", show_alert=True)
            return
    elif invite_from == "followers":
        row = db_query("SELECT 1 FROM follows WHERE follower_id = %s AND following_id = %s", (sender_id, target_id))
        if not row:
            await c.answer("⛔ هذا اللاعب يستقبل الدعوات فقط من الذين يتابعونه. تابعَه أولاً ثم جرّب الدعوة.", show_alert=True)
            return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ اقبل", callback_data=f"accept_inv_{sender_id}"),
            InlineKeyboardButton(text="❌ ارفض", callback_data=f"reject_inv_{sender_id}"),
            InlineKeyboardButton(text="🔇 اكتم", callback_data=f"mute_inv_{sender_id}")
        ]
    ])
    try:
        await c.bot.send_message(
            target_id,
            f"📩 **{sender_name}** يطلبك للعب معه",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await c.answer("✅ تم إرسال طلب اللعب بنجاح!", show_alert=True)
    except Exception:
        await c.answer("⚠️ تعذر إرسال الطلب (ربما قام اللاعب بحظر البوت).", show_alert=True)


@router.callback_query(F.data.startswith("mute_inv_confirm_"))
async def mute_invite_confirm(c: types.CallbackQuery):
    import datetime
    parts = c.data.split("_")
    if len(parts) < 5:
        await c.answer("⚠️ خطأ.", show_alert=True)
        return
    sender_id = int(parts[3])
    minutes = int(parts[4])
    muter_id = c.from_user.id
    if minutes == 0:
        invite_mutes[(muter_id, sender_id)] = None
        msg = "✅ تم كتم هذا اللاعب للأبد من إرسال دعوات لك."
    else:
        invite_mutes[(muter_id, sender_id)] = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
        msg = f"✅ تم كتم هذا اللاعب لمدة {minutes} دقيقة."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]])
    try:
        await c.message.edit_text(msg, reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("mute_inv_unmute_"))
async def mute_invite_unmute(c: types.CallbackQuery):
    """إلغاء الكتم عن اللاعب"""
    try:
        sender_id = int(c.data.split("_")[3])
    except (IndexError, ValueError):
        await c.answer("⚠️ خطأ.", show_alert=True)
        return
    muter_id = c.from_user.id
    key = (muter_id, sender_id)
    if key in invite_mutes:
        del invite_mutes[key]
    await c.answer("✅ تم إلغاء الكتم. يمكن لهذا اللاعب إرسال دعوات لك مجدداً.", show_alert=True)
    await process_user_search_by_id(c, sender_id)


@router.callback_query(F.data.startswith("mute_inv_"))
async def mute_invite_options(c: types.CallbackQuery):
    """عرض خيارات الكتم (لا يطابق confirm أو unmute)"""
    if c.data.startswith("mute_inv_confirm_") or c.data.startswith("mute_inv_unmute_"):
        await c.answer()
        return
    parts = c.data.split("_")
    if len(parts) < 3:
        await c.answer("⚠️ خطأ.", show_alert=True)
        return
    sender_id = int(parts[2])
    kb = [
        [InlineKeyboardButton(text="كتم ساعة", callback_data=f"mute_inv_confirm_{sender_id}_60")],
        [InlineKeyboardButton(text="كتم 5 ساعات", callback_data=f"mute_inv_confirm_{sender_id}_300")],
        [InlineKeyboardButton(text="كتم 10 ساعات", callback_data=f"mute_inv_confirm_{sender_id}_600")],
        [InlineKeyboardButton(text="كتم 24 ساعة", callback_data=f"mute_inv_confirm_{sender_id}_1440")],
        [InlineKeyboardButton(text="كتم للأبد", callback_data=f"mute_inv_confirm_{sender_id}_0")],
        [InlineKeyboardButton(text="❌ إلغاء الكتم", callback_data=f"mute_inv_unmute_{sender_id}")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data=f"view_profile_{sender_id}")]
    ]
    await c.message.edit_text("🔇 اختر مدة الكتم أو ألغِ الكتم:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()

# --- 1. عرض خيارات الوقت (تعديل الرسالة الحالية) ---
@router.callback_query(F.data.startswith("allow_invites_"))
async def show_invite_timer_options(c: types.CallbackQuery):
    target_id = int(c.data.split("_")[2])
    uid = c.from_user.id
    
    if uid != target_id:
        return await c.answer("🧐 يمكنك تعديل إعداداتك فقط من 'حسابي'.", show_alert=True)
    text = "🕒 **مدة استقبال طلبات اللعب**\n\nاختر المدة التي تريد فيها فتح استقبال الطلبات:"
    
    kb = [
    [InlineKeyboardButton(text="⏳ لمدة دقيقة واحدة (للتجربة)", callback_data=f"set_inv_1m_{uid}")],
    [InlineKeyboardButton(text="⌛ لمدة ساعة واحدة", callback_data=f"set_inv_1h_{uid}")],
    [InlineKeyboardButton(text="✅ دائماً", callback_data=f"set_inv_always_{uid}")],
    [InlineKeyboardButton(text="❌ إغلاق الآن", callback_data=f"set_inv_off_{uid}")],
    [InlineKeyboardButton(text="🔙 رجوع", callback_data=f"view_profile_{uid}")]
    ]
    
    # تعديل نص الرسالة الحالية (نظافة تامة)
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- 2. معالجة الحفظ في القاعدة مع المؤقت الجديد ---
@router.callback_query(F.data.startswith("set_inv_"))
async def process_invites_timer(c: types.CallbackQuery):
    data = c.data.split("_")
    action = data[2] # 1m, 1h, always, off
    uid = int(data[3])
    
    expiry_time = None
    status_val = 1
    
    if action == "off":
        status_val = 0
    elif action == "1m":
        expiry_time = datetime.datetime.now() + datetime.timedelta(minutes=1)
    elif action == "1h":
        expiry_time = datetime.datetime.now() + datetime.timedelta(hours=1)
    elif action == "always":
        expiry_time = None
        status_val = 1
    
    # تحديث قاعدة البيانات (تأكد من إضافة عمود invite_expiry)
    db_query("UPDATE users SET allow_invites = %s, invite_expiry = %s WHERE user_id = %s", 
    (status_val, expiry_time, uid), commit=True)
    
    await c.answer("✅ تم التحديث")
    
    # العودة لبروفايل اللاعب باستخدام تعديل الرسالة
    await process_user_search_by_id(c, uid)

# --- قبول الدعوة: إنشاء غرفة ثنائية وبدء اللعب فوراً (ظهور الأوراق) ---
@router.callback_query(F.data.startswith("accept_inv_"))
async def accept_game_invite(c: types.CallbackQuery):
    sender_id = int(c.data.split("_")[2])
    target_id = c.from_user.id

    sender_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (sender_id,))
    target_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (target_id,))
    s_name = sender_data[0]['player_name'] if sender_data else "لاعب"
    t_name = target_data[0]['player_name'] if target_data else "لاعب"

    code = generate_room_code()
    db_query(
        "INSERT INTO rooms (room_id, creator_id, max_players, score_limit, status) VALUES (%s, %s, 2, 0, 'playing')",
        (code, sender_id), commit=True
    )
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)", (code, sender_id, s_name), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name, is_ready) VALUES (%s, %s, %s, TRUE)", (code, target_id, t_name), commit=True)

    try:
        from handlers.room_2p import start_new_round
        await start_new_round(code, c.bot, start_turn_idx=0)
        await c.answer("✅ تم قبول الدعوة! جاري بدء اللعبة...", show_alert=True)
    except Exception as e:
        await c.answer("⚠️ حدث خطأ في بدء اللعبة.", show_alert=True)
        try:
            await c.bot.send_message(sender_id, f"✅ وافق **{t_name}** على دعوتك! لكن حدث خطأ في بدء الجولة.")
            await c.bot.send_message(target_id, f"حدث خطأ في بدء اللعبة. جرّب إنشاء غرفة من القائمة.")
        except Exception:
            pass

# --- 2. دالة رفض الطلب (تنفذ عند ضغط الصديق على ❌ رفض) ---
@router.callback_query(F.data.startswith("reject_inv_"))
async def reject_game_invite(c: types.CallbackQuery):
    sender_id = int(c.data.split("_")[2])
    target_name = c.from_user.full_name
    
    try:
        await c.bot.send_message(sender_id, f"❌ اعتذر **{target_name}** عن اللعب حالياً.")
    except Exception:
        pass
    try:
        await c.message.delete()
        await c.answer("تم رفض الطلب بنجاح.")
    except Exception:
        await c.message.edit_text("❌ تم رفض الطلب.")


@router.callback_query(F.data == "check_channel_sub")
async def on_check_channel_sub(c: types.CallbackQuery, state: FSMContext):
    if not CHANNEL_ID:
        await c.answer()
        return
    if await is_channel_member(c.bot, c.from_user.id):
        await state.clear()
        user = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
        name = user[0]['player_name'] if user else c.from_user.full_name
        await show_main_menu(c.message, name, user_id=c.from_user.id, state=state)
        await c.answer()
    else:
        await c.answer("⛔ ما زلت غير مشترك. اشترك ثم اضغط «تحقق».", show_alert=True)

@router.callback_query(F.data == "home")
async def home_callback(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    name = user[0]['player_name'] if user else c.from_user.full_name
    
    # تشغيل المنيو الرئيسي عند الضغط على عودة
    await show_main_menu(c.message, name, user_id=c.from_user.id, state=state)
    await c.answer()

