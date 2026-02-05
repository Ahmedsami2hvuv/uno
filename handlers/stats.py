from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query

router = Router()

@router.callback_query(F.data == "leaderboard")
async def show_leaderboard(callback: types.CallbackQuery):
    # جلب أفضل 10 لاعبين بناءً على نقاط الأونلاين
    top_players = db_query("SELECT player_name, online_points FROM users WHERE is_registered = TRUE ORDER BY online_points DESC LIMIT 10")
    
    text = "🏆 **قائمة المتصدرين في أونو أونلاين** 🏆\n\n"
    if not top_players:
        text += "لا يوجد متصدرون حالياً. كن الأول!"
    else:
        for i, player in enumerate(top_players, 1):
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            rank = medals.get(i, f"{i}.")
            text += f"{rank} **{player['player_name']}** — {player['online_points']} نقطة\n"
    
    kb = [[InlineKeyboardButton(text="🔙 عودة", callback_data="home")]]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

