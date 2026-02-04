import os
import psycopg2
from psycopg2.extras import RealDictCursor
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- الإعدادات من ريلوي ---
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
DB_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- قيم أوراق الأونو ---
CARD_VALUES = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "+1": 10, "+2": 20, "+4": 50, "منع": 20, "تحويل": 20, "ملونة": 50
}

# --- إدارة قاعدة البيانات ---
def init_db():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS players_stats (
                    player_name TEXT PRIMARY KEY,
                    wins INTEGER DEFAULT 0,
                    games INTEGER DEFAULT 0)''')
    conn.commit()
    cur.close()
    conn.close()

def get_all_players_from_db():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT player_name FROM players_stats")
    players = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return players

def update_db_stats(name, is_win=False):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    if is_win:
        cur.execute('''INSERT INTO players_stats (player_name, wins, games) VALUES (%s, 1, 1)
                       ON CONFLICT (player_name) DO UPDATE SET wins = players_stats.wins + 1, games = players_stats.games + 1''', (name,))
    else:
        cur.execute('''INSERT INTO players_stats (player_name, wins, games) VALUES (%s, 0, 1)
                       ON CONFLICT (player_name) DO UPDATE SET games = players_stats.games + 1''', (name,))
    conn.commit()
    cur.close()
    conn.close()

# --- الحالات (FSM) ---
class UnoGame(StatesGroup):
    selecting_players = State()
    adding_player = State()
    setting_limit = State()
    playing = State()
    confirm_finish = State()
    choosing_winner = State()
    scoring_menu = State()
    entering_cards = State()

# --- دالة التحقق من الاشتراك ---
async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# --- أوامر البوت ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if not await check_sub(message.from_user.id):
        return await message.answer(f"⚠️ اشترك بالقناة أولاً: {CHANNEL_ID}")

    all_p = get_all_players_from_db()
    await state.update_data(all_players=all_p, selected_players=[])
    
    kb = [[InlineKeyboardButton(text=p, callback_data=f"sel_{p}")] for p in all_p]
    kb.append([InlineKeyboardButton(text="➕ إضافة لاعب جديد", callback_data="new_p")])
    kb.append([InlineKeyboardButton(text="🚀 بدء اللعبة", callback_data="go_limit")])
    
    await message.answer("🃏 اختر اللاعبين أو أضف جديداً:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.selecting_players)

@dp.callback_query(F.data.startswith("sel_"), UnoGame.selecting_players)
async def toggle_player(callback: types.CallbackQuery, state: FSMContext):
    p = callback.data.split("_")[1]
    data = await state.get_data()
    sel = data['selected_players']
    if p in sel: sel.remove(p)
    else: sel.append(p)
    await state.update_data(selected_players=sel)
    
    kb = [[InlineKeyboardButton(text=f"{name} {'✅' if name in sel else ''}", callback_data=f"sel_{name}")] for name in data['all_players']]
    kb.append([InlineKeyboardButton(text="➕ إضافة لاعب جديد", callback_data="new_p")])
    kb.append([InlineKeyboardButton(text="🚀 بدء اللعبة", callback_data="go_limit")])
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "new_p", UnoGame.selecting_players)
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("أرسل اسم اللاعب الجديد:")
    await state.set_state(UnoGame.adding_player)

@dp.message(UnoGame.adding_player)
async def save_new_p(message: types.Message, state: FSMContext):
    name = message.text.strip()
    update_db_stats(name, is_win=False) # إضافة للقاعدة بـ 0 لعبات حالياً
    await message.answer(f"تمت إضافة {name}")
    await cmd_start(message, state)

@dp.callback_query(F.data == "go_limit", UnoGame.selecting_players)
async def set_limit(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data['selected_players']) < 2: return await callback.answer("اختر 2 على الأقل!", show_alert=True)
    
    kb = [[InlineKeyboardButton(text=str(x), callback_data=f"lim_{x}")] for x in [150, 300, 500]]
    await callback.message.answer("اختر سقف النقاط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.setting_limit)

@dp.callback_query(F.data.startswith("lim_"), UnoGame.setting_limit)
async def start_game(callback: types.CallbackQuery, state: FSMContext):
    limit = int(callback.data.split("_")[1])
    data = await state.get_data()
    for p in data['selected_players']: update_db_stats(p) # تسجيل دخول اللعبة
    await state.update_data(limit=limit, totals={p: 0 for p in data['selected_players']}, direction="clockwise")
    await send_dir(callback.message, "clockwise")
    await state.set_state(UnoGame.playing)

async def send_dir(message, d):
    txt = "🔄 الاتجاه: " + ("مع الساعة" if d == "clockwise" else "عكس الساعة")
    kb = [[InlineKeyboardButton(text="🔄 تحويل", callback_data="swap")], [InlineKeyboardButton(text="🏁 إنهاء", callback_data="finish")]]
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "swap", UnoGame.playing)
async def swap_dir(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new = "counter" if data['direction'] == "clockwise" else "clockwise"
    await state.update_data(direction=new)
    await callback.message.delete()
    await send_dir(callback.message, new)

@dp.callback_query(F.data == "finish", UnoGame.playing)
async def confirm(callback: types.CallbackQuery):
    kb = [[InlineKeyboardButton(text="نعم", callback_data="y"), InlineKeyboardButton(text="لا", callback_data="n")]]
    await callback.message.answer("متأكد؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await UnoGame.confirm_finish.set()

@dp.callback_query(F.data == "n", UnoGame.confirm_finish)
async def cancel(callback: types.CallbackQuery, state: FSMContext):
    d = (await state.get_data())['direction']
    await callback.message.delete()
    await send_dir(callback.message, d)
    await state.set_state(UnoGame.playing)

@dp.callback_query(F.data == "y", UnoGame.confirm_finish)
async def win_pick(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = [[InlineKeyboardButton(text=n, callback_data=f"w_{n}")] for n in data['selected_players']]
    await callback.message.edit_text("من الفائز؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.choosing_winner)

@dp.callback_query(F.data.startswith("w_"), UnoGame.choosing_winner)
async def scoring_m(callback: types.CallbackQuery, state: FSMContext):
    win = callback.data.split("_")[1]
    data = await state.get_data()
    await state.update_data(winner=win, round_p={p: 0 for p in data['selected_players']}, done_p=[])
    await show_menu(callback.message, state)

async def show_menu(msg, state):
    data = await state.get_data()
    kb = [[InlineKeyboardButton(text=f"{p} {'✅' if p in data['done_p'] else '⏳'}", callback_data=f"get_{p}")] 
          for p in data['selected_players'] if p != data['winner']]
    kb.append([InlineKeyboardButton(text="🧮 حساب نهائي", callback_data="calc")])
    await msg.edit_text("أدخل نقاط الخاسرين:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.scoring_menu)

@dp.callback_query(F.data.startswith("get_"), UnoGame.scoring_menu)
async def cards_kb(callback: types.CallbackQuery, state: FSMContext):
    p = callback.data.split("_")[1]
    await state.update_data(edit_p=p, temp=0)
    await render_kb(callback.message, p, 0)

async def render_kb(msg, p, s):
    lay = [["1","2","3"],["4","5","6"],["7","8","9"],["0","+1","+2"],["+4","منع","تحويل"],["ملونة","تم ✅"]]
    kb = [[InlineKeyboardButton(text=i, callback_data=f"a_{i}") for i in r] for r in lay]
    await msg.edit_text(f"اللاعب: {p} | النقاط: {s}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.entering_cards)

@dp.callback_query(F.data.startswith("a_"), UnoGame.entering_cards)
async def add_c(callback: types.CallbackQuery, state: FSMContext):
    v = callback.data.split("_")[1]
    data = await state.get_data()
    if v == "تم ✅":
        done = data['done_p']
        if data['edit_p'] not in done: done.append(data['edit_p'])
        rp = data['round_p']
        rp[data['edit_p']] = data['temp']
        await state.update_data(done_p=done, round_p=rp)
        await show_menu(callback.message, state)
    else:
        new = data['temp'] + CARD_VALUES.get(v, 0)
        await state.update_data(temp=new)
        await render_kb(callback.message, data['edit_p'], new)

@dp.callback_query(F.data == "calc", UnoGame.scoring_menu)
async def finish_round(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    totals = data['totals']
    totals[data['winner']] += sum(data['round_p'].values())
    await state.update_data(totals=totals)
    
    res = "\n".join([f"{p}: {s}" for p, s in totals.items()])
    win_all = [p for p, s in totals.items() if s >= data['limit']]
    
    if win_all:
        update_db_stats(win_all[0], is_win=True)
        await callback.message.answer(f"🏆 الفائز النهائي: {win_all[0]}\n{res}")
        await state.clear()
    else:
        await callback.message.answer(f"📊 النتائج:\n{res}\nجولة جديدة!")
        await send_dir(callback.message, data['direction'])
        await state.set_state(UnoGame.playing)

if __name__ == "__main__":
    import asyncio
    init_db()
    asyncio.run(dp.start_polling(bot))
