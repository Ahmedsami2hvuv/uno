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
def get_saved_players(user_id):
    sql = "SELECT player_name FROM calc_players WHERE creator_id = %s"
    res = db_query(sql, (user_id,))
    return [r['player_name'] for r in res] if res else []

def save_player_to_db(name, user_id):
    sql = "INSERT INTO calc_players (player_name, creator_id) VALUES (%s, %s) ON CONFLICT (player_name, creator_id) DO NOTHING"
    db_query(sql, (name, user_id), commit=True)

def delete_player_from_db(name, user_id):
    db_query("DELETE FROM calc_players WHERE player_name = %s AND creator_id = %s", (name, user_id), commit=True)

# --- واجهة إدارة اللاعبين ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
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
    uid = message.chat.id
    d['all_players'] = get_saved_players(uid) 
    
    kb_list = []
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
    
    text = "👥 **قائمة لاعبي الحاسبة**\n\nاختر اللاعبين المشاركين (✅) أو أضف لاعباً جديداً:"
    try: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
    except: await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@router.callback_query(F.data == "add_p_new")
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.adding_new_player)
    await callback.message.answer("🖋️ أرسل اسم اللاعب الجديد:")
    await callback.answer()

@router.message(CalcStates.adding_new_player)
async def process_name(message: types.Message, state: FSMContext):
    name, uid = message.text.strip()[:15], message.from_user.id
    if name:
        save_player_to_db(name, uid)
        state_data = await state.get_data()
        d = state_data.get('calc_data', {})
        d['all_players'] = get_saved_players(uid)
        if name not in d.get("selected", []): d.setdefault("selected", []).append(name)
        await state.update_data(calc_data=d)
    await state.set_state(None)
    await render_player_manager(message, state)

