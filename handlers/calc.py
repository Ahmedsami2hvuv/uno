from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from config import bot, IMG_CW, IMG_CCW
from database import db_query

router = Router()

class CalcStates(StatesGroup):
    adding_new_player = State()

# --- وظائف الحفظ (معدلة للـ PostgreSQL) ---
def get_saved_players():
    res = db_query("SELECT player_name FROM calc_players")
    return [r['player_name'] for r in res] if res else []

def save_player_to_db(name):
    # حفظ الاسم والتأكد من نجاح العملية
    db_query("INSERT INTO calc_players (player_name) VALUES (%s) ON CONFLICT (player_name) DO NOTHING", (name,), commit=True)

def delete_player_from_db(name):
    db_query("DELETE FROM calc_players WHERE player_name = %s", (name,), commit=True)

# --- واجهة إدارة اللاعبين ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    saved_p = get_saved_players()
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
    d = (await state.get_data()).get('calc_data', {})
    kb = []
    # عرض الأسامي المحفوظة
    for p in d.get("all_players", []):
        is_sel = "✅ " if p in d["selected"] else "▫️ "
        kb.append([
            InlineKeyboardButton(text=f"{is_sel}{p}", callback_data=f"sel_{p}"),
            InlineKeyboardButton(text="🗑️ مسح من الذاكرة", callback_data=f"delp_{p}")
        ])
    
    kb.append([InlineKeyboardButton(text="➕ إضافة اسم لاعب", callback_data="add_p_new")])
    if len(d.get("selected", [])) >= 2:
        kb.append([InlineKeyboardButton(text="➡️ استمرار (ضبط السقف)", callback_data="go_ceiling")])
    kb.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="home")])
    
    text = "👥 **ذاكرة لاعبي الحاسبة**\nالأسامي هنا تُحفظ وتظهر في الإحصائيات:"
    try: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except: await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "add_p_new")
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CalcStates.adding_new_player)
    await callback.message.answer("🖋️ أرسل اسم اللاعب:")
    await callback.answer()

@router.message(CalcStates.adding_new_player)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()[:15]
    if name:
        save_player_to_db(name) # حفظ بالداتا بيس
        d = (await state.get_data())['calc_data']
        d['all_players'] = get_saved_players() # تحديث القائمة فوراً
        if name not in d["selected"]: d["selected"].append(name)
        await state.update_data(calc_data=d)
    await state.set_state(None)
    await render_player_manager(message, state)

@router.callback_query(F.data.startswith("delp_"))
async def del_p(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split("_")[1]
    delete_player_from_db(name)
    d = (await state.get_data())['calc_data']
    d['all_players'] = get_saved_players()
    if name in d['selected']: d['selected'].remove(name)
    await state.update_data(calc_data=d)
    await render_player_manager(callback.message, state)

@router.callback_query(F.data.startswith("sel_"))
async def toggle_p(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split("_")[1]
    d = (await state.get_data())['calc_data']
    if name in d['selected']: d['selected'].remove(name)
    else: d['selected'].append(name)
    await state.update_data(calc_data=d)
    await render_player_manager(callback.message, state)

# --- ترتيب الأزرار الجديد (حسب طلبك) ---
async def render_keypad(message, state, target, cur_sum):
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
    await message.edit_text(f"🔢 حساب أوراق: **{target}**\nالمجموع الحالي: `{cur_sum}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- تحديث الصورة (edit_media) لحل مشكلة التحميل ---
async def render_main_ui(message, state, extra=""):
    d = (await state.get_data())['calc_data']
    img_url = IMG_CW if d['direction'] == "CW" else IMG_CCW
    table = f"🏆 **السقف: {d['ceiling']}**\n━━━━━━━━━━━━━━\n"
    for p, s in d['scores'].items(): table += f"👤 {p}: `{s}`\n"
    table += "━━━━━━━━━━━━━━\n"
    table += f"🔄 الاتجاه: {'مع العقارب' if d['direction'] == 'CW' else 'عكس العقارب'}"
    if extra: table += f"\n\n📢 {extra}"
    kb = [[InlineKeyboardButton(text="🔄 تغيير الاتجاه", callback_data="c_dir"), InlineKeyboardButton(text="🔔 إنهاء الجولة", callback_data="c_end_round")]]
    
    if message.photo:
        await message.edit_media(media=InputMediaPhoto(media=img_url, caption=table), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await bot.send_photo(message.chat.id, photo=img_url, caption=table, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        try: await message.delete()
        except: pass

# --- بقية الدوال (اختيار السقف، الفائز، إنهاء الجولة) ---
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
    for p, pts in d['temp_round'].items(): d['scores'][p] += pts
    d['scores'][d['current_winner']] += sum_pts
    
    res = f"📝 **نتائج الجولة:**\n"
    for p, s in d['scores'].items():
        change = f"+{d['temp_round'][p]}" if p != d['current_winner'] else f"+{sum_pts}"
        res += f"👤 {p}: {s} ({change})\n"
    
    over = any(s >= d['ceiling'] for s in d['scores'].values())
    if over:
        fw = max(d['scores'], key=d['scores'].get)
        res += f"\n🏁 **انتهت اللعبة!**\nالفائز: **{fw}** 🏆"
        kb = [[InlineKeyboardButton(text="🏠 القائمة", callback_data="home")]]
    else:
        kb = [[InlineKeyboardButton(text="🔄 جولة جديدة", callback_data="c_next_round")]]
    
    await state.update_data(calc_data=d)
    await callback.message.edit_text(res, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "c_next_round")
async def next_rnd(callback: types.CallbackQuery, state: FSMContext):
    await render_main_ui(callback.message, state, "جولة جديدة!")
