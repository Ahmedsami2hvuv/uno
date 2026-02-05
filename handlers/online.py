import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك الأوراق (توليد الدك)
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    deck.extend(["🌈"] * 4)
    deck.extend(["🌈➕1"] * 4)
    deck.extend(["🌈➕2"] * 4)
    deck.extend(["🌈➕4"] * 4)
    random.shuffle(deck)
    return deck

# 2. وظيفة إرسال يد اللاعب (واجهة اللعب)
async def send_player_hand(user_id, game_id):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (user_id == game['p1_id'])
    hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    
    turn_text = "🟢 دورك الآن!" if game['turn'] == user_id else "⏳ دور الخصم..."
    opp_hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(",")
    
    text = (f"🃏 **الورقة المكشوفة:** `{game['top_card']}`\n"
            f"👤 الخصم لديه: {len(opp_hand)} أوراق\n"
            f"━━━━━━━━━━━━━━\n"
            f"{turn_text}")

    kb = []
    row = []
    for i, card in enumerate(hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"op_play_{game_id}_{i}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"op_draw_{game_id}"),
               InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}")])

    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. محرك البحث عن لاعب (Matchmaking)
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # البحث عن أي مباراة تنتظر لاعب (p2_id is NULL)
    waiting_game = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting_game:
        # وجدنا خصم! لنبدأ اللعبة
        game = waiting_game[0]
        deck = generate_deck()
        p1_hand = [deck.pop() for _ in range(7)]
        p2_hand = [deck.pop() for _ in range(7)]
        top_card = deck.pop()
        
        db_query('''UPDATE active_games SET 
                    p2_id = %s, 
                    p1_hand = %s, 
                    p2_hand = %s, 
                    top_card = %s, 
                    deck = %s, 
                    status = 'playing', 
                    turn = %s 
                    WHERE game_id = %s''', 
                 (user_id, ",".join(p1_hand), ",".join(p2_hand), top_card, ",".join(deck), game['p1_id'], game['game_id']), 
                 commit=True, fetch=False)
        
        await callback.message.edit_text("✅ تم العثور على خصم! بدأت اللعبة.")
        # إرسال أوراق اللعب للاعبين الاثنين
        await send_player_hand(game['p1_id'], game['game_id'])
        await send_player_hand(user_id, game['game_id'])
        
    else:
        # لا يوجد أحد ينتظر، نفتح غرفة جديدة وننتظر
        # أولاً نتأكد أن اللاعب ليس لديه غرفة انتظار قديمة
        db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True, fetch=False)
        
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True, fetch=False)
        await callback.message.edit_text("🔎 جاري البحث عن خصم... أرسل هذا البوت لصديق ليلعب معك!")
