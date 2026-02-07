from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
import random
import string

router = Router()

# دالة لتوليد كود غرفة فريد
def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

# --- حالات الغرف الخاصة ---
class RoomStates(StatesGroup):
    wait_for_code = State() # حالة انتظار كود الغرفة للانضمام

# --- قسم مستخرج الأكواد ---
@router.message(F.photo)
async def get_photo_id(message: types.Message):
    file_id = message.photo[-1].file_id
    await message.reply(f"✅ كود الصورة (File ID):\n\n`{file_id}`", parse_mode="Markdown")

@router.message(F.document)
async def get_doc_id(message: types.Message):
    if message.document and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
        await message.reply(f"✅ كود الصورة (مستند):\n\n`{file_id}`", parse_mode="Markdown")

# --- نظام التسجيل والترحيب ---
class RegisterStates(StatesGroup):
    wait_name = State()
    wait_password = State()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    
    if not user or not user[0].get('is_registered'):
        if not user:
            db_query("INSERT INTO users (user_id, username, is_registered) VALUES (%s, %s, FALSE)", 
                     (message.from_user.id, message.from_user.username), commit=True)
        await message.answer("👋 أهلاً بك! لإنشاء حسابك، أرسل اسم اللاعب الذي تريده:")
        await state.set_state(RegisterStates.wait_name)
    else:
        await show_main_menu(message, user[0]['player_name'])

# (دوال التسجيل تبقى كما هي لتجنب المشاكل)
@router.message(RegisterStates.wait_name)
async def get_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    existing = db_query("SELECT user_id FROM users WHERE player_name = %s", (name,))
    if existing: return await message.answer("❌ هذا الاسم محجوز! اختر اسماً آخر:")
    await state.update_data(p_name=name); await message.answer(f"أهلاً {name}! الآن اختر رمزاً سرياً:"); await state.set_state(RegisterStates.wait_password)

@router.message(RegisterStates.wait_password)
async def get_pass(message: types.Message, state: FSMContext):
    password = message.text.strip(); data = await state.get_data()
    db_query("UPDATE users SET player_name = %s, password = %s, is_registered = TRUE WHERE user_id = %s", (data['p_name'], password, message.from_user.id), commit=True)
    await message.answer("✅ تم تفعيل حسابك!"); await show_main_menu(message, data['p_name'])

# --- القائمة الرئيسية ---
async def show_main_menu(message, name):
    kb = [[InlineKeyboardButton(text="🎲 لعب عشوائي", callback_data="mode_random"), InlineKeyboardButton(text="🏠 غرفة لعب", callback_data="private_room_menu")],
          [InlineKeyboardButton(text="🧮 حاسبة اونو", callback_data="mode_calc")],
          [InlineKeyboardButton(text="🏆 المتصدرين", callback_data="leaderboard"), InlineKeyboardButton(text="👤 حسابي", callback_data="my_profile")]]
    text = f"🃏 مرحباً بك {name}\nاختر ما تريد فعله:"
    if hasattr(message, "answer"): await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- معالج خيارات الغرفة ---
@router.callback_query(F.data == "private_room_menu")
async def private_room_main(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = [[InlineKeyboardButton(text="➕ إنشاء غرفة جديدة", callback_data="room_create")],
          [InlineKeyboardButton(text="🚪 انضمام لغرفة", callback_data="room_join_input")],
          [InlineKeyboardButton(text="🏠 الرجوع للقائمة", callback_data="home")]]
    await c.message.edit_text("🎮 **غرف اللعب الخاصة**\n\nأنشئ غرفة ودز الكود لربعك أو ادخل كود غرفة واصلك.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- 🚀 نظام الانضمام (الذي كان مفقوداً) ---
@router.callback_query(F.data == "room_join_input")
async def join_room_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("📥 **أرسل كود الغرفة المكون من 5 رموز:**\n(مثال: `ABC12`)")
    await state.set_state(RoomStates.wait_for_code)

@router.message(RoomStates.wait_for_code)
async def process_room_join(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    
    if not room:
        return await message.answer("❌ الكود غير صحيح أو الغرفة لم تعد موجودة. حاول مرة أخرى:")
    
    # التحقق إذا كانت الغرفة ممتلئة (مثال مبدئي)
    players = db_query("SELECT COUNT(*) as count FROM room_players WHERE room_id = %s", (code,))
    if players[0]['count'] >= room[0]['max_players']:
        await state.clear()
        return await message.answer("🚫 الغرفة ممتلئة بالفعل!")

    # إضافة اللاعب للغرفة
    user_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    p_name = user_data[0]['player_name']
    
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (code, message.from_user.id, p_name), commit=True)
    
    await state.clear()
    await message.answer(f"✅ تم الانضمام للغرفة `{code}` بنجاح!\nننتظر اكتمال العدد لبدء اللعب...")

# --- مراحل إنشاء الغرفة ---
@router.callback_query(F.data == "room_create")
async def room_create_start(c: types.CallbackQuery):
    kb = []; row = []
    for i in range(2, 11):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"setp_{i}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    await c.message.edit_text("👥 **حدد عدد اللاعبين (2 - 10):**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("setp_"))
async def set_room_players(c: types.CallbackQuery):
    num = c.data.split("_")[1]
    scores = [100, 150, 200, 250, 300, 350, 400, 450, 500]
    kb = []; row = []
    for s in scores:
        row.append(InlineKeyboardButton(text=str(s), callback_data=f"sets_{num}_{s}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    await c.message.edit_text(f"🎯 **تم اختيار {num} لاعبين.**\nحدد سقف النقاط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sets_"))
async def finalize_room_creation(c: types.CallbackQuery):
    _, p_count, s_limit = c.data.split("_")
    room_code = generate_room_code()
    user_id = c.from_user.id
    user_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (user_id,))
    p_name = user_data[0]['player_name'] if user_data else c.from_user.full_name

    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit) VALUES (%s, %s, %s, %s)", (room_code, user_id, int(p_count), int(s_limit)), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", (room_code, user_id, p_name), commit=True)
    
    # إرسال رسالة الإعداد
    await c.message.edit_text(f"✅ **تم إنشاء الغرفة!**\n\n👥 العدد: {p_count} | 🎯 السقف: {s_limit}\n\nننتظر دخول ربعك (1/{p_count})")
    
    # 🚨 إرسال الكود برسالة منفصلة للنسخ السهل
    await c.message.answer(f"`{room_code}`")
    await c.message.answer("☝️ **اضغط على الكود أعلاه لنسخه** وارسله لأصدقائك.")

@router.callback_query(F.data == "home")
async def go_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (callback.from_user.id,))
    await show_main_menu(callback.message, user[0]['player_name'])
