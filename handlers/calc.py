from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from config import bot, IMG_CW, IMG_CCW
from database import db_query

router = Router()

class CalcStates(StatesGroup):
    adding_new_player = State()

# --- وظائف قاعدة البيانات (مع عزل المستخدمين) ---
def get_saved_players(user_id):
    # يجلب فقط اللاعبين الخاصين بهذا المستخدم
    res = db_query("SELECT player_name FROM calc_players WHERE creator_id = %s", (user_id,))
    return [r['player_name'] for r in res] if res else []

def save_player_to_db(name, user_id):
    # يحفظ الاسم مع معرف المستخدم لمنع التداخل
    db_query("INSERT INTO calc_players (player_name, creator_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (name, user_id), commit=True)

def delete_player_from_db(name, user_id):
    db_query("DELETE FROM calc_players WHERE player_name = %s AND creator_id = %s", (name, user_id), commit=True)

# --- واجهة إدارة اللاعبين ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    saved_p = get_saved_players(user_id)
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
    
    text = "👥 **ذاكرة الحاسبة الخاصة بك**:"
    try: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except: 
        await message.delete()
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "add_p_new")
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.adding_new_player)
    await callback.message.answer("🖋️ أرسل اسم اللاعب الجديد:")
    await callback.answer()

@router.message(CalcStates.adding_new_player)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()[:15]
    user_id = message.from_user.id
    save_player_to_db(name, user_id)
    d = (await state.get_data())['calc_data']
    d['all_players'] = get_saved_players(user_id)
    if name not in d["selected"]: d["selected"].append(name)
    await state.update_data(calc_data=d)
    await state.set_state(None)
    await render_player_manager(message, state)

# (نفس دوال الاتجاه والسقف تبقى كما هي مع استخدام دالة render_main_ui المصلحة)

@router.callback_query(F.data.startswith("calcpts_"))
async def show_keypad(callback: types.CallbackQuery, state: FSMContext):
    target = callback.data.split("_")[1]
    # تصليح "سكتة البوت": مسح الرسالة القديمة (اللي بيها صورة) وفتح الكيبورد كرسالة نصية
    try: await callback.message.delete()
    except: pass
    await render_keypad(callback.message.chat.id, state, target, 0)

async def render_keypad(chat_id, state, target, cur_sum):
    kb = [
        [InlineKeyboardButton(text="1", callback_data=f"k_{target}_{cur_sum}_1"), InlineKeyboardButton(text="2", callback_data=f"k_{target}_{cur_sum}_2"), InlineKeyboardButton(text="3", callback_data=f"k_{target}_{cur_sum}_3")],
        [InlineKeyboardButton(text="4", callback_data=f"k_{target}_{cur_sum}_4"), InlineKeyboardButton(text="5", callback_data=f"k_{target}_{cur_sum}_5"), InlineKeyboardButton(text="6", callback_data=f"k_{target}_{cur_sum}_6")],
        [InlineKeyboardButton(text="7", callback_data=f"k_{target}_{cur_sum}_7"), InlineKeyboardButton(text="8", callback_data=f"k_{target}_{cur_sum}_8"), InlineKeyboardButton(text="9", callback_data=f"k_{target}_{cur_sum}_9")],
        [InlineKeyboardButton(text="0", callback_data=f"k_{target}_{cur_sum}_0")],
        [InlineKeyboardButton(text="🔄 تحويل (20)", callback_data=f"k_{target}_{cur_sum}_20"), InlineKeyboardButton(text="🚫 منع (20)", callback_data=f"k_{target}_{cur_sum}_20"), InlineKeyboardButton(text="➕2 (20)", callback_data=f"k_{target}_{cur_sum}_20")],
        [InlineKeyboardButton(text="🌈 ملون (50)", callback_data=f"k_{target}_{cur_sum}_50")],
        [InlineKeyboardButton(text="🃏 ملون+1 (10)", callback_data=f"k_{target}_{cur_sum}_10"), InlineKeyboardButton(text="🃏 ملون+2 (20)", callback_data=f"k_{target}_{cur_sum}_20"), InlineKeyboardButton(text="🃏 ملون+4 (50)", callback_data=f"k_{target}_{cur_sum}_50")],
        [InlineKeyboardButton(text="🧹 إعادة", callback_data=f"calcpts_{target}"), InlineKeyboardButton(text="✅ تم", callback_data=f"kdone_{target}_{cur_sum}")]
    ]
    await bot.send_message(chat_id, f"🔢 حساب أوراق: **{target}**\nالمجموع الحالي: `{cur_sum}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("k_"))
async def update_keypad(callback: types.CallbackQuery, state: FSMContext):
    _, target, cur, val = callback.data.split("_")
    # هنا نستخدم edit_text لأن الرسالة نصية أصلاً
    kb = [
        [InlineKeyboardButton(text="1", callback_data=f"k_{target}_{int(cur)+int(val)}_1"), InlineKeyboardButton(text="2", callback_data=f"k_{target}_{int(cur)+int(val)}_2"), InlineKeyboardButton(text="3", callback_data=f"k_{target}_{int(cur)+int(val)}_3")],
        [InlineKeyboardButton(text="4", callback_data=f"k_{target}_{int(cur)+int(val)}_4"), InlineKeyboardButton(text="5", callback_data=f"k_{target}_{int(cur)+int(val)}_5"), InlineKeyboardButton(text="6", callback_data=f"k_{target}_{int(cur)+int(val)}_6")],
        [InlineKeyboardButton(text="7", callback_data=f"k_{target}_{int(cur)+int(val)}_7"), InlineKeyboardButton(text="8", callback_data=f"k_{target}_{int(cur)+int(val)}_8"), InlineKeyboardButton(text="9", callback_data=f"k_{target}_{int(cur)+int(val)}_9")],
        [InlineKeyboardButton(text="0", callback_data=f"k_{target}_{int(cur)+int(val)}_0")],
        [InlineKeyboardButton(text="🔄 تحويل (20)", callback_data=f"k_{target}_{int(cur)+int(val)}_20"), InlineKeyboardButton(text="🚫 منع (20)", callback_data=f"k_{target}_{int(cur)+int(val)}_20"), InlineKeyboardButton(text="➕2 (20)", callback_data=f"k_{target}_{int(cur)+int(val)}_20")],
        [InlineKeyboardButton(text="🌈 ملون (50)", callback_data=f"k_{target}_{int(cur)+int(val)}_50")],
        [InlineKeyboardButton(text="🃏 ملون+1 (10)", callback_data=f"k_{target}_{int(cur)+int(val)}_10"), InlineKeyboardButton(text="🃏 ملون+2 (20)", callback_data=f"k_{target}_{int(cur)+int(val)}_20"), InlineKeyboardButton(text="🃏 ملون+4 (50)", callback_data=f"k_{target}_{int(cur)+int(val)}_50")],
        [InlineKeyboardButton(text="🧹 إعادة", callback_data=f"calcpts_{target}"), InlineKeyboardButton(text="✅ تم", callback_data=f"kdone_{target}_{int(cur)+int(val)}")]
    ]
    await callback.message.edit_text(f"🔢 حساب أوراق: **{target}**\nالمجموع الحالي: `{int(cur)+int(val)}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# (بقية الدوال kdone_ و finish_round_final تبقى كما هي)