@router.callback_query(F.data.startswith("sel_"))
async def toggle_p(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split("_")[1]
    state_data = await state.get_data()
    d = state_data.get('calc_data', {})
    if name in d.get("selected", []): d["selected"].remove(name)
    else: d.setdefault("selected", []).append(name)
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

# --- سقف اللعب ---
@router.callback_query(F.data == "go_ceiling")
async def choose_ceiling(callback: types.CallbackQuery, state: FSMContext):
    kb = [[InlineKeyboardButton(text=str(x), callback_data=f"set_{x}") for x in [100, 150, 200]],
          [InlineKeyboardButton(text=str(x), callback_data=f"set_{x}") for x in [250, 300, 400]],
          [InlineKeyboardButton(text="500", callback_data="set_500")]]
    await callback.message.edit_text("🎯 **حدد سقف الخسارة:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("set_"))
async def start_session(callback: types.CallbackQuery, state: FSMContext):
    val = int(callback.data.split("_")[1])
    d = (await state.get_data())['calc_data']
    d['ceiling'] = val
    d['scores'] = {p: 0 for p in d['selected']}
    await state.update_data(calc_data=d)
    await render_main_ui(callback.message, state)

async def render_main_ui(message, state, extra=""):
    d = (await state.get_data())['calc_data']
    img = IMG_CW if d['direction'] == "CW" else IMG_CCW
    table = f"🏆 **السقف: {d['ceiling']}**\n━━━━━━━━━━━━━━\n"
    for p, s in d['scores'].items(): table += f"👤 {p}: `{s}`\n"
    table += "━━━━━━━━━━━━━━\n"
    table += f"🔄 الاتجاه: {'مع العقارب' if d['direction'] == 'CW' else 'عكس العقارب'}"
    if extra: table += f"\n\n📢 {extra}"
    kb = [[InlineKeyboardButton(text="🔄 تغيير الاتجاه", callback_data="c_dir"), InlineKeyboardButton(text="🔔 إنهاء الجولة", callback_data="c_end_round")]]
    if message.photo: await message.edit_media(media=InputMediaPhoto(media=img, caption=table), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else: 
        await bot.send_photo(message.chat.id, photo=img, caption=table, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        try: await message.delete()
        except: pass

@router.callback_query(F.data == "c_dir")
async def c_toggle_dir(callback: types.CallbackQuery, state: FSMContext):
    d = (await state.get_data())['calc_data']
    d['direction'] = "CCW" if d['direction'] == "CW" else "CW"
    await state.update_data(calc_data=d)
    await render_main_ui(callback.message, state)

@router.callback_query(F.data == "c_end_round")
async def select_winner_init(callback: types.CallbackQuery, state: FSMContext):
    d = (await state.get_data())['calc_data']
    kb = [[InlineKeyboardButton(text=p, callback_data=f"win_{p}")] for p in d['selected']]
    await callback.message.answer("🏆 **من هو الفائز بهذه الجولة؟**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("win_"))
async def start_points_calc(callback: types.CallbackQuery, state: FSMContext):
    winner = callback.data.split("_")[1]
    d = (await state.get_data())['calc_data']
    d['current_winner'] = winner
    d['temp_round'] = {p: 0 for p in d['selected'] if p != winner}
    d['calculated_losers'] = []
    await state.update_data(calc_data=d)
    await render_loser_list(callback.message, state)

async def render_loser_list(message, state):
    d = (await state.get_data())['calc_data']
    kb = []
    for p in d['temp_round'].keys():
        mark = "✅ " if p in d['calculated_losers'] else "⏳ "
        kb.append([InlineKeyboardButton(text=f"{mark}{p} ({d['temp_round'][p]})", callback_data=f"calcpts_{p}")])
    if len(d['calculated_losers']) == len(d['temp_round']):
        kb.append([InlineKeyboardButton(text="✅ تأكيد وحساب النقاط", callback_data="c_finish_round_now")])
    await message.edit_text("📉 **حساب أوراق الخاسرين:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- الكيبورد المصلح وحساب الأوراق ---
@router.callback_query(F.data.startswith("calcpts_"))
async def show_keypad(callback: types.CallbackQuery, state: FSMContext):
    target = callback.data.split("_")[1]
    try: await callback.message.delete()
    except: pass
    await render_keypad(callback.message.chat.id, state, target, 0)

async def render_keypad(cid, state, target, cur):
    kb = [
        [InlineKeyboardButton(text="1", callback_data=f"k_{target}_{cur}_1"), InlineKeyboardButton(text="2", callback_data=f"k_{target}_{cur}_2"), InlineKeyboardButton(text="3", callback_data=f"k_{target}_{cur}_3")],
        [InlineKeyboardButton(text="4", callback_data=f"k_{target}_{cur}_4"), InlineKeyboardButton(text="5", callback_data=f"k_{target}_{cur}_5"), InlineKeyboardButton(text="6", callback_data=f"k_{target}_{cur}_6")],
        [InlineKeyboardButton(text="7", callback_data=f"k_{target}_{cur}_7"), InlineKeyboardButton(text="8", callback_data=f"k_{target}_{cur}_8"), InlineKeyboardButton(text="9", callback_data=f"k_{target}_{cur}_9")],
        [InlineKeyboardButton(text="0", callback_data=f"k_{target}_{cur}_0")],
        [InlineKeyboardButton(text="🔄 (20)", callback_data=f"k_{target}_{cur}_20"), InlineKeyboardButton(text="🚫 (20)", callback_data=f"k_{target}_{cur}_20"), InlineKeyboardButton(text="➕2 (20)", callback_data=f"k_{target}_{cur}_20")],
        [InlineKeyboardButton(text="🌈 ملون (50)", callback_data=f"k_{target}_{cur}_50")],
        [InlineKeyboardButton(text="🃏 م+1 (10)", callback_data=f"k_{target}_{cur}_10"), InlineKeyboardButton(text="🃏 م+2 (20)", callback_data=f"k_{target}_{cur}_20"), InlineKeyboardButton(text="🃏 م+4 (50)", callback_data=f"k_{target}_{cur}_50")],
        [InlineKeyboardButton(text="🧹 إعادة", callback_data=f"calcpts_{target}"), InlineKeyboardButton(text="✅ تم", callback_data=f"kdone_{target}_{cur}")]
    ]
    await bot.send_message(cid, f"🔢 حساب: **{target}**\nالمجموع: `{cur}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("k_"))
async def update_keypad(callback: types.CallbackQuery, state: FSMContext):
    _, t, c, v = callback.data.split("_")
    new = int(c) + int(v)
    # إعادة بناء الكيبورد مع الرقم الجديد
    kb = [
        [InlineKeyboardButton(text="1", callback_data=f"k_{t}_{new}_1"), InlineKeyboardButton(text="2", callback_data=f"k_{t}_{new}_2"), InlineKeyboardButton(text="3", callback_data=f"k_{t}_{new}_3")],
        [InlineKeyboardButton(text="4", callback_data=f"k_{t}_{new}_4"), InlineKeyboardButton(text="5", callback_data=f"k_{t}_{new}_5"), InlineKeyboardButton(text="6", callback_data=f"k_{t}_{new}_6")],
        [InlineKeyboardButton(text="7", callback_data=f"k_{t}_{new}_7"), InlineKeyboardButton(text="8", callback_data=f"k_{t}_{new}_8"), InlineKeyboardButton(text="9", callback_data=f"k_{t}_{new}_9")],
        [InlineKeyboardButton(text="0", callback_data=f"k_{t}_{new}_0")],
        [InlineKeyboardButton(text="🔄 (20)", callback_data=f"k_{t}_{new}_20"), InlineKeyboardButton(text="🚫 (20)", callback_data=f"k_{t}_{new}_20"), InlineKeyboardButton(text="➕2 (20)", callback_data=f"k_{t}_{new}_20")],
        [InlineKeyboardButton(text="🌈 ملون (50)", callback_data=f"k_{t}_{new}_50")],
        [InlineKeyboardButton(text="🃏 م+1 (10)", callback_data=f"k_{t}_{new}_10"), InlineKeyboardButton(text="🃏 م+2 (20)", callback_data=f"k_{t}_{new}_20"), InlineKeyboardButton(text="🃏 م+4 (50)", callback_data=f"k_{t}_{new}_50")],
        [InlineKeyboardButton(text="🧹 إعادة", callback_data=f"calcpts_{t}"), InlineKeyboardButton(text="✅ تم", callback_data=f"kdone_{t}_{new}")]
    ]
    await callback.message.edit_text(f"🔢 حساب: **{t}**\nالمجموع: `{new}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("kdone_"))
async def save_loser_pts(callback: types.CallbackQuery, state: FSMContext):
    _, t, f = callback.data.split("_")
    d = (await state.get_data())['calc_data']
    d['temp_round'][t] = int(f)
    if t not in d['calculated_losers']: d['calculated_losers'].append(t)
    await state.update_data(calc_data=d)
    await render_loser_list(callback.message, state)

@router.callback_query(F.data == "c_finish_round_now")
async def finish_round_final(callback: types.CallbackQuery, state: FSMContext):
    d = (await state.get_data())['calc_data']
    sum_pts = sum(d['temp_round'].values())
    for p, pts in d['temp_round'].items(): d['scores'][p] += pts
    d['scores'][d['current_winner']] += sum_pts
    res = f"📝 **نتائج الجولة:**\n"
    for p, s in d['scores'].items():
        ch = f"+{d['temp_round'][p]}" if p != d['current_winner'] else f"+{sum_pts}"
        res += f"👤 {p}: {s} ({ch})\n"
    if any(s >= d['ceiling'] for s in d['scores'].values()):
        fw = max(d['scores'], key=d['scores'].get)
        res += f"\n🏁 **انتهت اللعبة!**\nالفائز: **{fw}** 🏆"
        kb = [[InlineKeyboardButton(text="🏠 القائمة", callback_data="home")]]
    else: kb = [[InlineKeyboardButton(text="🔄 جولة جديدة", callback_data="c_next_round")]]
    await state.update_data(calc_data=d)
    await callback.message.edit_text(res, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "c_next_round")
async def next_rnd(callback: types.CallbackQuery, state: FSMContext):
    await render_main_ui(callback.message, state, "جولة جديدة!")
