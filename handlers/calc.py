from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

# تعريف قيم النقاط المحدثة
CARD_POINTS = {
    "0":0, "1":1, "2":2, "3":3, "4":4, "5":5, "6":6, "7":7, "8":8, "9":9,
    "🚫":20, "🔄":20, "➕2":20, "🌈":50, "🌈➕1":10, "🌈➕2":20, "🌈➕4":50
}

# تحديث لوحة الأرقام (التي تظهر عند إدخال نقاط اللاعب)
async def render_numpad(msg, player_name, current_score):
    # ترتيب الأزرار بشكل منظم
    layout = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["0", "🚫", "🔄"],
        ["➕2", "🌈", "🌈➕1"], # إضافة الجوكر +1
        ["🌈➕2", "🌈➕4", "تم ✅"]  # إضافة الجوكر +2
    ]
    
    kb = [[InlineKeyboardButton(text=item, callback_data=f"cv_{item}") for item in row] for row in layout]
    
    await msg.edit_text(
        f"👤 اللاعب: {player_name}\n"
        f"🔢 النقاط الحالية: {current_score}\n"
        "اختر الأوراق المتبقية لديه:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

# (بقية منطق الحاسبة والنتائج...)
