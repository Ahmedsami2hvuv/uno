from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import bot, IMG_CW, IMG_CCW

router = Router()

class CalcStates(StatesGroup):
    adding_new_player = State()
    managing_players = State()

# --- البداية ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    data = {
        "all_players": [], 
        "selected": [], 
        "ceiling": 0, 
        "scores": {}, 
        "direction": "CW", 
        "calculated_losers": [],
        "temp_round": {}
    }
    await state.update_data(calc_data=data)
    await render_player_manager(callback.message, state)

async def render_player_manager(message, state):
    state_data = await state.get_data()
    data = state_data.get('calc_data', {})
    kb = []
    
    for p in data.get("all_players", []):
        is_sel = "✅ " if p in data["selected"] else "▫️ "
        kb.append([
            InlineKeyboardButton(text=f"{is_sel}{p}", callback_data=f"sel_{p}"),
            InlineKeyboardButton(text="❌ مسح", callback_data=f"delp_{p}")
        ])
    
    kb.append([InlineKeyboardButton(text="➕ إضافة اسم لاعب", callback_data="add_p_new")])
    if len(data.get("selected", [])) >= 2:
        kb.append([InlineKeyboardButton(text="➡️ اختيار السقف", callback_data="go_ceiling")])
    kb.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")])
    
    text = "🧮 **إدارة لاعبي الجلسة**\nأضف أسماء اللاعبين الآن:"
    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- إضافة اللاعب (التصحيح النهائي) ---
@router.callback_query(F.data == "add_p_new")
async def ask_new_name(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.adding_new_player)
    await callback.message.answer("🖋 أرسل اسم اللاعب الآن (اكتب الاسم وارسله):")
    await callback.answer()

@router.message(CalcStates.adding_new_player)
async def process_new_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    state_data = await state.get_data()
    d = state_data.get('calc_data', {"all_players": [], "selected": []})
    
    if name and name not in d["all_players"]:
        d["all_players"].append(name)
        d["selected"].append(name)
        await state.update_data(calc_data=d)
        await message.answer(f"✅ تم إضافة {name}")
    
    # نرجعه لحالة الانتظار حتى يقدر يضيف لاعب ثاني أو يكمل
    await state.set_state(None) 
    await render_player_manager(message, state)

# --- بقية الدوال (تغيير الاتجاه، السقف، الحساب) ---
# (ملاحظة: كمل باقي الكود اللي اعطيتك اياه سابقاً من "toggle_player" وصعوداً)
