import asyncio
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import bot, IMG_CW, IMG_CCW
from database import db_query

router = Router()

# --- تعريف الحالات المعقدة للحاسبة ---
class CalcStates(StatesGroup):
    managing_players = State()
    adding_new_player = State()
    choosing_ceiling = State()
    main_session = State()
    selecting_winner = State()
    calculating_loser_points = State()

# --- 1. البداية: اختيار اللاعبين ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    # جلب أسماء اللاعبين المسجلين في النظام سابقاً (اختياري) أو البدء بقائمة فارغة
    data = {"all_players": [], "selected": [], "ceiling": 0, "scores": {}, "direction": "CW", "history": []}
    await state.update_data(calc_data=data)
    await render_player_manager(callback.message, state)

async def render_player_manager(message, state):
    data = (await state.get_data())['calc_data']
    kb = []
    # عرض اللاعبين مع علامة صح
    for p in data['all_players']:
        mark = "✅ " if p in data['selected'] else ""
        kb.append([InlineKeyboardButton(text=f"{mark}{p}", callback_data=f"sel_{p}")])
    
    kb.append([InlineKeyboardButton(text="➕ إضافة لاعب جديد", callback_data="add_p_new")])
    if len(data['selected']) >= 2:
        kb.append([InlineKeyboardButton(text="➡️ استمرار (اختيار السقف)", callback_data="go_ceiling")])
    
    text = "👥 **إدارة اللاعبين**\nاختر اللاعبين المشاركين (بحد أقصى 10):"
    await (message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)) if hasattr(message, "edit_text") else message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)))

# --- إضافة لاعب ومسح ---
@router.callback_query(F.data == "add_p_new")
async def ask_new_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("أرسل اسم اللاعب الجديد:")
    await state.set_state(CalcStates.adding_new_player)

@router.message(CalcStates.adding_new_player)
async def process_new_name(message: types.Message, state: FSMContext):
    name = message.text.strip()[:15]
    d = (await state.get_data())['calc_data']
    if name not in d['all_players'] and len(d['all_players']) < 10:
        d['all_players'].append(name)
        d['selected'].append(name)
    await state.update_data(calc_data=d)
    await render_player_manager(message, state)

