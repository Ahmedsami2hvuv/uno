import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك الأوراق
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

# 2. واجهة اللعب (Hand)
async def send_player_hand(user_id, game_id):
    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    turn_text = "🟢 دورك!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم"
    
    text = f"🃏 المكشوفة: `{game['top_card']}`\n👤 الخصم: {len(opp_hand)} أوراق\n━━━━━━━━━━━━━━\n{turn_text}"
    kb = []
    row = []
    for i, card in enumerate(my_hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{i}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب", callback_data=f"d_{game_id}"),
               InlineKeyboardButton(text="📢 أونو!", callback_data=f"u_{game_id}")])
    
    opp_uno = game['p2_uno'] if is_p1 else game['p1_uno']
    if len(opp_hand) == 1 and not opp_uno:
        kb.append([InlineKeyboardButton(text="🚨 صيده!", callback_data=f"c_{game_id}")])

    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. محرك الربط (Matchmaking)
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        g = waiting[0]
        deck = generate_deck()
        p1_h, p2_h = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)]
        top = deck.pop()
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s WHERE game_id=%s''',
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        await callback.message.edit_text("✅ تم الربط! بدأت اللعبة.")
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم أونلاين...")

# 4. معالجة لعب الورقة (القوانين والعقوبات)
@router.callback_query(F.data.startswith("p_"))
async def process_play(callback: types.CallbackQuery):
    _, g_id, idx = callback.data.split("_")
    game_res = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))
    if not game_res: return
    game = game_res[0]
    
    if int(callback.from_user.id) != int(game['turn']):
        return await callback.answer("مو دورك! ⏳", show_alert=True)
    
    is_p1 = (int(callback.from_user.id) == int(game['p1_id']))
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    deck = [d for d in game['deck'].split(",") if d]
    played_card = my_hand[int(idx)]
    top_card = game['top_card']

    # فحص قانونية الورقة
    can_play = False
    if "🌈" in played_card or "🌈" in top_card:
        can_play = True
    else:
        if played_card[0] == top_card[0] or played_card.split()[-1] == top_card.split()[-1]:
            can_play = True

    if not can_play:
        await callback.answer("❌ ورقة خطأ! سحب ورقتين.", show_alert=True)
        for _ in range(2): 
            if deck: my_hand.append(deck.pop(0))
        next_turn = game['p2_id'] if is_p1 else game['p1_id']
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s",
                 (",".join(my_hand), ",".join(deck), next_turn, g_id), commit=True)
        await callback.message.delete()
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)
        return

    my_hand.pop(int(idx))

    # فحص الفوز
    if not my_hand:
        db_query("UPDATE users SET online_points = online_points + 10 WHERE user_id = %s", (callback.from_user.id,), commit=True)
        pts = db_query("SELECT online_points FROM users WHERE user_id = %s", (callback.from_user.id,))[0]['online_points']
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        await callback.message.delete()
        await callback.message.answer(f"🏆 مبروك! فزت بـ 10 نقاط.\n⭐ رصيدك الحالي: {pts}")
        await bot.send_message(game['p2_id'] if is_p1 else game['p1_id'], f"💀 خسرت! رصيد الخصم وصل لـ {pts}")
        return

    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    if "➕" in played_card:
        plus = 1 if "➕1" in played_card else (2 if "➕2" in played_card else 4)
        for _ in range(plus):
            if deck: opp_hand.append(deck.pop(0))
        next_turn = callback.from_user.id
    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = callback.from_user.id

    db_query(f'''UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, 
                {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s, p1_uno=FALSE, p2_uno=FALSE WHERE game_id=%s''', 
             (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)
    
    await callback.message.delete()
    if played_card == "🌈":
        await ask_color(callback.from_user.id, g_id)
    else:
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)

# 5. السحب والأونو والصيد
@router.callback_query(F.data.startswith("d_"))
async def process_draw(callback: types.CallbackQuery):
    g_id = callback.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(callback.from_user.id) != int(game['turn']): return await callback.answer("مو دورك!")
    is_p1 = (int(callback.from_user.id) == int(game['p1_id']))
    deck = [x for x in game['deck'].split(",") if x]
    hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    if deck:
        new_c = deck.pop(0); hand.append(new_c)
        t = game['top_card']
        can_p = ("🌈" in new_c or new_c[0] == t[0] or (len(new_c.split())>1 and len(t.split())>1 and new_c.split()[1] == t.split()[1]))
        nt = callback.from_user.id if can_p else (game['p2_id'] if is_p1 else game['p1_id'])
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
                 (",".join(hand), ",".join(deck), nt, g_id), commit=True)
        await callback.message.delete(); await send_player_hand(game['p1_id'], g_id); await send_player_hand(game['p2_id'], g_id)

@router.callback_query(F.data.startswith("u_"))
async def process_uno(callback: types.CallbackQuery):
    g_id = callback.data.split("_")[1]
    is_p1 = (int(callback.from_user.id) == int(db_query("SELECT p1_id FROM active_games WHERE game_id=%s", (g_id,))[0]['p1_id']))
    db_query(f"UPDATE active_games SET {'p1_uno' if is_p1 else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)
    await callback.answer("📢 أونو!"); await callback.message.delete(); await send_player_hand(callback.from_user.id, g_id)

@router.callback_query(F.data.startswith("c_"))
async def process_catch(callback: types.CallbackQuery):
    g_id = callback.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1_c = (int(callback.from_user.id) == int(game['p1_id']))
    target_hand = (game['p2_hand'] if is_p1_c else game['p1_hand']).split(",")
    deck = game['deck'].split(",")
    target_hand.extend([deck.pop(0), deck.pop(0)])
    db_query(f"UPDATE active_games SET {'p2_hand' if is_p1_c else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(target_hand), ",".join(deck), g_id), commit=True)
    await callback.answer("🚨 صادوووه!"); await callback.message.delete(); await send_player_hand(game['p1_id'], g_id); await send_player_hand(game['p2_id'], g_id)

# 6. اختيار اللون
async def ask_color(user_id, game_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"sc_{game_id}_🔴"), InlineKeyboardButton(text="🔵", callback_data=f"sc_{game_id}_🔵")],
          [InlineKeyboardButton(text="🟡", callback_data=f"sc_{game_id}_🟡"), InlineKeyboardButton(text="🟢", callback_data=f"sc_{game_id}_🟢")]]
    await bot.send_message(user_id, "🌈 اختر اللون المطلوب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sc_"))
async def set_color_logic(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    next_p = game['p2_id'] if int(c.from_user.id) == int(game['p1_id']) else game['p1_id']
    db_query("UPDATE active_games SET top_card=%s, turn=%s WHERE game_id=%s", (f"{col} (🌈)", next_p, g_id), commit=True)
    await c.message.delete(); await send_player_hand(game['p1_id'], g_id); await send_player_hand(game['p2_id'], g_id)
