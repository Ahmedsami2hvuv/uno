from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import bot, IMG_CW, IMG_CCW

router = Router()

class CalcStates(StatesGroup):
    adding_new_player = State()
    choosing_ceiling = State()
    main_session = State()
    selecting_winner = State()

# --- البداية ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    data = {
        "all_players": [], "selected": [], "ceiling": 0, "scores": {}, 
        "direction": "CW", "calculated_losers": [], "temp_round": {}, "current_winner": ""
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
        kb.append([InlineKeyboardButton(text="➡️ ابدأ اللعب (اختيار السقف)", callback_data="go_ceiling")])
    kb.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")])
    
    text = "🧮 **حاسبة الجلسة اليدوية**\nأضف أسماء اللاعبين (خطارك أو أصدقائك):"
    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- إضافة لاعب (تصحيح الاستلام) ---
@router.callback_query(F.data == "add_p_new")
async def ask_new_name(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.adding_new_player)
    await callback.message.answer("🖋 أرسل اسم اللاعب الآن (اكتبه بالدردشة):")
    await callback.answer()

@router.message(CalcStates.adding_new_player)
async def process_new_name(message: types.Message, state: FSMContext):
    name = message.text.strip()[:15]
    state_data = await state.get_data()
    d = state_data.get('calc_data', {"all_players": [], "selected": []})
    
    if name and name not in d["all_players"]:
        d["all_players"].append(name)
        d["selected"].append(name)
        await state.update_data(calc_data=d)
        await message.answer(f"✅ تم إضافة: {name}")
    
    # العودة لانتظار إدارة اللاعبين
    await state.set_state(None)
    await render_player_manager(message, state)

