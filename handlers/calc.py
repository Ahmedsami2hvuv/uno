from aiogram import Router, F, types
from database import db_query

router = Router()

@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery):
    # كود الحاسبة والاتجاهات والصور...
    await callback.message.edit_text("🧮 نظام الحاسبة اليدوية جاهز.")