@router.callback_query(F.data.startswith("sel_"))
async def toggle_player(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split("_")[1]
    d = (await state.get_data())['calc_data']
    if name in d['selected']: d['selected'].remove(name)
    else: d['selected'].append(name)
    await state.update_data(calc_data=d)
    await render_player_manager(callback.message, state)

# --- 2. اختيار سقف اللعب ---
@router.callback_query(F.data == "go_ceiling")
async def choose_ceiling(callback: types.CallbackQuery, state: FSMContext):
    kb = [
        [InlineKeyboardButton(text="100", callback_data="set_100"), InlineKeyboardButton(text="150", callback_data="set_150"), InlineKeyboardButton(text="200", callback_data="set_200")],
        [InlineKeyboardButton(text="250", callback_data="set_250"), InlineKeyboardButton(text="300", callback_data="set_300"), InlineKeyboardButton(text="350", callback_data="set_350")],
        [InlineKeyboardButton(text="400", callback_data="set_400"), InlineKeyboardButton(text="450", callback_data="set_450"), InlineKeyboardButton(text="500", callback_data="set_500")]
    ]
    await callback.message.edit_text("🎯 **اختيار سقف اللعب**\nمتى تنتهي اللعبة؟ اختر النقاط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("set_"))
async def start_session(callback: types.CallbackQuery, state: FSMContext):
    val = int(callback.data.split("_")[1])
    d = (await state.get_data())['calc_data']
    d['ceiling'] = val
    d['scores'] = {p: 0 for p in d['selected']}
    await state.update_data(calc_data=d)
    await render_main_ui(callback.message, state)

# --- 3. الواجهة الرئيسية للجولة ---
async def render_main_ui(message, state, extra=""):
    d = (await state.get_data())['calc_data']
    img = IMG_CW if d['direction'] == "CW" else IMG_CCW
    table = f"🏆 **السقف: {d['ceiling']}**\n━━━━━━━━━━━━━━\n"
    for p, s in d['scores'].items():
        table += f"👤 {p}: `{s}`\n"
    table += "━━━━━━━━━━━━━━\n"
    table += f"🔄 الاتجاه: {'مع العقارب' if d['direction'] == 'CW' else 'عكس العقارب'}"
    if extra: table += f"\n\n📢 {extra}"

    kb = [
        [InlineKeyboardButton(text="🔄 تغيير الاتجاه", callback_data="c_dir"), InlineKeyboardButton(text="🔔 إنهاء الجولة", callback_data="c_end_round")],
        [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="c_stats"), InlineKeyboardButton(text="❌ إنهاء كلي", callback_data="home")]
    ]
    try: await message.delete()
    except: pass
    await bot.send_photo(message.chat.id, photo=img, caption=table, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "c_dir")
async def c_toggle_dir(callback: types.CallbackQuery, state: FSMContext):
    d = (await state.get_data())['calc_data']
    d['direction'] = "CCW" if d['direction'] == "CW" else "CW"
    await state.update_data(calc_data=d)
    await render_main_ui(callback.message, state)

# --- 4. إنهاء الجولة واختيار الفائز ---
@router.callback_query(F.data == "c_end_round")
async def confirm_end(callback: types.CallbackQuery):
    kb = [[InlineKeyboardButton(text="✅ نعم، إنهاء", callback_data="c_confirm_yes"), InlineKeyboardButton(text="❌ لا", callback_data="c_confirm_no")]]
    await callback.message.answer("⚠️ هل أنت متأكد من إنهاء هذه الجولة؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "c_confirm_yes")
async def select_winner(callback: types.CallbackQuery, state: FSMContext):
    d = (await state.get_data())['calc_data']
    kb = [[InlineKeyboardButton(text=p, callback_data=f"win_{p}")] for p in d['selected']]
    await callback.message.edit_text("🏆 **من هو الفائز في هذه الجولة؟**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("win_"))
async def confirm_winner(callback: types.CallbackQuery, state: FSMContext):
    winner = callback.data.split("_")[1]
    kb = [[InlineKeyboardButton(text="✅ نعم", callback_data=f"wconf_{winner}"), InlineKeyboardButton(text="❌ لا", callback_data="c_confirm_yes")]]
    await callback.message.edit_text(f"هل أنت متأكد أن الفائز هو **{winner}**؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("wconf_"))
async def start_points_calc(callback: types.CallbackQuery, state: FSMContext):
    winner = callback.data.split("_")[1]
    d = (await state.get_data())['calc_data']
    d['current_winner'] = winner
    d['temp_round'] = {p: 0 for p in d['selected'] if p != winner}
    d['calculated_losers'] = []
    await state.update_data(calc_data=d)
    await render_loser_list(callback.message, state)

# --- 5. حاسبة الأوراق الذكية ---
async def render_loser_list(message, state):
    d = (await state.get_data())['calc_data']
    kb = []
    for p in d['temp_round'].keys():
        mark = "✅ " if p in d['calculated_losers'] else "⏳ "
        kb.append([InlineKeyboardButton(text=f"{mark}{p} ({d['temp_round'][p]})", callback_data=f"calcpts_{p}")])
    
    if len(d['calculated_losers']) == len(d['temp_round']):
        kb.append([InlineKeyboardButton(text="✅ تم الحساب (عرض النتائج)", callback_data="c_finish_round_now")])
    
    await message.edit_text("📉 **حساب أوراق الخاسرين**\nاختر لاعب لحساب أوراقه:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("calcpts_"))
async def show_keypad(callback: types.CallbackQuery, state: FSMContext):
    target = callback.data.split("_")[1]
    await render_keypad(callback.message, state, target, 0)

async def render_keypad(message, state, target, current_sum):
    kb = [
        [InlineKeyboardButton(text="1", callback_data=f"k_{target}_{current_sum}_1"), InlineKeyboardButton(text="2", callback_data=f"k_{target}_{current_sum}_2"), InlineKeyboardButton(text="3", callback_data=f"k_{target}_{current_sum}_3")],
        [InlineKeyboardButton(text="4", callback_data=f"k_{target}_{current_sum}_4"), InlineKeyboardButton(text="5", callback_data=f"k_{target}_{current_sum}_5"), InlineKeyboardButton(text="6", callback_data=f"k_{target}_{current_sum}_6")],
        [InlineKeyboardButton(text="7", callback_data=f"k_{target}_{current_sum}_7"), InlineKeyboardButton(text="8", callback_data=f"k_{target}_{current_sum}_8"), InlineKeyboardButton(text="9", callback_data=f"k_{target}_{current_sum}_9")],
        [InlineKeyboardButton(text="0", callback_data=f"k_{target}_{current_sum}_0")],
        [InlineKeyboardButton(text="🔄 تحويل (20)", callback_data=f"k_{target}_{current_sum}_20"), InlineKeyboardButton(text="🚫 منع (20)", callback_data=f"k_{target}_{current_sum}_20"), InlineKeyboardButton(text="➕2 (20)", callback_data=f"k_{target}_{current_sum}_20")],
        [InlineKeyboardButton(text="🌈+4 (50)", callback_data=f"k_{target}_{current_sum}_50"), InlineKeyboardButton(text="🌈+2 (50)", callback_data=f"k_{target}_{current_sum}_50"), InlineKeyboardButton(text="🌈+1 (50)", callback_data=f"k_{target}_{current_sum}_50")],
        [InlineKeyboardButton(text="🧹 إلغاء", callback_data=f"calcpts_{target}"), InlineKeyboardButton(text="✅ تم", callback_data=f"kdone_{target}_{current_sum}")]
    ]
    await message.edit_text(f"🔢 حساب أوراق: **{target}**\nالمجموع الحالي: `{current_sum}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("k_"))
async def update_keypad(callback: types.CallbackQuery, state: FSMContext):
    _, target, cur, val = callback.data.split("_")
    new_sum = int(cur) + int(val)
    await render_keypad(callback.message, state, target, new_sum)

@router.callback_query(F.data.startswith("kdone_"))
async def save_loser_pts(callback: types.CallbackQuery, state: FSMContext):
    _, target, final_val = callback.data.split("_")
    d = (await state.get_data())['calc_data']
    d['temp_round'][target] = int(final_val)
    if target not in d['calculated_losers']: d['calculated_losers'].append(target)
    # نقل المحسوب للأعلى
    d['calculated_losers'].sort(key=lambda x: x == target, reverse=True)
    await state.update_data(calc_data=d)
    await render_loser_list(callback.message, state)

# --- 6. عرض نتائج الجولة وتحديث الجدول ---
@router.callback_query(F.data == "c_finish_round_now")
async def show_round_results(callback: types.CallbackQuery, state: FSMContext):
    d = (await state.get_data())['calc_data']
    total_round = sum(d['temp_round'].values())
    res_text = f"📝 **نتائج الجولة:**\n"
    for p, pts in d['temp_round'].items():
        res_text += f"👤 {p}: +{pts}\n"
        d['scores'][p] += pts
    
    res_text += f"\n🏆 الفائز {d['current_winner']} حصل على مجموع الأوراق!"
    
    # فحص سقف اللعب
    game_over = False
    loser_final = ""
    for p, s in d['scores'].items():
        if s >= d['ceiling']:
            game_over = True
            loser_final = p

    kb = [[InlineKeyboardButton(text="🔄 جولة جديدة", callback_data="c_next_round")]]
    if game_over:
        winner_final = min(d['scores'], key=d['scores'].get)
        res_text += f"\n\n🚨 **انتهت اللعبة!**\nاللاعب {loser_final} كسر السقف.\n🏆 الفائز الكلي: **{winner_final}**"
        kb = [[InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]]
    
    await state.update_data(calc_data=d)
    await callback.message.edit_text(res_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "c_next_round")
async def next_round_trigger(callback: types.CallbackQuery, state: FSMContext):
    await render_main_ui(callback.message, state, "جولة جديدة! بالتوفيق.")
