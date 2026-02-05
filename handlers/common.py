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
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    
    # إذا لم يكن مسجلاً أو لم يكمل بياناته
    if not user or not user[0]['is_registered']:
        if not user: # تسجيل أولي في الداتا بيس
            db_query("INSERT INTO users (user_id, username) VALUES (%s, %s)", 
                     (message.from_user.id, message.from_user.username), commit=True, fetch=False)
        
        await message.answer("👋 أهلاً بك في بوت أونو! لكي تبدأ اللعب، نحتاج لإنشاء حساب لك.\n\n👤 أرسل الآن اسم اللاعب الذي تود الظهور به:")
        await state.set_state(RegisterStates.wait_name)
    else:
        # إذا كان مسجلاً، تظهر القائمة الرئيسية مباشرة
        await show_main_menu(message, user[0]['player_name'])

@router.message(RegisterStates.wait_name)
async def get_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 3 or len(name) > 15:
        return await message.answer("⚠️ الاسم يجب أن يكون بين 3 إلى 15 حرفاً. جرب اسماً آخر:")
    
    await state.update_data(p_name=name)
    await message.answer(f"جميل يا {name}! الآن أرسل **رمزاً سرياً** لحماية حسابك (أرقام أو حروف):")
    await state.set_state(RegisterStates.wait_password)

@router.message(RegisterStates.wait_password)
async def get_pass(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    
    db_query("UPDATE users SET player_name = %s, password = %s, is_registered = TRUE WHERE user_id = %s",
             (data['p_name'], password, message.from_user.id), commit=True, fetch=False)
    
    await message.answer("🎉 مبروك! تم إنشاء حسابك بنجاح. يمكنك الآن اللعب وجمع النقاط.")
    await state.clear()
    await show_main_menu(message, data['p_name'])

async def show_main_menu(message, name):
    kb = [
        [InlineKeyboardButton(text="🎲 لعب عشوائي (أونلاين)", callback_data="mode_random")],
        [InlineKeyboardButton(text="🧮 حاسبة أونو (يدوية)", callback_data="mode_calc")],
        [InlineKeyboardButton(text="🏆 قائمة المتصدرين", callback_data="leaderboard")],
        [InlineKeyboardButton(text="👤 حسابي", callback_data="my_profile")]
    ]
    await message.answer(f"🃏 مرحباً بك {name}\nاختر ما تود فعله:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
