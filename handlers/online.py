import random
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    deck.extend(["🌈", "🌈➕1", "🌈➕2", "🌈➕4"] * 4)
    random.shuffle(deck)
    return deck

async def send_player_hand(user_id, game_id):
    game_list = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not game_list: return
    game = game_list[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    turn_text = "🟢 دورك!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم"
    
    text = f"🃏 المكشوفة: `{game['top_card']}`\n👤 الخصم: {len(opp_hand)} أوراق\n━━━━━━━━━━━━━━\n{turn_text}"
    kb = []
    row = []
    for i, card in enumerate(my_hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"op_play_{game_id}_{i}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton(text="📥 سحب", callback_data=f"op_draw_{game_id}"),
               InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}")])
    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    # 1. تنظيف أي انتظار قديم (بدون fetch)
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    
    # 2. البحث عن خصم
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        g = waiting[0]
        deck = generate_deck()
        p1_h, p2_h = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)]
        top = deck.pop()
        
        # 3. تحديث وبدء اللعبة
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s WHERE game_id=%s''',
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        
        await callback.message.edit_text("✅ تم الربط! بدأت اللعبة.")
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        # 4. إذا لم يجد خصم، ينتظر هو
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم... أرسل البوت لصديقك.")
