from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query

router = Router()

# 1. ميزة مستخرج الأكواد (خليتها بالبداية وبدون قيود "state" حتى تشتغل فوراً)
@router.message(F.photo)
async def get_photo_id(message: types.Message):
    file_id = message.photo[-1].file_id
    await message.reply(f"✅ كود الصورة (File ID):\n\n`{file_id}`")

@router.message(F.document)
async def get_doc_id(message: types.Message):
    if message.document and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
        await message.reply(f"✅ كود الصورة (مستند):\n\n`{file_id}`")

# --- باقي الكود القديم (التسجيل والترحيب) ---

class RegisterStates(StatesGroup):
    wait_name = State()
    wait_password = State()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear() # تصفير أي حالة قديمة
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    
    if not user or not user[0].get('is_registered'):
        if not user:
            db_query("INSERT INTO users (user_id, username, is_registered) VALUES (%s, %s, FALSE)", 
                     (message.from_user.id, message.from_user.username), commit=True)
        await message.answer("👋 أهلاً بك! لكي تبدأ، أرسل اسم اللاعب الذي تريده:")
        await state.set_state(RegisterStates.wait_name)
    else:
        await show_main_menu(message, user[0]['player_name'])

# ... (بقية الدوال: get_name, get_pass, show_main_menu) تبقى كما هي
