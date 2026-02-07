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

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

class RoomStates(StatesGroup):
    wait_for_code = State()

# --- دالة توزيع الأوراق (7 أوراق) ---
async def start_private_game(room_id, bot):
    colors, numbers = ['🔴', '🔵', '🟡', '🟢'], [str(i) for i in range(10)] + ['🚫', '🔄', '➕2']
    deck = [f"{c} {n}" for c in colors for n in numbers] + [f"{c} {n}" for c in colors for n in numbers if n != '0']
    for _ in range(4): deck.extend(["🌈 جوكر", "➕4 🔥"])
    random.shuffle(deck)

    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)

    top_card = deck.pop()
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0 WHERE room_id = %s", (top_card, json.dumps(deck), room_id), commit=True)
    await refresh_game_ui(room_id, bot)

# --- واجهة اللعبة (تطلع للكل) ---
async def refresh_game_ui(room_id, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    turn_idx = room['turn_index']
    top_card = room['top_card']

    status_text = f"🃏 **الورقة الحالية:** [ {top_card} ]\n"
    status_text += "👥 **اللاعبين:**\n"
    for i, p in enumerate(players):
        star = "🌟" if i == turn_idx else "⏳"
        status_text += f"{star} | {p['player_name'][:10]} | 🃏 {len(json.loads(p['hand']))}\n"

    for p in players:
        if p.get('last_msg_id'):
            try: await bot.delete_message(p['user_id'], p['last_msg_id'])
            except: pass

        hand = json.loads(p['hand'])
        kb = []
        kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"draw_{room_id}")])
        
        row = []
        for idx, card in enumerate(hand):
            row.append(InlineKeyboardButton(text=card, callback_data=f"play_{room_id}_{idx}"))
            if len(row) == 2: kb.append(row); row = []
        if row: kb.append(row)

        msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", (msg.message_id, room_id, p['user_id']), commit=True)

# --- معالجة الضغط على الورقة ---
@router.callback_query(F.data.startswith("play_"))
async def play_card(c: types.CallbackQuery):
    _, room_id, idx = c.data.split("_")
    idx, user_id = int(idx), c.from_user.id
    
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    if players[room['turn_index']]['user_id'] != user_id:
        return await c.answer("⏳ مو دورك حبيبي!", show_alert=True)

    hand = json.loads(players[room['turn_index']]['hand'])
    played_card = hand[idx]

    # فحص بسيط للمطابقة
    if not (any(x in played_card for x in ['🌈', '🔥']) or 
            played_card.split()[0] == room['top_card'].split()[0] or 
            played_card.split()[1] == room['top_card'].split()[1]):
        return await c.answer("❌ ما ترهم!", show_alert=True)

    hand.pop(idx)
    next_idx = (room['turn_index'] + 1) % len(players)
    
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, user_id), commit=True)
    db_query("UPDATE rooms SET top_card = %s, turn_index = %s WHERE room_id = %s", (played_card, next_idx, room_id), commit=True)
    
    await refresh_game_ui(room_id, c.bot)

# --- سحب ورقة ---
@router.callback_query(F.data.startswith("draw_"))
async def draw_card(c: types.CallbackQuery):
    room_id = c.data.split("_")[1]
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    deck = json.loads(room['deck'])
    
    new_card = deck.pop(0)
    player = db_query("SELECT * FROM room_players WHERE room_id = %s AND user_id = %s", (room_id, c.from_user.id))[0]
    hand = json.loads(player['hand'])
    hand.append(new_card)

    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, c.from_user.id), commit=True)
    db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
    
    await c.answer(f"📥 سحبت: {new_card}")
    await refresh_game_ui(room_id, c.bot)

# (أضف دوال Create و Join البسيطة هنا)