# --- بقية المنطق (السقف، الحساب، الكيبورد) ---
@router.callback_query(F.data.startswith("delp_"))
async def delete_player(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split("_")[1]
    d = (await state.get_data())['calc_data']
    if name in d['all_players']: d['all_players'].remove(name)
    if name in d['selected']: d['selected'].remove(name)
    await state.update_data(calc_data=d)
    await render_player_manager(callback.message, state)

@router.callback_query(F.data.startswith("sel_"))
async def toggle_player(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split("_")[1]
    d = (await state.get_data())['calc_data']
    if name in d['selected']: d['selected'].remove(name)
    else: d['selected'].append(name)
    await state.update_data(calc_data=d)
    await render_player_manager(callback.message, state)

@router.callback_query(F.data == "go_ceiling")
async def choose_ceiling(callback: types.CallbackQuery, state: FSMContext):
    kb = [
        [InlineKeyboardButton(text="100", callback_data="set_100"), InlineKeyboardButton(text="150", callback_data="set_150"), InlineKeyboardButton(text="200", callback_data="set_200")],
        [InlineKeyboardButton(text="250", callback_data="set_250"), InlineKeyboardButton(text="300", callback_data="set_300"), InlineKeyboardButton(text="350", callback_data="set_350")],
        [InlineKeyboardButton(text="400", callback_data="set_400"), InlineKeyboardButton(text="450", callback_data="set_450"), InlineKeyboardButton(text="500", callback_data="set_500")]
    ]
    await callback.message.edit_text("🎯 **اختر سقف نقاط الخسارة:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

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
    table = f"🏆 **سقف اللعب: {d['ceiling']}**\n━━━━━━━━━━━━━━\n"
    for p, s in d['scores'].items(): table += f"👤 {p}: `{s}`\n"
    table += "━━━━━━━━━━━━━━\n"
    table += f"🔄 الاتجاه: {'مع العقارب' if d['direction'] == 'CW' else 'عكس العقارب'}"
    if extra: table += f"\n\n📢 {extra}"
    kb = [[InlineKeyboardButton(text="🔄 تغيير الاتجاه", callback_data="c_dir"), InlineKeyboardButton(text="🔔 إنهاء الجولة", callback_data="c_end_round")],
          [InlineKeyboardButton(text="❌ إنهاء كلي", callback_data="home")]]
    try: await message.delete()
    except: pass
    await bot.send_photo(message.chat.id, photo=img, caption=table, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

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
    sorted_players = sorted(d['temp_round'].keys(), key=lambda x: x in d['calculated_losers'], reverse=True)
    kb = []
    for p in sorted_players:
        mark = "✅ " if p in d['calculated_losers'] else "⏳ "
        kb.append([InlineKeyboardButton(text=f"{mark}{p} ({d['temp_round'][p]})", callback_data=f"calcpts_{p}")])
    if len(d['calculated_losers']) == len(d['temp_round']):
        kb.append([InlineKeyboardButton(text="✅ تأكيد النتائج", callback_data="c_finish_round_now")])
    await message.edit_text("📉 **حساب أوراق الخاسرين:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("calcpts_"))
async def show_keypad(callback: types.CallbackQuery, state: FSMContext):
    target = callback.data.split("_")[1]
    await render_keypad(callback.message, state, target, 0)

async def render_keypad(message, state, target, cur_sum):
    kb = [
        [InlineKeyboardButton(text="1", callback_data=f"k_{target}_{cur_sum}_1"), InlineKeyboardButton(text="2", callback_data=f"k_{target}_{cur_sum}_2"), InlineKeyboardButton(text="3", callback_data=f"k_{target}_{cur_sum}_3")],
        [InlineKeyboardButton(text="4", callback_data=f"k_{target}_{cur_sum}_4"), InlineKeyboardButton(text="5", callback_data=f"k_{target}_{cur_sum}_5"), InlineKeyboardButton(text="6", callback_data=f"k_{target}_{cur_sum}_6")],
        [InlineKeyboardButton(text="7", callback_data=f"k_{target}_{cur_sum}_7"), InlineKeyboardButton(text="8", callback_data=f"k_{target}_{cur_sum}_8"), InlineKeyboardButton(text="9", callback_data=f"k_{target}_{cur_sum}_9")],
        [InlineKeyboardButton(text="0", callback_data=f"k_{target}_{cur_sum}_0")],
        [InlineKeyboardButton(text="🔄 (20)", callback_data=f"k_{target}_{cur_sum}_20"), InlineKeyboardButton(text="🚫 (20)", callback_data=f"k_{target}_{cur_sum}_20"), InlineKeyboardButton(text="➕2 (20)", callback_data=f"k_{target}_{cur_sum}_20")],
        [InlineKeyboardButton(text="🃏 س2 (20)", callback_data=f"k_{target}_{cur_sum}_20"), InlineKeyboardButton(text="🃏 س1 (10)", callback_data=f"k_{target}_{cur_sum}_10")],
        [InlineKeyboardButton(text="🌈+4 (50)", callback_data=f"k_{target}_{cur_sum}_50"), InlineKeyboardButton(text="🌈+2 (50)", callback_data=f"k_{target}_{cur_sum}_50"), InlineKeyboardButton(text="🌈+1 (50)", callback_data=f"k_{target}_{cur_sum}_50")],
        [InlineKeyboardButton(text="🧹 إعادة", callback_data=f"calcpts_{target}"), InlineKeyboardButton(text="✅ تم", callback_data=f"kdone_{target}_{cur_sum}")]
    ]
    await message.edit_text(f"🔢 حساب: **{target}**\nالمجموع: `{cur_sum}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("k_"))
async def update_keypad(callback: types.CallbackQuery, state: FSMContext):
    _, target, cur, val = callback.data.split("_")
    await render_keypad(callback.message, state, target, int(cur) + int(val))

@router.callback_query(F.data.startswith("kdone_"))
async def save_loser_pts(callback: types.CallbackQuery, state: FSMContext):
    _, target, f_val = callback.data.split("_")
    d = (await state.get_data())['calc_data']
    d['temp_round'][target] = int(f_val)
    if target not in d['calculated_losers']: d['calculated_losers'].append(target)
    await state.update_data(calc_data=d)
    await render_loser_list(callback.message, state)

@router.callback_query(F.data == "c_finish_round_now")
async def finish_round_final(callback: types.CallbackQuery, state: FSMContext):
    d = (await state.get_data())['calc_data']
    sum_pts = sum(d['temp_round'].values())
    res = "📝 **نتائج الجولة:**\n"
    for p, pts in d['temp_round'].items():
        res += f"👤 {p}: +{pts}\n"
        d['scores'][p] += pts
    res += f"\n🏆 الفائز {d['current_winner']} جمع: +{sum_pts}"
    over = any(s >= d['ceiling'] for s in d['scores'].values())
    kb = [[InlineKeyboardButton(text="🔄 جولة جديدة", callback_data="c_next_round")]]
    if over:
        fw = min(d['scores'], key=d['scores'].get)
        res += f"\n\n🏁 **اللعبة انتهت!**\nالفائز الكلي: **{fw}**"
        kb = [[InlineKeyboardButton(text="🏠 القائمة", callback_data="home")]]
    await state.update_data(calc_data=d)
    await callback.message.edit_text(res, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "c_next_round")
async def next_rnd(callback: types.CallbackQuery, state: FSMContext):
    await render_main_ui(callback.message, state, "جولة جديدة!")
