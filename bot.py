import logging
import json
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- جلب الإعدادات من متغيرات البيئة (Railway) ---
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0)) # تحويل الأيدي إلى رقم

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- قيم النقاط ---
CARD_VALUES = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "+1": 10, "+2": 20, "+4": 50, "منع": 20, "تحويل": 20, "ملونة": 50
}

STATS_FILE = "stats_data.json"

def load_data():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"players_stats": {}}

def save_data(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

class UnoGame(StatesGroup):
    selecting_players = State()
    adding_new_player = State()
    setting_limit = State()
    playing = State()
    confirm_finish = State()
    choosing_winner = State()
    scoring_menu = State()
    entering_cards = State()

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- لوحة الإدارة (مستقبلاً) ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ هذا الأمر للمطور فقط.")
    await message.answer("🛠 لوحة الإدارة:\nيمكنك هنا إضافة ميزات مثل تصفير الإحصائيات أو إرسال إذاعة.")

# --- الأوامر الأساسية ونظام اللعب ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if not await check_sub(message.from_user.id):
        return await message.answer(f"⚠️ يجب الاشتراك بالقناة أولاً: {CHANNEL_ID}")

    data = load_data()
    all_players = list(data["players_stats"].keys())
    
    kb = [[InlineKeyboardButton(text=f"{p} {'✅' if p in (await state.get_data()).get('selected_players', []) else ''}", 
                                  callback_data=f"select_{p}")] for p in all_players]
    kb.append([InlineKeyboardButton(text="➕ إضافة لاعب جديد", callback_data="add_new")])
    kb.append([InlineKeyboardButton(text="🚀 بدء اللعبة", callback_data="start_game_setup")])
    
    await state.update_data(all_players=all_players)
    if 'selected_players' not in (await state.get_data()):
        await state.update_data(selected_players=[])
        
    await message.answer("🎴 اختر اللاعبين المشاركين:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.selecting_players)

@dp.callback_query(F.data.startswith("select_"), UnoGame.selecting_players)
async def select_player(callback: types.CallbackQuery, state: FSMContext):
    player = callback.data.split("_")[1]
    data = await state.get_data()
    selected = data['selected_players']
    if player in selected: selected.remove(player)
    else: selected.append(player)
    
    await state.update_data(selected_players=selected)
    kb = [[InlineKeyboardButton(text=f"{p} {'✅' if p in selected else ''}", callback_data=f"select_{p}")] for p in data['all_players']]
    kb.append([InlineKeyboardButton(text="➕ إضافة لاعب جديد", callback_data="add_new")])
    kb.append([InlineKeyboardButton(text="🚀 بدء اللعبة", callback_data="start_game_setup")])
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "add_new", UnoGame.selecting_players)
async def ask_new_player(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("أرسل اسم اللاعب الجديد:")
    await state.set_state(UnoGame.adding_new_player)

@dp.message(UnoGame.adding_new_player)
async def process_new_player(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    data = load_data()
    if new_name not in data["players_stats"]:
        data["players_stats"][new_name] = {"wins": 0, "games": 0}
        save_data(data)
    await message.answer(f"تمت إضافة {new_name}!")
    await cmd_start(message, state)

@dp.callback_query(F.data == "start_game_setup", UnoGame.selecting_players)
async def setup_limit(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data['selected_players']) < 2:
        return await callback.answer("اختر لاعبين اثنين على الأقل!", show_alert=True)
    
    kb = [[InlineKeyboardButton(text=str(limit), callback_data=f"set_{limit}")] for limit in [150, 300, 500]]
    await callback.message.answer("اختر سقف النقاط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.setting_limit)

@dp.callback_query(F.data.startswith("set_"), UnoGame.setting_limit)
async def start_playing(callback: types.CallbackQuery, state: FSMContext):
    limit = int(callback.data.split("_")[1])
    data = await state.get_data()
    stats = load_data()
    for p in data['selected_players']:
        stats["players_stats"][p]["games"] += 1
    save_data(stats)
    await state.update_data(limit=limit, totals={p: 0 for p in data['selected_players']}, direction="clockwise")
    await send_direction(callback.message, "clockwise")
    await state.set_state(UnoGame.playing)

async def send_direction(message, direction):
    text = "🔄 اتجاه اللعب: " + ("مع عقارب الساعة" if direction == "clockwise" else "عكس عقارب الساعة")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 تحويل الاتجاه", callback_data="toggle_dir")],
        [InlineKeyboardButton(text="🏁 إنهاء الجولة", callback_data="pre_finish")]
    ])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "toggle_dir", UnoGame.playing)
async def toggle_dir(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new_dir = "counter" if data['direction'] == "clockwise" else "clockwise"
    await state.update_data(direction=new_dir)
    await callback.message.delete()
    await send_direction(callback.message, new_dir)

@dp.callback_query(F.data == "pre_finish", UnoGame.playing)
async def pre_finish(callback: types.CallbackQuery):
    kb = [[InlineKeyboardButton(text="✅ نعم", callback_data="confirm_yes"), InlineKeyboardButton(text="❌ لا", callback_data="confirm_no")]]
    await callback.message.answer("متأكد من إنهاء الجولة؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await UnoGame.confirm_finish.set()

@dp.callback_query(F.data == "confirm_no", UnoGame.confirm_finish)
async def cancel_finish(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.delete()
    await send_direction(callback.message, data['direction'])
    await state.set_state(UnoGame.playing)

@dp.callback_query(F.data == "confirm_yes", UnoGame.confirm_finish)
async def choose_winner(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = [[InlineKeyboardButton(text=n, callback_data=f"win_{n}")] for n in data['selected_players']]
    await callback.message.edit_text("اختر الفائز بالجولة:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.choosing_winner)

@dp.callback_query(F.data.startswith("win_"), UnoGame.choosing_winner)
async def start_scoring(callback: types.CallbackQuery, state: FSMContext):
    winner = callback.data.split("_")[1]
    data = await state.get_data()
    await state.update_data(current_winner=winner, round_points={p: 0 for p in data['selected_players']}, finished_players=[])
    await show_scoring_menu(callback.message, state)

async def show_scoring_menu(message, state):
    data = await state.get_data()
    kb = [[InlineKeyboardButton(text=f"{p} {'✅' if p in data['finished_players'] else '⏳'}", callback_data=f"scorefor_{p}")] 
          for p in data['selected_players'] if p != data['current_winner']]
    kb.append([InlineKeyboardButton(text="🧮 تم الحساب", callback_data="final_calc_round")])
    await message.edit_text("إدخال النقاط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.scoring_menu)

@dp.callback_query(F.data.startswith("scorefor_"), UnoGame.scoring_menu)
async def show_cards_input(callback: types.CallbackQuery, state: FSMContext):
    player = callback.data.split("_")[1]
    await state.update_data(editing_player=player, temp_score=0)
    await render_cards_kb(callback.message, player, 0)

async def render_cards_kb(message, player, current_sum):
    layout = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["0", "+1", "+2"], ["+4", "منع", "تحويل"], ["ملونة", "تم ✅"]]
    kb = [[InlineKeyboardButton(text=item, callback_data=f"add_{item}") for item in row] for row in layout]
    await message.edit_text(f"اللاعب: {player} | النقاط: {current_sum}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.entering_cards)

@dp.callback_query(F.data.startswith("add_"), UnoGame.entering_cards)
async def handle_card_click(callback: types.CallbackQuery, state: FSMContext):
    val_key = callback.data.split("_")[1]
    data = await state.get_data()
    if val_key == "تم ✅":
        finished = data['finished_players']
        if data['editing_player'] not in finished: finished.append(data['editing_player'])
        round_pts = data['round_points']
        round_pts[data['editing_player']] = data['temp_score']
        await state.update_data(finished_players=finished, round_points=round_pts)
        await show_scoring_menu(callback.message, state)
    else:
        new_total = data['temp_score'] + CARD_VALUES.get(val_key, 0)
        await state.update_data(temp_score=new_total)
        await render_cards_kb(callback.message, data['editing_player'], new_total)

@dp.callback_query(F.data == "final_calc_round", UnoGame.scoring_menu)
async def final_calc(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    totals = data['totals']
    totals[data['current_winner']] += sum(data['round_points'].values())
    await state.update_data(totals=totals)
    
    res = "📊 النتائج:\n" + "\n".join([f"- {p}: {s}" for p, s in totals.items()])
    winner_overall = [p for p, s in totals.items() if s >= data['limit']]
    
    if winner_overall:
        stats = load_data()
        stats["players_stats"][winner_overall[0]]["wins"] += 1
        save_data(stats)
        await callback.message.answer(f"🏆 الفائز النهائي: {winner_overall[0]}\n{res}")
        await state.clear()
    else:
        await callback.message.answer(res + "\nجولة جديدة!")
        await send_direction(callback.message, data['direction'])
        await state.set_state(UnoGame.playing)

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    data = load_data()
    res = "📈 الإحصائيات:\n" + "\n".join([f"👤 {p}: فاز {s['wins']} | لعب {s['games']}" for p, s in data["players_stats"].items()])
    await message.answer(res)

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
