from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from config import bot, IMG_CW, IMG_CCW
from database import db_query

router = Router()

class CalcStates(StatesGroup):
    adding_new_player = State()

# --- وظائف قاعدة البيانات ---
def check_and_create_table():
    db_query('''CREATE TABLE IF NOT EXISTS calc_players (
                id SERIAL PRIMARY KEY,
                player_name TEXT,
                creator_id BIGINT,
                wins INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                UNIQUE(player_name, creator_id))''', commit=True)

def get_saved_players(user_id):
    check_and_create_table()
    res = db_query("SELECT player_name FROM calc_players WHERE creator_id = %s", (user_id,))
    return [r['player_name'] for r in res] if res else []

def save_player_to_db(name, user_id):
    check_and_create_table()
    db_query("INSERT INTO calc_players (player_name, creator_id) VALUES (%s, %s) ON CONFLICT (player_name, creator_id) DO NOTHING", (name, user_id), commit=True)

def delete_player_from_db(name, user_id):
    db_query("DELETE FROM calc_players WHERE player_name = %s AND creator_id = %s", (name, user_id), commit=True)

# --- واجهة إدارة اللاعبين ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
    saved_p = get_saved_players(uid)
    # تهيئة البيانات في الذاكرة
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
    
    # تحديث القائمة من الداتا بيس لضمان ظهور الأسماء الجديدة
    uid = (await state.get_data()).get('uid', message.chat.id) # احتياطي
    d['all_players'] = get_saved_players(message.chat.id) 
    
    kb_list = []
    # بناء الأزرار لكل لاعب
    for p in d.get("all_players", []):
        is_sel = "✅ " if p in d.get("selected", []) else "▫️ "
        kb_list.append([
            InlineKeyboardButton(text=f"{is_sel}{p}", callback_data=f"sel_{p}"),
            InlineKeyboardButton(text="🗑️ مسح", callback_data=f"delp_{p}")
        ])
    
    kb_list.append([InlineKeyboardButton(text="➕ إضافة اسم لاعب جديد", callback_data="add_p_new")])
    
    if len(d.get("selected", [])) >= 2:
        kb_list.append([InlineKeyboardButton(text="➡️ استمرار لضبط السقف", callback_data="go_ceiling")])
    
    kb_list.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")])
    
    text = "👥 **قائمة لاعبي الحاسبة**\n\n- اختر اللاعبين الذين سيشاركون الآن (يظهر ✅ بجانب المختار).\n- إذا لم تظهر الأسماء، أضف لاعباً جديداً."
    
    # محاولة تعديل الرسالة، وإذا فشل يرسل وحدة جديدة
    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
    except:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@router.callback_query(F.data == "add_p_new")
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.adding_new_player)
    await callback.message.answer("🖋️ أرسل اسم اللاعب الجديد الآن:")
    await callback.answer()

@router.message(CalcStates.adding_new_player)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()[:15]
    uid = message.from_user.id
    if name:
        save_player_to_db(name, uid)
        # سحب البيانات الحالية وتحديثها
        state_data = await state.get_data()
        d = state_data.get('calc_data', {})
        d['all_players'] = get_saved_players(uid)
        # تلقائياً نختار اللاعب الجديد
        if name not in d.get("selected", []):
            d.setdefault("selected", []).append(name)
        await state.update_data(calc_data=d)
    
    await state.set_state(None)
    await render_player_manager(message, state)

@router.callback_query(F.data.startswith("sel_"))
async def toggle_p(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split("_")[1]
    state_data = await state.get_data()
    d = state_data.get('calc_data', {})
    
    if name in d.get("selected", []):
        d["selected"].remove(name)
    else:
        d.setdefault("selected", []).append(name)
    
    await state.update_data(calc_data=d)
    await render_player_manager(callback.message, state)

@router.callback_query(F.data.startswith("delp_"))
async def del_p(callback: types.CallbackQuery, state: FSMContext):
    name, uid = callback.data.split("_")[1], callback.from_user.id
    delete_player_from_db(name, uid)
    state_data = await state.get_data()
    d = state_data.get('calc_data', {})
    d['all_players'] = get_saved_players(uid)
    if name in d.get("selected", []): d["selected"].remove(name)
    await state.update_data(calc_data=d)
    await render_player_manager(callback.message, state)

# --- استمرار بقية الكود (السقف والكيبورد) من النسخة السابقة ---
# (تأكد من إبقاء دوال go_ceiling و render_main_ui و render_keypad كما هي)
