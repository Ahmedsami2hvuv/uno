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
def get_saved_players():
    # جلب الأسامي من الداتا بيس
    res = db_query("SELECT player_name FROM calc_players")
    return [r['player_name'] for r in res] if res else []

def save_player_to_db(name):
    # حفظ الاسم في الداتا بيس
    db_query("INSERT INTO calc_players (player_name) VALUES (%s) ON CONFLICT (player_name) DO NOTHING", (name,), commit=True)

def delete_player_from_db(name):
    db_query("DELETE FROM calc_players WHERE player_name = %s", (name,), commit=True)

# --- واجهة إدارة اللاعبين ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    saved_p = get_saved_players() # جلب المحفوظين
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
    # عرض كل الأسامي المخزونة بالداتا بيس
    for p in d.get("all_players", []):
        is_sel = "✅ " if p in d["selected"] else "▫️ "
        kb.append([
            InlineKeyboardButton(text=f"{is_sel}{p}", callback_data=f"sel_{p}"),
            InlineKeyboardButton(text="🗑️ مسح من الذاكرة", callback_data=f"delp_{p}")
        ])
    
    kb.append([InlineKeyboardButton(text="➕ إضافة لاعب جديد", callback_data="add_p_new")])
    if len(d.get("selected", [])) >= 2:
        kb.append([InlineKeyboardButton(text="➡️ استمرار (ضبط السقف)", callback_data="go_ceiling")])
    kb.append([InlineKeyboardButton(text="🏠 الرئيسية", callback_data="home")])
    
    text = "👥 **ذاكرة لاعبي الحاسبة**\nالأسامي هنا تُحفظ دائماً وتظهر في الإحصائيات:"
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
    save_player_to_db(name) # حفظ بالداتا بيس
    d = (await state.get_data())['calc_data']
    d['all_players'] = get_saved_players() # تحديث القائمة
    if name not in d["selected"]: d["selected"].append(name)
    await state.update_data(calc_data=d)
    await state.set_state(None)
    await render_player_manager(message, state)

@router.callback_query(F.data.startswith("delp_"))
async def del_p(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split("_")[1]
    delete_player_from_db(name) # مسح من الداتا بيس
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

# --- الكيبورد المعدل بدقة (كما طلبت) ---
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
    await message.edit_text(f"🔢 حساب أوراق: **{target}**\nالمجموع: `{cur_sum}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- تحديث الصورة بدون إعادة إرسال (حل مشكلة التحميل) ---
async def render_main_ui(message, state, extra=""):
    d = (await state.get_data())['calc_data']
    img_url = IMG_CW if d['direction'] == "CW" else IMG_CCW
    table = f"🏆 **السقف: {d['ceiling']}**\n━━━━━━━━━━━━━━\n"
    for p, s in d['scores'].items(): table += f"👤 {p}: `{s}`\n"
    table += "━━━━━━━━━━━━━━\n"
    table += f"🔄 الاتجاه: {'مع العقارب' if d['direction'] == 'CW' else 'عكس العقارب'}"
    if extra: table += f"\n\n📢 {extra}"
    
    kb = [[InlineKeyboardButton(text="🔄 تغيير الاتجاه", callback_data="c_dir"), InlineKeyboardButton(text="🔔 إنهاء الجولة", callback_data="c_end_round")]]
    
    # إذا كانت الرسالة نصية نرسل صورة، إذا كانت صورة نحدثها
    if message.photo:
        await message.edit_media(media=InputMediaPhoto(media=img_url, caption=table), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await bot.send_photo(message.chat.id, photo=img_url, caption=table, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await message.delete()

# (ملاحظة: باقي الدوال win_, c_finish_round_now, الخ.. تبقى كما هي في الكود السابق مع التأكد من إضافة نقاط الفائز)
