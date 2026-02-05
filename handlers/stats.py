from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query

router = Router()

@router.callback_query(F.data == "leaderboard")
async def show_leaderboard(callback: types.CallbackQuery):
    top = db_query("SELECT player_name, online_points FROM users WHERE is_registered = TRUE ORDER BY online_points DESC LIMIT 10")
    txt = "🏆 **قائمة المتصدرين**\n\n"
    if not top: txt += "لا يوجد متصدرون حالياً."
    else:
        for i, p in enumerate(top, 1):
            txt += f"{i}. {p['player_name']} — {p['online_points']} نقطة\n"
    kb = [[InlineKeyboardButton(text="🔙 عودة", callback_data="home")]]
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "my_profile")
async def show_profile(callback: types.CallbackQuery):
    user = db_query("SELECT * FROM users WHERE user_id = %s", (callback.from_user.id,))[0]
    txt = (f"👤 **حسابك الشخصي**\n\n"
           f"📛 الاسم: {user['player_name']}\n"
           f"🔑 الرمز: {user['password']}\n"
           f"⭐ النقاط: {user['online_points']}")
    kb = [[InlineKeyboardButton(text="🔙 عودة", callback_data="home")]]
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
