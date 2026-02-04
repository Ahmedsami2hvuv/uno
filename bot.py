import logging
import json
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- الإعدادات ---
TOKEN = "YOUR_BOT_TOKEN"
CHANNEL_ID = "@YOUR_CHANNEL"  # معرف قناتك (يجب أن يكون البوت مشرفاً فيها)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- قيم الأوراق ---
CARD_VALUES = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "+1": 10, "+2": 20, "+4": 50, "منع": 20, "تحويل": 20, "ملونة": 50
}

# --- إدارة البيانات (الإحصائيات) ---
STATS_FILE = "stats.json"

def load_stats():
    if os.path.exists(STATS_FILE):
        return json.load(STATS_FILE)
    return {"players": {}}

def save_stats(data):
    with open(STATS_FILE, "w") as f:
        json.dump(data, f)

# --- الحالات (States) ---
class GameFlow(StatesGroup):
    waiting_for_names = State()
    waiting_for_limit = State()
    main_game = State()
    confirm_end = State()
    choosing_winner = State()
    scoring_menu = State()  # قائمة اللاعبين لوضع الصح
    entering_cards = State() # شاشة الأزرار (1, 2, +4...)

# --- دالة التحقق من الاشتراك ---
async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- الأوامر الأساسية ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if not await is_subscribed(message.from_user.id):
        return await message.answer(f"❌ يجب عليك الاشتراك في القناة أولاً: {CHANNEL_ID}")
    
    await message.answer("🃏 أهلاً بك في بوت حاسبة أونو!\nأرسل أسماء اللاعبين الآن (مثال: أحمد، علي، سجاد):")
    await state.set_state(GameFlow.waiting_for_names)

@dp.message(GameFlow.waiting_for_names)
async def get_names(message: types.Message, state: FSMContext):
    names = [n.strip() for n in message.text.replace("،", ",").split(",")]
    if len(names) < 2:
        return await message.answer("الرجاء إدخال اسمين على الأقل.")
    
    await state.update_data(players=names, totals={n: 0 for n in names}, history=[])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="150", callback_data="lim_150"),
         InlineKeyboardButton(text="300", callback_data="lim_300"),
         InlineKeyboardButton(text="500", callback_data="lim_500")]
    ])
    await message.answer("اختر الحد الأقصى للنقاط (الرقم اللي نوصله):", reply_markup=kb)
    await state.set_state(GameFlow.waiting_for_limit)

# --- منطق اللعب والاتجاه ---
@dp.callback_query(F.data.startswith("lim_"))
async def set_limit(callback: types.CallbackQuery, state: FSMContext):
    limit = int(callback.data.split("_")[1])
    await state.update_data(limit=limit, direction="clockwise")
    await show_direction(callback.message, "clockwise")
    await state.set_state(GameFlow.main_game)

async def show_direction(message, direction):
    text = "🔄 اتجاه اللعب: " + ("مع عقارب الساعة" if direction == "clockwise" else "عكس عقارب الساعة")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 تحويل الاتجاه", callback_data="toggle")],
        [InlineKeyboardButton(text="🏁 إنهاء الجولة", callback_data="pre_finish")]
    ])
    # ملاحظة: استبدل الرابط بصورة حقيقية لاتجاه اللعب
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "toggle", GameFlow.main_game)
async def toggle_dir(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new_dir = "counter" if data['direction'] == "clockwise" else "clockwise"
    await state.update_data(direction=new_dir)
    await callback.message.delete()
    await show_direction(callback.message, new_dir)

# --- إنهاء الجولة وحساب النقاط ---
@dp.callback_query(F.data == "pre_finish")
async def confirm_finish(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="نعم، إنهاء", callback_data="conf_yes"),
         InlineKeyboardButton(text="لا، إكمال", callback_data="conf_no")]
    ])
    await callback.message.answer("هل أنت متأكد من إنهاء الجولة؟", reply_markup=kb)

