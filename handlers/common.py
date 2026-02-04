from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [
        [InlineKeyboardButton(text="🧮 حاسبة اونو", callback_data="mode_calc")],
        [InlineKeyboardButton(text="🎲 لعب عشوائي", callback_data="mode_random")],
        [InlineKeyboardButton(text="🏠 غرفة لعب", callback_data="create_room")]
    ]
    await message.answer(f"🃏 أهلاً بك {message.from_user.first_name}!\nاختر نظام اللعب:", 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

