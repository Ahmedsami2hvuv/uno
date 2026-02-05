from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query

router = Router()

@router.callback_query(F.data == "leaderboard")
async def show_leaderboard(callback: types.CallbackQuery):
    # جلب التوب 10
    top = db_query("SELECT player_name, online_points FROM users WHERE is_registered = TRUE ORDER BY online_points DESC LIMIT 10")
    
    txt = "🏆 **قائمة المتصدرين (أونلاين)** 🏆\n\n"
    if not top:
        txt += "لا يوجد لاعبون مسجلون حالياً."
    else:
        for i, p in enumerate(top, 1):
            txt += f"{i}. {p['player_name']} — {p['online_points']} نقطة\n"
    
    kb = [[InlineKeyboardButton(text="🔙 عودة", callback_data="home")]]
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
