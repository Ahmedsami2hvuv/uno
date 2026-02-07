from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
import random
import string
import json
import asyncio

router = Router()

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

class RoomStates(StatesGroup):
    wait_for_code = State()

class RegisterStates(StatesGroup):
    wait_name = State()
    wait_password = State()

class GameStates(StatesGroup):
    waiting_for_challenge = State()
    waiting_for_color_choice = State()

# --- دالة إنشاء الكومة الرسمية (108 ورقة) ---
async def create_uno_deck():
    colors = ['🔴', '🔵', '🟡', '🟢']
    numbers = ['0'] + [str(i) for i in range(1, 10)] * 2
    actions = ['🚫', '🔄', '➕2'] * 2
    deck = []
    for color in colors:
        for num in numbers: deck.append(f"{color} {num}")
        for action in actions: deck.append(f"{color} {action}")
    for _ in range(4):
        deck.append("🌈 جوكر ملون")
        deck.append("🌈 جوكر +4")
    random.shuffle(deck)
    return deck

# --- دالة فحص قابلية اللعب ---
async def is_card_playable(card, top_card, current_color):
    if '🌈' in card: return True
    card_parts = card.split()
    top_parts = top_card.split()
    # فحص اللون أو القيمة
    if card_parts[0] == current_color: return True
    if len(card_parts) > 1 and len(top_parts) > 1:
        if card_parts[1] == top_parts[1]: return True
    return False

# --- دالة حساب النقاط ---
def calculate_hand_points(hand_json):
    hand = json.loads(hand_json) if isinstance(hand_json, str) else hand_json
    total = 0
    for card in hand:
        if any(x in card for x in ['🚫', '🔄', '➕2']): total += 20
        elif '🌈' in card: total += 50
        else:
            try: total += int(card.split()[1])
            except: total += 5
    return total

# --- 📊 واجهة الجدول الموحدة (الأوراق تطلع للكل) ---
async def refresh_game_ui(room_id, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    turn_idx = room['turn_index']
    top_card = room['top_card']
    current_color = room.get('current_color', top_card.split()[0])
    current_player_id = players[turn_idx]['user_id']

    status_text = f"🃏 **الورقة:** [ {top_card} ] | 🎨: {current_color}\n"
    status_text += f"📦 الكومة: {len(json.loads(room['deck']))} | 🎯 السقف: {room['score_limit']}\n\n"
    
    for i, p in enumerate(players):
        star = "🌟" if i == turn_idx else "⏳"
        status_text += f"{star} {p['player_name'][:10]} | 🃏 {len(json.loads(p['hand']))} | 🏆 {p['points']}\n"

    for p in players:
        if p.get('last_msg_id'):
            try: await bot.delete_message(p['user_id'], p['last_msg_id'])
            except: pass
        
        hand = json.loads(p['hand'])
        kb = []
        # زر السحب يظهر للكل لكن يعمل فقط في دورك
        kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"draw_{room_id}")])
        
        row = []
        for idx, card in enumerate(hand):
            row.append(InlineKeyboardButton(text=card, callback_data=f"play_{room_id}_{idx}"))
            if len(row) == 2: kb.append(row); row = []
        if row: kb.append(row)
        
        msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", (msg.message_id, room_id, p['user_id']), commit=True)

# --- 🃏 دالة بدء اللعبة (7 أوراق حقيقية) ---
async def start_private_game(room_id, bot):
    deck = await create_uno_deck()
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s, points = 0 WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)
    
    top_card = deck.pop()
    while any(x in top_card for x in ['🌈', '🚫', '🔄', '➕']):
        deck.append(top_card); random.shuffle(deck); top_card = deck.pop()
        
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0, current_color = %s, status='playing' WHERE room_id = %s", 
             (top_card, json.dumps(deck), top_card.split()[0], room_id), commit=True)
    await refresh_game_ui(room_id, bot)