@dp.callback_query(F.data == "conf_no")
async def cancel_finish(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.delete()
    await show_direction(callback.message, data['direction'])

@dp.callback_query(F.data == "conf_yes")
async def choose_winner(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=n, callback_data=f"win_{n}")] for n in data['players']
    ])
    await callback.message.edit_text("اختر اللاعب الفائز في هذه الجولة:", reply_markup=kb)
    await state.set_state(GameFlow.choosing_winner)

@dp.callback_query(F.data.startswith("win_"))
async def start_scoring_players(callback: types.CallbackQuery, state: FSMContext):
    winner = callback.data.split("_")[1]
    await state.update_data(current_winner=winner, round_points={n: 0 for n in (await state.get_data())['players']}, finished_players=[])
    await show_scoring_menu(callback.message, state)

async def show_scoring_menu(message, state):
    data = await state.get_data()
    buttons = []
    for n in data['players']:
        if n == data['current_winner']: continue
        status = "✅" if n in data['finished_players'] else "⏳"
        buttons.append([InlineKeyboardButton(text=f"{n} {status}", callback_data=f"scorefor_{n}")])
    
    buttons.append([InlineKeyboardButton(text="تم الحساب 🧮", callback_data="calculate_now")])
    await message.edit_text("اختر اللاعب لإدخال أوراقه:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(GameFlow.scoring_menu)

# --- لوحة الأزرار (أرقام وأوراق) ---
@dp.callback_query(F.data.startswith("scorefor_"))
async def card_input_screen(callback: types.CallbackQuery, state: FSMContext):
    player = callback.data.split("_")[1]
    await state.update_data(editing_player=player, temp_score=0)
    await show_cards_kb(callback.message, player, 0)

async def show_cards_kb(message, player, current_sum):
    kb_layout = [
        ["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["0", "+1", "+2"],
        ["+4", "منع", "تحويل"], ["ملونة", "تم ✅"]
    ]
    buttons = [[InlineKeyboardButton(text=item, callback_data=f"add_{item}") for item in row] for row in kb_layout]
    await message.edit_text(f"إدخال أوراق اللاعب: {player}\nالمجموع الحالي: {current_sum}", 
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await GameFlow.entering_cards.set()

@dp.callback_query(F.data.startswith("add_"))
async def handle_card_click(callback: types.CallbackQuery, state: FSMContext):
    card = callback.data.split("_")[1]
    data = await state.get_data()
    
    if card == "تم ✅":
        finished = data.get('finished_players', [])
        if data['editing_player'] not in finished:
            finished.append(data['editing_player'])
        
        round_pts = data['round_points']
        round_pts[data['editing_player']] = data['temp_score']
        
        await state.update_data(finished_players=finished, round_points=round_pts)
        await show_scoring_menu(callback.message, state)
    else:
        val = CARD_VALUES.get(card, 0)
        new_total = data['temp_score'] + val
        await state.update_data(temp_score=new_total)
        await show_cards_kb(callback.message, data['editing_player'], new_total)

# --- الحساب النهائي ---
@dp.callback_query(F.data == "calculate_now")
async def final_calc(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    # مجموع نقاط الخاسرين يذهب للفائز
    total_round_pts = sum(data['round_points'].values())
    totals = data['totals']
    totals[data['current_winner']] += total_round_pts
    
    await state.update_data(totals=totals)
    
    result_text = "نتائج هذه الجولة:\n"
    for p, s in totals.items():
        result_text += f"{p}: {s} نقطة\n"
        
    # تحقق من الفوز النهائي
    winner_overall = [p for p, s in totals.items() if s >= data['limit']]
    
    if winner_overall:
        await callback.message.answer(f"🏆 اللعبة انتهت! الفائز النهائي هو {winner_overall[0]} بمجموع {totals[winner_overall[0]]}")
        await state.clear()
    else:
        await callback.message.answer(result_text + "\nتبدأ جولة جديدة الآن!")
        await show_direction(callback.message, data['direction'])
        await state.set_state(GameFlow.main_game)

if __name__ == "__main__":
    dp.run_polling(bot)
