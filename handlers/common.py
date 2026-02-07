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

class RoomStates(StatesGroup):
    wait_for_code = State()

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

# --- 1. أمر البداية (هذا اللي يخلي البوت ينطق) ---
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [
        [InlineKeyboardButton(text="🏠 إنشاء غرفة", callback_data="room_create")],
        [InlineKeyboardButton(text="🚪 انضمام لغرفة", callback_data="room_join_input")]
    ]
    await message.answer(
        f"🃏 أهلاً بك {message.from_user.full_name} في بوت الأونو!\n\n"
        "هذا النظام يعتمد قوانين الأونو الرسمية (7 أوراق).\n"
        "اختر ما تريد فعله:", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

# --- 2. معالج الأزرار الرئيسية ---
@router.callback_query(F.data == "room_create")
async def room_create_start(c: types.CallbackQuery):
    kb = [[InlineKeyboardButton(text=str(i), callback_data=f"setp_{i}") for i in range(2, 5)]]
    await c.message.edit_text("👥 حدد عدد اللاعبين:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("setp_"))
async def set_room_players(c: types.CallbackQuery):
    num = c.data.split("_")[1]
    kb = [[InlineKeyboardButton(text="100 نقطة", callback_data=f"sets_{num}_100")]]
    await c.message.edit_text(f"🎯 لاعبين: {num}\nحدد سقف النقاط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sets_"))
async def finalize_room_creation(c: types.CallbackQuery):
    _, p_count, s_limit = c.data.split("_")
    code = generate_room_code()
    
    # جلب اسم اللاعب من جدول users
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    p_name = user[0]['player_name'] if user else c.from_user.full_name

    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit) VALUES (%s, %s, %s, %s)", 
             (code, c.from_user.id, int(p_count), int(s_limit)), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", 
             (code, c.from_user.id, p_name), commit=True)
    
    await c.message.edit_text(f"✅ تم إنشاء الغرفة!\n\nكود الدخول: `{code}`\n\nانتظر انضمام بقية اللاعبين...")
    await c.message.answer(f"`{code}`")

@router.callback_query(F.data == "room_join_input")
async def join_room_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("📥 أرسل كود الغرفة المكون من 5 رموز:")
    await state.set_state(RoomStates.wait_for_code)

@router.message(RoomStates.wait_for_code)
async def process_room_join(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    
    if not room:
        return await message.answer("❌ الكود غير صحيح، تأكد من الكود وأرسله مرة أخرى.")
    
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    p_name = user[0]['player_name'] if user else message.from_user.full_name
    
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", 
             (code, message.from_user.id, p_name), commit=True)
    
    current_players = db_query("SELECT COUNT(*) as count FROM room_players WHERE room_id = %s", (code,))[0]['count']
    
    if current_players >= room[0]['max_players']:
        await message.answer("🎉 اكتمل العدد! جاري بدء اللعبة...")
        await start_private_game(code, message.bot)
    else:
        await message.answer(f"✅ تم الانضمام! ({current_players}/{room[0]['max_players']}) بانتظار البقية...")
    await state.clear()

# --- 3. محرك اللعبة (توزيع 7 أوراق) ---
async def start_private_game(room_id, bot):
    colors, numbers = ['🔴', '🔵', '🟡', '🟢'], [str(i) for i in range(10)] + ['🚫', '🔄', '➕2']
    deck = [f"{c} {n}" for c in colors for n in numbers] + [f"{c} {n}" for c in colors for n in numbers if n != '0']
    for _ in range(4): deck.extend(["🌈 جوكر", "➕4 🔥"])
    random.shuffle(deck)

    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
                 (json.dumps(hand), room_id, p['user_id']), commit=True)

    top_card = deck.pop()
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0, status='playing' WHERE room_id = %s", 
             (top_card, json.dumps(deck), room_id), commit=True)
    await refresh_game_ui(room_id, bot)

# (أضف دالة refresh_game_ui و play_card هنا كما في الكود المستقر السابق)
