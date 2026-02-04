from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database import db_query
from config import ADMIN_ID

router = Router()

class AdminStates(StatesGroup):
    broadcast = State()

@router.callback_query(F.data == "admin")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("❌ أنت لست الأدمن!", show_alert=True)
    
    user_count = db_query("SELECT COUNT(*) FROM users")[0]['count']
    kb = [
        [InlineKeyboardButton(text="📢 إذاعة رسالة للكل", callback_data="bc_all")],
        [InlineKeyboardButton(text="🔙 العودة", callback_data="home")]
    ]
    await callback.message.edit_text(f"⚡ لوحة تحكم الأدمن\n\n👥 عدد المستخدمين: {user_count}", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# كود الإذاعة يكمل هنا...

