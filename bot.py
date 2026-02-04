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
IMG_CW = os.getenv("IMG_CW") 
IMG_CCW = os.getenv("IMG_CCW")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CARD_VALUES = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "+1": 10, "+2": 20, "+4": 50, "منع": 20, "تحويل": 20, "ملونة": 50
}

# --- إدارة قاعدة البيانات (تحديث لدعم خصوصية المستخدم) ---
def init_db():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    # أضفنا user_id ليكون المفتاح الأساسي مشتركاً مع اسم اللاعب
    cur.execute('''CREATE TABLE IF NOT EXISTS players_stats (
                    user_id BIGINT,
                    player_name TEXT,
                    wins INTEGER DEFAULT 0,
                    games INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, player_name))''')
    conn.commit()
    cur.close()
    conn.close()

def get_players_by_user(user_id):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT player_name FROM players_stats WHERE user_id = %s", (user_id,))
    players = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return players

def update_db_stats(user_id, name, is_win=False):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    if is_win:
        cur.execute('''INSERT INTO players_stats (user_id, player_name, wins, games) VALUES (%s, %s, 1, 1)
                       ON CONFLICT (user_id, player_name) DO UPDATE SET wins = players_stats.wins + 1, games = players_stats.games + 1''', (user_id, name))
    else:
        cur.execute('''INSERT INTO players_stats (user_id, player_name, wins, games) VALUES (%s, %s, 0, 1)
                       ON CONFLICT (user_id, player_name) DO UPDATE SET games = players_stats.games + 1''', (user_id, name))
    conn.commit()
    cur.close()
    conn.close()

def get_user_stats(user_id):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM players_stats WHERE user_id = %s ORDER BY wins DESC", (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# --- الحالات ---
class UnoGame(StatesGroup):
    main_menu = State()
    selecting_players = State()
    adding_player = State()
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
    except: return False

# --- القائمة الرئيسية ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    if not await check_sub(message.from_user.id):
        return await message.answer(f"⚠️ اشترك بالقناة أولاً: {CHANNEL_ID}")

    await state.clear()
    kb = [
        [InlineKeyboardButton(text="🎮 بدء لعبة جديدة", callback_data="start_new_game")],
        [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="view_stats")],
        [InlineKeyboardButton(text="➕ إضافة لاعب جديد", callback_data="new_p_menu")]
    ]
    await message.answer("🃏 مرحباً بك في حاسبة أونو!\nاختر ما تريد القيام به:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- التعامل مع الإحصائيات ---
@dp.callback_query(F.data == "view_stats")
async def show_stats(callback: types.CallbackQuery):
    stats = get_user_stats(callback.from_user.id)
    if not stats:
        return await callback.answer("لا يوجد لاعبون مسجلون لديك بعد.", show_alert=True)
    
    txt = "📊 إحصائيات لاعبيك:\n\n"
    for s in stats:
        txt += f"👤 {s['player_name']}: فوز ({s['wins']}) | لعب ({s['games']})\n"
    
    kb = [[InlineKeyboardButton(text="🔙 العودة", callback_data="back_to_main")]]
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "back_to_main")
async def back_main(callback: types.CallbackQuery, state: FSMContext):
    await cmd_start(callback.message, state)

# --- بدء اللعبة واختيار اللاعبين ---
@dp.callback_query(F.data == "start_new_game")
async def start_select(callback: types.CallbackQuery, state: FSMContext):
    all_p = get_players_by_user(callback.from_user.id)
    await state.update_data(all_players=all_p, selected_players=[])
    
    kb = [[InlineKeyboardButton(text=p, callback_data=f"sel_{p}")] for p in all_p]
    kb.append([InlineKeyboardButton(text="🚀 بدء تحديد النقاط", callback_data="go_limit")])
    kb.append([InlineKeyboardButton(text="🔙 العودة", callback_data="back_to_main")])
    
    await callback.message.edit_text("اختر اللاعبين المشاركين في هذه اللعبة:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.selecting_players)

@dp.callback_query(F.data.startswith("sel_"), UnoGame.selecting_players)
async def toggle_player(callback: types.CallbackQuery, state: FSMContext):
    p = callback.data.split("_")[1]
    data = await state.get_data()
    sel = data.get('selected_players', [])
    if p in sel: sel.remove(p)
    else: sel.append(p)
    await state.update_data(selected_players=sel)
    
    kb = [[InlineKeyboardButton(text=f"{name} {'✅' if name in sel else ''}", callback_data=f"sel_{name}")] for name in data['all_players']]
    kb.append([InlineKeyboardButton(text="🚀 بدء تحديد النقاط", callback_data="go_limit")])
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "new_p_menu")
async def ask_name_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("أرسل اسم اللاعب الجديد ليتم حفظه في قائمتك:")
    await state.set_state(UnoGame.adding_player)

