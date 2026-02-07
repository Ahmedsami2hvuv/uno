from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
import random
import string
import json

router = Router()

# دالة لتوليد كود غرفة فريد
def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

# --- حالات الغرف الخاصة ---
class RoomStates(StatesGroup):
    wait_for_code = State()

class RegisterStates(StatesGroup):
    wait_name = State()
    wait_password = State()

# --- قسم مستخرج الأكواد ---
@router.message(F.photo)
async def get_photo_id(message: types.Message):
    await message.reply(f"✅ كود الصورة: `{message.photo[-1].file_id}`", parse_mode="Markdown")

# --- نظام التسجيل والترحيب ---
@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    if not user or not user[0].get('is_registered'):
        if not user:
            db_query("INSERT INTO users (user_id, username, is_registered) VALUES (%s, %s, FALSE)", 
                     (message.from_user.id, message.from_user.username), commit=True)
        await message.answer("👋 أهلاً بك! لإنشاء حسابك، أرسل اسم اللاعب الذي تريده:")
        await state.set_state(RegisterStates.wait_name)
    else:
        await show_main_menu(message, user[0]['player_name'])

@router.message(RegisterStates.wait_name)
async def get_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if db_query("SELECT user_id FROM users WHERE player_name = %s", (name,)):
        return await message.answer("❌ الاسم محجوز! اختر غيره:")
    await state.update_data(p_name=name)
    await message.answer(f"أهلاً {name}! اختر رمزاً سرياً لحسابك:")
    await state.set_state(RegisterStates.wait_password)

@router.message(RegisterStates.wait_password)
async def get_pass(message: types.Message, state: FSMContext):
    password, data = message.text.strip(), await state.get_data()
    db_query("UPDATE users SET player_name = %s, password = %s, is_registered = TRUE WHERE user_id = %s",
             (data['p_name'], password, message.from_user.id), commit=True)
    await message.answer("✅ تم التفعيل!"); await show_main_menu(message, data['p_name'])

# --- القائمة الرئيسية ---
async def show_main_menu(message, name):
    kb = [[InlineKeyboardButton(text="🎲 لعب عشوائي", callback_data="mode_random"), 
           InlineKeyboardButton(text="🏠 غرفة لعب", callback_data="private_room_menu")],
          [InlineKeyboardButton(text="🧮 حاسبة اونو", callback_data="mode_calc")],
          [InlineKeyboardButton(text="🏆 المتصدرين", callback_data="leaderboard")]]
    text = f"🃏 مرحباً بك {name}\nاختر ما تريد فعله:"
    if hasattr(message, "answer"): await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- معالج خيارات الغرفة ---
