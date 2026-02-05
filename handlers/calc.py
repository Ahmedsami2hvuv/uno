from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from config import bot, IMG_CW, IMG_CCW
from database import db_query

router = Router()

class CalcStates(StatesGroup):
    adding_new_player = State()

# --- وظائف قاعدة البيانات المصلحة ---
def get_saved_players(user_id):
    res = db_query("SELECT player_name FROM calc_players WHERE creator_id = %s", (user_id,))
    return [r['player_name'] for r in res] if res else []

def save_player_to_db(name, user_id):
    # نستخدم %s للـ PostgreSQL لضمان الحفظ الصحيح
    db_query("INSERT INTO calc_players (player_name, creator_id) VALUES (%s, %s) ON CONFLICT (player_name, creator_id) DO NOTHING", (name, user_id), commit=True)

def delete_player_from_db(name, user_id):
    db_query("DELETE FROM calc_players WHERE player_name = %s AND creator_id = %s", (name, user_id), commit=True)

# --- واجهة إدارة اللاعبين ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
    # جلب الأسامي المحفوظة لهذا المستخدم تحديداً
    saved_p = get_saved_players(uid)
    data = {
        "all_players": saved_p, 
        "selected": [], 
        "ceiling": 0, 
        "scores": {}, 
        "direction": "CW", 
        "calculated_losers": [], 
        "temp_round": {}, 
        "current_winner": ""
    }
    await state.update_data(calc_data=data)
    await render_player_manager(callback.message, state)

async def render_player_manager(message, state):
    state_data = await state.get_data()
    d = state_data.get('calc_data', {})
    kb = []
    # هنا تظهر الأسماء المخزونة
    for p in d.get("all_players", []):
        is_sel = "✅ " if p in d["selected"] else "▫️ "
        kb.append([
            InlineKeyboardButton(text=f"{is_sel}{p}", callback_data=f"sel_{p}"),
            InlineKeyboardButton(text="🗑️ مسح", callback_data=f"delp_{p}")
        ])
    
    kb.append([InlineKeyboardButton(text="➕ إضافة اسم لاعب", callback_data="add_p_new")])
    if len(d.get("selected", [])) >= 2:
        kb.append([InlineKeyboardButton(text="➡️ ابدأ اللعب", callback_data="go_ceiling")])
    kb.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="home")])
    
    text = "👥 **ذاكرة لاعبي الحاسبة الخاصة بك**:\n(الأسماء تظهر هنا بعد كتابتها)"
    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "add_p_new")
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.adding_new_player)
    await callback.message.answer("🖋️ أرسل اسم اللاعب:")
    await callback.answer()

@router.message(CalcStates.adding_new_player)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()[:15]
    uid = message.from_user.id
    if name:
        # 1. الحفظ في الداتا بيس
        save_player_to_db(name, uid)
        
        # 2. تحديث البيانات في الـ State
        state_data = await state.get_data()
        d = state_data['calc_data']
        d['all_players'] = get_saved_players(uid) # إعادة جلب القائمة المحدثة
        if name not in d["selected"]:
            d["selected"].append(name)
        
        await state.update_data(calc_data=d)
    
    await state.set_state(None)
    # 3. العودة لعرض القائمة (الآن سيظهر الاسم الجديد)
    await render_player_manager(message, state)

# --- الدوال الأخرى (الاتجاه، السقف، الكيبورد) تبقى كما هي من الكود السابق ---
# تأكد من نسخ باقي الملف من الرسالة السابقة إذا كنت تمسح الملف بالكامل
