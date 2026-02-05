import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك الأوراق المطور
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    
    # الأوراق الخاصة اللي طلبتها
    deck.extend(["🌈"] * 4)       # ملونة (50 نقطة)
    deck.extend(["🌈➕1"] * 4)     # جوكر +1 (10 نقاط)
    deck.extend(["🌈➕2"] * 4)     # جوكر +2 (20 نقطة)
    deck.extend(["🌈➕4"] * 4)     # جوكر +4 (50 نقطة)
    random.shuffle(deck)
    return deck

# 2. وظيفة إرسال يد اللاعب (أزرار الأوراق)
async def send_player_hand(user_id, game_id):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (user_id == game['p1_id'])
    hand = game['p1_hand'].split(",") if is_p1 else game['p2_hand'].split(",")
    
    turn_text = "🟢 دورك الآن!" if game['turn'] == user_id else "⏳ دور الخصم..."
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    opp_hand_count = len(game['p2_hand'].split(',')) if is_p1 else len(game['p1_hand'].split(','))

    status_msg = (f"🃏 **الورقة المكشوفة:** `{game['top_card']}`\n"
                  f"━━━━━━━━━━━━━━\n"
                  f"{turn_text}\n"
                  f"👤 الخصم لديه: {opp_hand_count} أوراق")

    kb = []
    row = []
    for i, card in enumerate(hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"op_play_{game_id}_{i}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"op_draw_{game_id}")])
    kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}")])

    await bot.send_message(user_id, status_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. نظام البحث عن لاعب
@router.callback_query(F.data == "mode_random")
async def start_matchmaking(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    waiting_game = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting_game:
        g = waiting_game[0]
        deck = generate_deck()
        p1_h, p2_h = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)]
        top = deck.pop()
        
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, 
                   deck=%s, status='playing', turn=%s WHERE game_id=%s''', 
                (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True, fetch=False)
        
        await callback.message.edit_text("✅ وجدنا خصماً! بدأت اللعبة...")
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True, fetch=False)
        await callback.message.edit_text("🔎 جاري البحث عن لاعب... (سيلعب البوت معك بعد 30ث)")

# 4. منطق لعب الورقة والتحقق من الصحة
@router.callback_query(F.data.startswith("op_play_"))
async def process_play(c: types.CallbackQuery):
    _, _, g_id, idx = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    if c.from_user.id != game['turn']:
        return await c.answer("مو دورك! انتظر الخصم يلعب ⏳", show_alert=True)
    
    is_p1 = (c.from_user.id == game['p1_id'])
    hand = game['p1_hand'].split(",") if is_p1 else game['p2_hand'].split(",")
    played_card = hand[int(idx)]
    top_card = game['top_card']
    
    # منطق التحقق (نفس اللون أو نفس الرقم/الرمز)
    can_play = False
    if "🌈" in played_card: can_play = True
    else:
        t_color = top_card.split(" ")[0]
        t_val = top_card.split(" ")[1] if " " in top_card else top_card
        p_color = played_card.split(" ")[0]
        p_val = played_card.split(" ")[1] if " " in played_card else played_card
        if p_color == t_color or p_val == t_val: can_play = True

    if not can_play:
        await c.answer("❌ ورقة غلط! عقوبة سحب ورقتين.", show_alert=True)
        # سحب عقوبة
        deck = game['deck'].split(",")
        hand.extend([deck.pop(), deck.pop()])
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", 
                 (",".join(hand), ",".join(deck), g_id), commit=True, fetch=False)
        await c.message.delete()
        return await send_player_hand(c.from_user.id, g_id)

    # إذا كانت الورقة صحيحة
    hand.pop(int(idx))
    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    
    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, turn=%s WHERE game_id=%s",
             (played_card, ",".join(hand), next_turn, g_id), commit=True, fetch=False)
    
    await c.message.delete()
    # تحديث الشاشتين
    await send_player_hand(game['p1_id'], g_id)
    await send_player_hand(game['p2_id'], g_id)