# --- معالجة لعب الورقة ---
@router.callback_query(F.data.startswith("play_"))
async def play_card(c: types.CallbackQuery, state: FSMContext):
    _, room_id, idx = c.data.split("_")
    idx, user_id = int(idx), c.from_user.id
    
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    if players[room['turn_index']]['user_id'] != user_id:
        return await c.answer("⏳ مو دورك! تفرج وخطط 🌟", show_alert=True)
    
    hand = json.loads(players[room['turn_index']]['hand'])
    played_card = hand[idx]
    
    if not await is_card_playable(played_card, room['top_card'], room['current_color']):
        return await c.answer("❌ ما ترهم!", show_alert=True)

    # إذا جوكر، لازم يختار لون
    if '🌈' in played_card:
        await state.update_data(room_id=room_id, card_idx=idx, player_index=room['turn_index'])
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔴", callback_data=f"color_🔴_{room_id}"), InlineKeyboardButton(text="🔵", callback_data=f"color_🔵_{room_id}")],
            [InlineKeyboardButton(text="🟡", callback_data=f"color_🟡_{room_id}"), InlineKeyboardButton(text="🟢", callback_data=f"color_🟢_{room_id}")]
        ])
        await c.message.answer("🎨 اختر اللون:", reply_markup=kb)
        return

    # تنفيذ اللعب العادي
    hand.pop(idx)
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, user_id), commit=True)
    
    if len(hand) == 0:
        # هنا برمجنا حساب النقاط للفوز بالجولة (مختصر)
        db_query("UPDATE rooms SET status='finished' WHERE room_id = %s", (room_id,), commit=True)
        return await c.message.answer(f"🏆 {c.from_user.full_name} فاز بالجولة!")

    # نقل الدور (تبسيط)
    next_idx = (room['turn_index'] + 1) % room['max_players']
    db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s WHERE room_id = %s", 
             (played_card, played_card.split()[0], next_idx, room_id), commit=True)
    
    await refresh_game_ui(room_id, c.bot)

# (أضف هنا باقي دوال الـ Start, Create, Join كما هي عندك)
@router.callback_query(F.data == "room_create")
async def room_create_start(c: types.CallbackQuery):
    kb = [[InlineKeyboardButton(text=str(i), callback_data=f"setp_{i}") for i in range(2, 5)],
          [InlineKeyboardButton(text=str(i), callback_data=f"setp_{i}") for i in range(5, 8)]]
    await c.message.edit_text("👥 حدد عدد اللاعبين:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("setp_"))
async def set_room_players(c: types.CallbackQuery):
    num = c.data.split("_")[1]
    kb = [[InlineKeyboardButton(text=str(s), callback_data=f"sets_{num}_{s}") for s in [100, 200, 500]]]
    await c.message.edit_text(f"🎯 لاعبين: {num}. حدد السقف:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sets_"))
async def finalize_room_creation(c: types.CallbackQuery):
    _, p_count, s_limit = c.data.split("_")
    code = generate_room_code()
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit) VALUES (%s, %s, %s, %s)", (code, c.from_user.id, int(p_count), int(s_limit)), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name, join_order) VALUES (%s, %s, %s, 1)", (code, c.from_user.id, u_name), commit=True)
    await c.message.edit_text(f"✅ الغرفة: `{code}`"); await c.message.answer(f"`{code}`")

@router.callback_query(F.data == "room_join_input")
async def join_room_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("📥 أرسل كود الغرفة:")
    await state.set_state(RoomStates.wait_for_code)

@router.message(RoomStates.wait_for_code)
async def process_room_join(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room: return await message.answer("❌ كود غلط")
    user_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    db_query("INSERT INTO room_players (room_id, user_id, player_name, join_order) VALUES (%s, %s, %s, (SELECT COUNT(*)+1 FROM room_players WHERE room_id=%s))", (code, message.from_user.id, user_data[0]['player_name'], code), commit=True)
    
    current_players = db_query("SELECT COUNT(*) as count FROM room_players WHERE room_id = %s", (code,))[0]['count']
    if current_players == room[0]['max_players']:
        await start_private_game(code, message.bot)
    else:
        await message.answer(f"✅ دخلت! ({current_players}/{room[0]['max_players']})")