@router.callback_query(F.data == "private_room_menu")
async def private_room_main(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = [[InlineKeyboardButton(text="➕ إنشاء غرفة", callback_data="room_create")],
          [InlineKeyboardButton(text="🚪 انضمام لغرفة", callback_data="room_join_input")],
          [InlineKeyboardButton(text="🏠 الرجوع", callback_data="home")]]
    await c.message.edit_text("🎮 **غرف اللعب الخاصة**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- نظام الانضمام والتصويت الذكي ---
@router.callback_query(F.data == "room_join_input")
async def join_room_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("📥 أرسل كود الغرفة (5 رموز):")
    await state.set_state(RoomStates.wait_for_code)

@router.message(RoomStates.wait_for_code)
async def process_room_join(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room: return await message.answer("❌ الكود غير صحيح.")
    
    current_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
    if any(p['user_id'] == message.from_user.id for p in current_players):
        return await message.answer("⚠️ أنت موجود أصلاً بالغرفة!")
    
    if len(current_players) >= room[0]['max_players']:
        return await message.answer("🚫 الغرفة ممتلئة!")

    user_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", 
             (code, message.from_user.id, user_data[0]['player_name']), commit=True)
    
    new_count, max_p = len(current_players) + 1, room[0]['max_players']
    await state.clear()
    await message.answer(f"✅ دخلت الغرفة `{code}`. ({new_count}/{max_p})")

    if new_count == max_p:
        if max_p == 2 or max_p % 2 != 0:
            db_query("UPDATE rooms SET game_mode = 'solo', status = 'playing' WHERE room_id = %s", (code,), commit=True)
            await start_private_game(code, message.bot)
        else:
            db_query("UPDATE rooms SET status = 'voting' WHERE room_id = %s", (code,), commit=True)
            kb = [[InlineKeyboardButton(text="👥 نظام فريق", callback_data=f"vote_team_{code}"),
                   InlineKeyboardButton(text="👤 نظام فردي", callback_data=f"vote_solo_{code}")]]
            all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
            for p in all_players:
                try: await message.bot.send_message(p['user_id'], "🎉 اكتمل العدد! صوتوا للنمط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                except: pass

@router.callback_query(F.data.startswith("vote_"))
async def handle_voting(c: types.CallbackQuery):
    _, mode, code = c.data.split("_")
    db_query("UPDATE rooms SET game_mode = %s, status = 'playing' WHERE room_id = %s", (mode, code), commit=True)
    await start_private_game(code, c.bot)

# --- 🃏 المحرك: توزيع الأوراق وبدء اللعبة ---
async def start_private_game(room_id, bot):
    colors, numbers = ['🔴', '🔵', '🟡', '🟢'], [str(i) for i in range(10)] + ['🚫', '🔄', '➕2']
    deck = [f"{c} {n}" for c in colors for n in numbers] + [f"{c} {n}" for c in colors for n in numbers if n != '0']
    for _ in range(4): deck.extend(["🌈 جوكر", "➕4 🔥"])
    random.shuffle(deck)

    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)

    top_card = deck.pop()
    while any(x in top_card for x in ['➕', '🌈', '🚫', '🔄']):
        deck.append(top_card); random.shuffle(deck); top_card = deck.pop()

    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0 WHERE room_id = %s", (top_card, json.dumps(deck), room_id), commit=True)
    await refresh_game_ui(room_id, bot)

# --- 📊 واجهة الجدول ---
async def refresh_game_ui(room_id, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    deck_count = len(json.loads(room['deck']))
    
    status_text = f"🃏 **الورقة:** [ {room['top_card']} ]\n📦 **الكومة:** {deck_count}\n\n👥 **اللاعبين:**\n"
    for i, p in enumerate(players):
        star = "🌟" if i == room['turn_index'] else "⏳"
        status_text += f"{star} | {p['player_name'][:10]:<10} | 🃏 {len(json.loads(p['hand']))}\n"
    
    for i, p in enumerate(players):
        kb = [[InlineKeyboardButton(text="🃏 أوراقي", callback_data=f"show_hand_{room_id}")]] if i == room['turn_index'] else []
        try: await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except: pass

# --- مراحل إنشاء الغرفة ---
@router.callback_query(F.data == "room_create")
async def room_create_start(c: types.CallbackQuery):
    kb, row = [], []
    for i in range(2, 11):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"setp_{i}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    await c.message.edit_text("👥 حدد عدد اللاعبين:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("setp_"))
async def set_room_players(c: types.CallbackQuery):
    num, scores = c.data.split("_")[1], [100, 200, 300, 400, 500]
    kb, row = [], []
    for s in scores:
        row.append(InlineKeyboardButton(text=str(s), callback_data=f"sets_{num}_{s}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    await c.message.edit_text(f"🎯 لاعبين: {num}. حدد السقف:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sets_"))
async def finalize_room_creation(c: types.CallbackQuery):
    _, p_count, s_limit = c.data.split("_")
    code = generate_room_code()
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit) VALUES (%s, %s, %s, %s)", (code, c.from_user.id, int(p_count), int(s_limit)), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", (code, c.from_user.id, u_name), commit=True)
    await c.message.edit_text(f"✅ الغرفة: `{code}`\nانتظر ربعك (1/{p_count})"); await c.message.answer(f"`{code}`")

@router.callback_query(F.data == "home")
async def go_home(c: types.CallbackQuery, state: FSMContext):
    await state.clear(); user = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    await show_main_menu(c.message, user[0]['player_name'])
