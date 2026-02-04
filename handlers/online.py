from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from database import db_query
import random

router = Router()

class OnlineStates(StatesGroup):
    waiting = State()
    playing = State()

# هنا نضع كود "اللعب العشوائي" وتوزيع الأوراق اللي جربته قبل قليل
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    # كود البحث عن لاعب وتوزيع الورق...
    await callback.message.edit_text("🔎 جاري البحث عن لاعب في الغرفة...")
    # (تكملة الكود الخاص بالغرفة)