@dp.message(UnoGame.adding_player)
async def save_new_p(message: types.Message, state: FSMContext):
    name = message.text.strip()
    # حفظ اللاعب مع user_id الخاص بالمستخدم
    update_db_stats(message.from_user.id, name)
    await message.answer(f"تمت إضافة {name} لقائمة لاعبيك بنجاح!")
    await cmd_start(message, state)

# --- بقية منطق اللعب (النهاية، التحويل، الحساب) كما في الكود السابق مع تعديل الـ user_id ---
# سأقوم بدمجها هنا للتأكد من أن كل شيء يعمل مع الـ user_id الجديد

@dp.callback_query(F.data == "go_limit", UnoGame.selecting_players)
async def set_limit(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data.get('selected_players', [])) < 2: 
        return await callback.answer("يجب اختيار لاعبين اثنين على الأقل!", show_alert=True)
    
    kb = [[InlineKeyboardButton(text=str(x), callback_data=f"lim_{x}")] for x in [150, 300, 500]]
    await callback.message.answer("اختر سقف النقاط لهذه اللعبة:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.setting_limit)

@dp.callback_query(F.data.startswith("lim_"), UnoGame.setting_limit)
async def start_game_logic(callback: types.CallbackQuery, state: FSMContext):
    limit = int(callback.data.split("_")[1])
    data = await state.get_data()
    for p in data['selected_players']: 
        update_db_stats(callback.from_user.id, p) # تسجيل دخول الجولة
    await state.update_data(limit=limit, totals={p: 0 for p in data['selected_players']}, direction="clockwise")
    await send_dir(callback.message, "clockwise")
    await state.set_state(UnoGame.playing)

async def send_dir(message, d):
    txt = "🔄 الاتجاه الحالي: " + ("مع عقارب الساعة" if d == "clockwise" else "عكس عقارب الساعة")
    img = IMG_CLOCKWISE if d == "clockwise" else IMG_CCW
    kb = [[InlineKeyboardButton(text="🔄 تحويل الاتجاه", callback_data="swap")], [InlineKeyboardButton(text="🏁 إنهاء الجولة", callback_data="finish")]]
    if img:
        await message.answer_photo(photo=img, caption=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "swap", UnoGame.playing)
async def swap_dir(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new = "counter" if data['direction'] == "clockwise" else "clockwise"
    await state.update_data(direction=new)
    await callback.message.delete()
    await send_dir(callback.message, new)

@dp.callback_query(F.data == "finish", UnoGame.playing)
async def confirm_round_end(callback: types.CallbackQuery, state: FSMContext):
    kb = [[InlineKeyboardButton(text="✅ نعم", callback_data="confirm_y"), InlineKeyboardButton(text="❌ لا", callback_data="confirm_n")]]
    await callback.message.answer("هل أنت متأكد من إنهاء هذه الجولة؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.confirm_finish)

@dp.callback_query(F.data == "confirm_n", UnoGame.confirm_finish)
async def cancel_f(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.delete()
    await send_dir(callback.message, data['direction'])
    await state.set_state(UnoGame.playing)

@dp.callback_query(F.data == "confirm_y", UnoGame.confirm_finish)
async def win_pick(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = [[InlineKeyboardButton(text=n, callback_data=f"w_{n}")] for n in data['selected_players']]
    await callback.message.edit_text("من هو اللاعب الفائز في هذه الجولة؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.choosing_winner)

@dp.callback_query(F.data.startswith("w_"), UnoGame.choosing_winner)
async def scoring_m(callback: types.CallbackQuery, state: FSMContext):
    win = callback.data.split("_")[1]
    data = await state.get_data()
    await state.update_data(winner=win, round_p={p: 0 for p in data['selected_players']}, done_p=[])
    await show_scoring_menu(callback.message, state)

async def show_scoring_menu(msg, state):
    data = await state.get_data()
    kb = [[InlineKeyboardButton(text=f"{p} {'✅' if p in data['done_p'] else '⏳'}", callback_data=f"get_{p}")] 
          for p in data['selected_players'] if p != data['winner']]
    kb.append([InlineKeyboardButton(text="🧮 حساب نقاط الجولة", callback_data="calc_final")])
    await msg.edit_text("اختر اللاعب لإدخال أوراقه المتبقية:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.scoring_menu)

@dp.callback_query(F.data.startswith("get_"), UnoGame.scoring_menu)
async def cards_kb(callback: types.CallbackQuery, state: FSMContext):
    p = callback.data.split("_")[1]
    await state.update_data(edit_p=p, temp=0)
    await render_cards_kb(callback.message, p, 0, state)

async def render_cards_kb(msg, p, s, state):
    lay = [["1","2","3"],["4","5","6"],["7","8","9"],["0","+1","+2"],["+4","منع","تحويل"],["ملونة","تم ✅"]]
    kb = [[InlineKeyboardButton(text=i, callback_data=f"a_{i}") for i in r] for r in lay]
    await msg.edit_text(f"اللاعب: {p}\nمجموع النقاط الحالي: {s}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(UnoGame.entering_cards)

@dp.callback_query(F.data.startswith("a_"), UnoGame.entering_cards)
async def add_card_val(callback: types.CallbackQuery, state: FSMContext):
    v = callback.data.split("_")[1]
    data = await state.get_data()
    if v == "تم ✅":
        done = data['done_p']
        if data['edit_p'] not in done: done.append(data['edit_p'])
        rp = data['round_p']
        rp[data['edit_p']] = data['temp']
        await state.update_data(done_p=done, round_p=rp)
        await show_scoring_menu(callback.message, state)
    else:
        new_val = data['temp'] + CARD_VALUES.get(v, 0)
        await state.update_data(temp=new_val)
        await render_cards_kb(callback.message, data['edit_p'], new_val, state)

@dp.callback_query(F.data == "calc_final", UnoGame.scoring_menu)
async def finish_round_and_calc(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    totals = data['totals']
    # الفائز يأخذ مجموع نقاط كل الخاسرين
    round_sum = sum(data['round_p'].values())
    totals[data['winner']] += round_sum
    await state.update_data(totals=totals)
    
    res_txt = "📊 نتائج اللاعبين التراكمية:\n"
    for p, s in totals.items():
        res_txt += f"- {p}: {s} نقطة\n"
    
    win_all = [p for p, s in totals.items() if s >= data['limit']]
    
    if win_all:
        winner_name = win_all[0]
        update_db_stats(callback.from_user.id, winner_name, is_win=True)
        await callback.message.answer(f"🏆 انتهت اللعبة!\nالفائز النهائي هو {winner_name} بمجموع {totals[winner_name]} نقطة!\n\n{res_txt}")
        await cmd_start(callback.message, state) # العودة للقائمة الرئيسية
    else:
        await callback.message.answer(f"📊 جولة انتهت!\n{res_txt}\nالجولة القادمة تبدأ الآن...")
        await send_dir(callback.message, data['direction'])
        await state.set_state(UnoGame.playing)

# كود استخراج File ID للصور (اختياري، يمكنك حذفه بعد استخراج الأكواد)
@dp.message(F.photo)
async def get_photo_id(message: types.Message):
    file_id = message.photo[-1].file_id
    await message.reply(f"File ID للصورة:\n<code>{file_id}</code>", parse_mode="HTML")

if __name__ == "__main__":
    import asyncio
    init_db()
    asyncio.run(dp.start_polling(bot))
