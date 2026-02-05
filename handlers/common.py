from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query

router = Router()

class RegisterStates(StatesGroup):
    wait_name = State()
    wait_password = State()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    # فحص هل المستخدم مسجل فعلاً؟
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    
    if not user or not user[0].get('is_registered'):
        # إذا لم يكن له سطر في الجدول أصلاً، ننشئه
        if not user:
            db_query("INSERT INTO users (user_id, username, is_registered) VALUES (%s, %s, FALSE)", 
                     (message.from_user.id, message.from_user.username), commit=True, fetch=False)
        
        await message.answer("👋 أهلاً بك! لكي تبدأ، أرسل اسم اللاعب الذي تريده:")
        await state.set_state(RegisterStates.wait_name)
    else:
        # إذا مسجل، نفتح القائمة فوراً
        await show_main_menu(message, user[0]['player_name'])

@router.message(RegisterStates.wait_name)
async def get_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    # منع تكرار الأسماء
    existing = db_query("SELECT user_id FROM users WHERE player_name = %s", (name,))
    if existing:
        return await message.answer("❌ هذا الاسم محجوز للاعب آخر! اختر اسماً غيره:")
    
    await state.update_data(p_name=name)
    await message.answer(f"جميل يا {name}! الآن أرسل رمزاً سرياً لحماية حسابك:")
    await state.set_state(RegisterStates.wait_password)

@router.message(RegisterStates.wait_password)
async def get_pass(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    # تحديث البيانات وتفعيل الحساب
    db_query("UPDATE users SET player_name = %s, password = %s, is_registered = TRUE WHERE user_id = %s",
             (data['p_name'], password, message.from_user.id), commit=True, fetch=False)
    
    await message.answer("✅ تم إنشاء حسابك بنجاح!")
    await show_main_menu(message, data['p_name'])

async def show_main_menu(message, name):
    # الأزرار بأسماء (callback_data) دقيقة جداً لتطابق الملفات الأخرى
    kb = [
        [InlineKeyboardButton(text="🎲 لعب عشوائي", callback_data="mode_random"),
         InlineKeyboardButton(text="🏠 إنشاء غرفة", callback_data="create_room")],
        [InlineKeyboardButton(text="🔑 دخول غرفة", callback_data="join_room")],
        [InlineKeyboardButton(text="🧮 حاسبة اونو", callback_data="mode_calc")],
        [InlineKeyboardButton(text="🏆 المتصدرين", callback_data="leaderboard"),
         InlineKeyboardButton(text="👤 حسابي", callback_data="my_profile")]
    ]
    text = f"🃏 مرحباً بك {name}\nاختر نظام اللعب:"
    if hasattr(message, "answer"):
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
