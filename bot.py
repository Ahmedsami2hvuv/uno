import os
import time
import random
import asyncio
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- الإعدادات ---
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
DB_URL = os.getenv("DATABASE_URL")
IMG_CW = os.getenv("IMG_CW") 
IMG_CCW = os.getenv("IMG_CCW")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- محرك أوراق الأونو ---
COLORS = ["🔴", "🔵", "🟡", "🟢"]
NUMBERS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
ACTIONS = ["🚫", "🔄", "➕2"]
SPECIALS = ["🌈", "🌈➕4"]

def generate_deck():
    deck = []
    for c in COLORS:
        deck.append(f"{c} 0")
        for n in NUMBERS[1:]:
            deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ACTIONS:
            deck.extend([f"{c} {a}", f"{c} {a}"])
    for s in SPECIALS:
        deck.extend([s] * 4)
    random.shuffle(deck)
    return deck

# --- إدارة قاعدة البيانات ---
def init_db():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT)")
    cur.execute('''CREATE TABLE IF NOT EXISTS players_stats (
                    user_id BIGINT, player_name TEXT, wins INTEGER DEFAULT 0, games INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, player_name))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS games_history (
                    id SERIAL PRIMARY KEY, user_id BIGINT, winner TEXT, duration TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS active_games (
                    game_id SERIAL PRIMARY KEY, p1_id BIGINT, p2_id BIGINT,
                    p1_hand TEXT, p2_hand TEXT, top_card TEXT, deck TEXT,
                    turn BIGINT, status TEXT DEFAULT 'waiting', last_action TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    cur.close()
    conn.close()

def db_query(query, params=(), commit=False, fetch=True):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(query, params)
    res = cur.fetchall() if fetch else None
    if commit: conn.commit()
    cur.close()
    conn.close()
    return res

# --- الحالات (States) ---
class UnoStates(StatesGroup):
    main = State()
    # الحاسبة اليدوية
    calc_adding = State()
    calc_selecting = State()
    calc_limit = State()
    calc_playing = State()
    calc_confirm = State()
    calc_winner = State()
    calc_scoring = State()
    calc_cards = State()
    # الأونلاين
    waiting_match = State()
    playing_online = State()
    # الأدمن
    broadcast = State()

# --- المساعدات ---
async def check_sub(user_id):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in ["member", "administrator", "creator"]
    except: return False

# --- القائمة الرئيسية ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if not await check_sub(message.from_user.id):
        return await message.answer(f"⚠️ اشترك بالقناة أولاً: {CHANNEL_ID}")
    
    db_query("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", 
             (message.from_user.id, message.from_user.username), commit=True, fetch=False)
    
    await state.clear()
    kb = [
        [InlineKeyboardButton(text="🧮 حاسبة أونو (يدوية)", callback_data="mode_calc")],
        [InlineKeyboardButton(text="🎲 لعب عشوائي (أونلاين)", callback_data="mode_random")],
        [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="stats"), InlineKeyboardButton(text="🏆 المتصدرين", callback_data="global")],
        [InlineKeyboardButton(text="⚙️ إدارة اللاعبين", callback_data="manage_p")]
    ]
    if message.from_user.id == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="⚡ لوحة الأدمن", callback_data="admin")])
        
    await message.answer(f"🃏 أهلاً بك {message.from_user.first_name}!\nاختر نظام اللعب:", 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ==========================================
# قسم اللعب العشوائي (Matchmaking)
# ==========================================
@dp.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    # البحث عن لعبة تنتظر
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        game = waiting[0]
        deck = generate_deck()
        p1_h, p2_h = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)]
        top = deck.pop()
        db_query('''UPDATE active_games SET p2_id = %s, p1_hand = %s, p2_hand = %s, 
                   top_card = %s, deck = %s, status = 'playing', turn = p1_id 
                   WHERE game_id = %s''', 
                (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), game['game_id']), commit=True, fetch=False)
        
        await callback.message.edit_text("✅ تم العثور على خصم! بدأت اللعبة.")
        await bot.send_message(game['p1_id'], "✅ وجدنا لك خصماً! دورك أولاً.")
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True, fetch=False)
        await callback.message.edit_text("🔎 جاري البحث عن لاعب... إذا تأخرنا (30ث) سيلعب البوت معك.")
        await asyncio.sleep(30)
        # تشغيل الذكاء الاصطناعي لو ماكو أحد (تبسيط)
        check = db_query("SELECT status FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,))
        if check:
            await callback.message.answer("🤖 لم نجد لاعباً، هل تود اللعب ضد الذكاء الاصطناعي؟ (قيد التطوير)")

# ==========================================
# قسم الحاسبة اليدوية (Old Calculator)
# ==========================================
@dp.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    players = db_query("SELECT player_name FROM players_stats WHERE user_id = %s", (callback.from_user.id,))
    await state.update_data(all_p=[p['player_name'] for p in players], sel_p=[])
    kb = [[InlineKeyboardButton(text=p['player_name'], callback_data=f"csel_{p['player_name']}")] for p in players]
    kb.append([InlineKeyboardButton(text="➕ إضافة لاعب", callback_data="cadd")])
    kb.append([InlineKeyboardButton(text="🚀 بدء", callback_data="cgo")])
    await callback.message.edit_text("اختر لاعبي الحاسبة:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoStates.calc_selecting)

@dp.callback_query(F.data.startswith("csel_"), UnoStates.calc_selecting)
async def csel(c: types.CallbackQuery, state: FSMContext):
    p = c.data.split("_")[1]
    data = await state.get_data()
    sel = data['sel_p']
    if p in sel: sel.remove(p)
    else: sel.append(p)
    await state.update_data(sel_p=sel)
    kb = [[InlineKeyboardButton(text=f"{n} {'✅' if n in sel else ''}", callback_data=f"csel_{n}")] for n in data['all_p']]
    kb.append([InlineKeyboardButton(text="🚀 بدء", callback_data="cgo")])
    await c.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "cadd")
async def cadd_ask(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("أرسل اسم اللاعب:")
    await state.set_state(UnoStates.calc_adding)

@dp.message(UnoStates.calc_adding)
async def cadd_save(m: types.Message, state: FSMContext):
    db_query("INSERT INTO players_stats (user_id, player_name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (m.from_user.id, m.text), commit=True, fetch=False)
    await cmd_start(m, state)

@dp.callback_query(F.data == "cgo", UnoStates.calc_selecting)
async def cgo(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data['sel_p']) < 2: return await c.answer("اختر 2 على الأقل", show_alert=True)
    lims = [100, 150, 200, 250, 300, 400, 500]
    kb = [[InlineKeyboardButton(text=str(x), callback_data=f"clim_{x}")] for x in lims]
    await c.message.edit_text("سقف النقاط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoStates.calc_limit)

@dp.callback_query(F.data.startswith("clim_"), UnoStates.calc_limit)
async def clim(c: types.CallbackQuery, state: FSMContext):
    l = int(c.data.split("_")[1])
    data = await state.get_data()
    await state.update_data(limit=l, totals={p: 0 for p in data['sel_p']}, dir="cw", start_t=time.time())
    await send_calc_dir(c.message, "cw")
    await state.set_state(UnoStates.calc_playing)

async def send_calc_dir(msg, d):
    img = IMG_CW if d == "cw" else IMG_CCW
    txt = "🔄 الاتجاه: " + ("مع الساعة" if d == "cw" else "عكس الساعة")
    kb = [[InlineKeyboardButton(text="🔄 تحويل", callback_data="cswp")], [InlineKeyboardButton(text="🏁 إنهاء جولة", callback_data="cfin")]]
    if img: await msg.answer_photo(img, caption=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else: await msg.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "cswp", UnoStates.calc_playing)
async def cswp(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new = "ccw" if data['dir'] == "cw" else "cw"
    await state.update_data(dir=new)
    await c.message.delete()
    await send_calc_dir(c.message, new)

@dp.callback_query(F.data == "cfin", UnoStates.calc_playing)
async def cfin(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = [[InlineKeyboardButton(text=n, callback_data=f"cwin_{n}")] for n in data['sel_p']]
    await c.message.answer("من الفائز بالجولة؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoStates.calc_winner)

@dp.callback_query(F.data.startswith("cwin_"), UnoStates.calc_winner)
async def cwin(c: types.CallbackQuery, state: FSMContext):
    w = c.data.split("_")[1]
    data = await state.get_data()
    await state.update_data(winner=w, r_scores={p: 0 for p in data['sel_p']}, done=[])
    await show_cscore(c.message, state)

async def show_cscore(msg, state):
    data = await state.get_data()
    kb = [[InlineKeyboardButton(text=f"{p} {'✅' if p in data['done'] else '⏳'}", callback_data=f"cgp_{p}")] for p in data['sel_p'] if p != data['winner']]
    kb.append([InlineKeyboardButton(text="🧮 حساب", callback_data="ccalc")])
    await msg.edit_text("نقاط الخاسرين:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoStates.calc_scoring)

@dp.callback_query(F.data.startswith("cgp_"), UnoStates.calc_scoring)
async def cgp(c: types.CallbackQuery, state: FSMContext):
    p = c.data.split("_")[1]
    await state.update_data(edit=p, temp=0)
    await render_numpad(c.message, p, 0)
    await state.set_state(UnoStates.calc_cards)

async def render_numpad(msg, p, s):
    vals = [["1","2","3"],["4","5","6"],["7","8","9"],["0","+1","+2"],["+4","منع","تحويل"],["ملونة","تم ✅"]]
    kb = [[InlineKeyboardButton(text=i, callback_data=f"cv_{i}") for i in r] for r in vals]
    await msg.edit_text(f"اللاعب: {p} | النقاط: {s}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("cv_"), UnoStates.calc_cards)
async def cv(c: types.CallbackQuery, state: FSMContext):
    v = c.data.split("_")[1]
    data = await state.get_data()
    if v == "تم ✅":
        done, rs = data['done'], data['r_scores']
        if data['edit'] not in done: done.append(data['edit'])
        rs[data['edit']] = data['temp']
        await state.update_data(done=done, r_scores=rs)
        await show_cscore(c.message, state)
    else:
        pts = {"+1":10,"+2":20,"+4":50,"منع":20,"تحويل":20,"ملونة":50}.get(v, int(v) if v.isdigit() else 0)
        new = data['temp'] + pts
        await state.update_data(temp=new)
        await render_numpad(c.message, data['edit'], new)

@dp.callback_query(F.data == "ccalc", UnoStates.calc_scoring)
async def cfinal(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    totals = data['totals']
    totals[data['winner']] += sum(data['r_scores'].values())
    await state.update_data(totals=totals)
    
    over = [p for p, s in totals.items() if s >= data['limit']]
    if over:
        win = over[0]
        dur = int(time.time() - data['start_t'])
        dur_s = f"{dur//60}د و {dur%60}ث"
        db_query("UPDATE players_stats SET wins = wins + 1 WHERE user_id = %s AND player_name = %s", (c.from_user.id, win), commit=True, fetch=False)
        db_query("INSERT INTO games_history (user_id, winner, duration) VALUES (%s, %s, %s)", (c.from_user.id, win, dur_s), commit=True, fetch=False)
        
        res = "\n".join([f"▫️ {p}: {s}" for p, s in totals.items()])
        msg = f"🏆 الفائز: {win}\n⏱️ المدة: {dur_s}\n\n📊 النتائج:\n{res}\n\nتعال العب @Unocalculator1bot\nمطور البوت https://t.me/m/_zZ653YLY2Ey"
        await c.message.answer(msg)
        await cmd_start(c.message, state)
    else:
        await c.message.answer("جولة انتهت! المستمرون:\n" + "\n".join([f"{p}: {s}" for p, s in totals.items()]))
        await send_calc_dir(c.message, data['dir'])
        await state.set_state(UnoStates.calc_playing)

# ==========================================
# قسم الإحصائيات والأدمن
# ==========================================
@dp.callback_query(F.data == "stats")
async def show_st(c: types.CallbackQuery):
    stats = db_query("SELECT * FROM players_stats WHERE user_id = %s ORDER BY wins DESC", (c.from_user.id,))
    txt = "📊 إحصائياتك:\n\n" + "\n".join([f"👤 {s['player_name']}: {s['wins']} فوز" for s in stats])
    await c.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 عودة", callback_data="home")]]))

@dp.callback_query(F.data == "global")
async def show_gl(c: types.CallbackQuery):
    gl = db_query("SELECT player_name, wins FROM players_stats ORDER BY wins DESC LIMIT 10")
    txt = "🏆 المتصدرين عالمياً:\n\n" + "\n".join([f"{i+1}. {s['player_name']} - {s['wins']}" for i, s in enumerate(gl)])
    await c.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 عودة", callback_data="home")]]))

@dp.callback_query(F.data == "admin")
async def adm_p(c: types.CallbackQuery):
    if c.from_user.id != ADMIN_ID: return
    count = db_query("SELECT COUNT(*) FROM users")[0]['count']
    await c.message.edit_text(f"الأدمن\nالمستخدمين: {count}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 إذاعة", callback_data="bc")]]))

@dp.callback_query(F.data == "bc")
async def bc_ask(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("أرسل رسالة الإذاعة:")
    await state.set_state(UnoStates.broadcast)

@dp.message(UnoStates.broadcast)
async def bc_do(m: types.Message, state: FSMContext):
    users = db_query("SELECT user_id FROM users")
    for u in users:
        try: await bot.send_message(u['user_id'], m.text)
        except: continue
    await m.answer("تمت الإذاعة")
    await cmd_start(m, state)

@dp.callback_query(F.data == "home")
async def go_h(c: types.CallbackQuery, state: FSMContext):
    await cmd_start(c.message, state)

if __name__ == "__main__":
    init_db()
    asyncio.run(dp.start_polling(bot))
