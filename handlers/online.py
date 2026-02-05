import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك الأوراق (7 أوراق لكل لاعب)
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
    try:
        game_data = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
        if not game_data: return
        game = game_data[0]
        
        is_p1 = (int(user_id) == int(game['p1_id']))
        my_hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
        opp_hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(",")
        
        # تنظيف القائمة من الفراغات
        my_hand = [c for c in my_hand if c]
        opp_hand = [c for c in opp_hand if c]

        turn_text = "🟢 دورك الآن!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم..."
        
        text = (f"🃏 **الورقة المكشوفة:** `{game['top_card']}`\n"
                f"👤 الخصم لديه: {len(opp_hand)} أوراق\n"
                f"━━━━━━━━━━━━━━\n"
                f"{turn_text}")

        kb = []
        row = []
        for i, card in enumerate(my_hand):
            row.append(InlineKeyboardButton(text=card, callback_data=f"op_play_{game_id}_{i}"))
            if len(row) == 3:
                kb.append(row)
                row = []
        if row: kb.append(row)
        
        # أزرار التحكم (سحب وأونو وصيد)
        control = [InlineKeyboardButton(text="📥 سحب", callback_data=f"op_draw_{game_id}")]
        if len(my_hand) == 2:
            control.append(InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}"))
        if len(opp_hand) == 1 and not (game['p2_uno'] if is_p1 else game['p1_uno']):
            control.append(InlineKeyboardButton(text="🚨 صيده!", callback_data=f"op_catch_{game_id}"))
        
        kb.append(control)
        await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except Exception as e:
        print(f"❌ Error in send_player_hand: {e}")

# 3. اللعب العشوائي (Matchmaking)
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    # تنظيف أي مباراة قديمة معلقة للاعب
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True, fetch=False)
    
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        g = waiting[0]
        deck = generate_deck()
        p1_h = [deck.pop() for _ in range(7)] # 7 أوراق
        p2_h = [deck.pop() for _ in range(7)] # 7 أوراق
        top = deck.pop()
        
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s WHERE game_id=%s''', 
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True, fetch=False)
        
        await callback.message.edit_text("✅ تم العثور على خصم!")
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True, fetch=False)
        await callback.message.edit_text("🔎 جاري البحث عن خصم... أرسل البوت لصديقك ليلعب معك!")

# 4. معالجة لعب الورقة
@router.callback_query(F.data.startswith("op_play_"))
async def process_play(c: types.CallbackQuery):
    try:
        data_parts = c.data.split("_")
        g_id = int(data_parts[2])
        idx = int(data_parts[3])
        
        game_data = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))
        if not game_data: return
        game = game_data[0]

        if int(c.from_user.id) != int(game['turn']):
            return await c.answer("مو دورك! ⏳", show_alert=True)

        is_p1 = (int(c.from_user.id) == int(game['p1_id']))
        my_hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
        played_card = my_hand.pop(idx)
        top_card = game['top_card']
        deck = game['deck'].split(",")

        # منطق التحقق (Logic)
        can_play = False
        if "🌈" in played_card: can_play = True
        else:
            t_col = top_card[0]; p_col = played_card[0]
            t_val = top_card.split(" ")[1] if " " in top_card else top_card
            p_val = played_card.split(" ")[1] if " " in played_card else played_card
            if p_col == t_col or p_val == t_val or "🌈" in top_card: can_play = True

        if not can_play:
            await c.answer("❌ ورقة غلط! عقوبة سحب 2")
            my_hand.extend([deck.pop(0), deck.pop(0)])
            db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), g_id), commit=True, fetch=False)
            await c.message.delete(); return await send_player_hand(c.from_user.id, g_id)

        # تحديث الدور (الأكشن يرجع الدور لك)
        is_action = any(x in played_card for x in ["🚫", "🔄", "➕", "🌈➕"])
        next_turn = game['p1_id'] if not is_p1 else game['p2_id']
        if is_action: next_turn = c.from_user.id

        # تحديث الداتا بيس
        db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, turn=%s, p1_uno=FALSE, p2_uno=FALSE WHERE game_id=%s", 
                 (played_card, ",".join(my_hand), next_turn, g_id), commit=True, fetch=False)

        await c.message.delete()
        
        if "🌈" in played_card and "➕" not in played_card:
            await ask_color(c.from_user.id, g_id)
        else:
            await send_player_hand(game['p1_id'], g_id)
            await send_player_hand(game['p2_id'], g_id)
    except Exception as e:
        print(f"❌ Error in process_play: {e}")

# 5. سحب ورقة
@router.callback_query(F.data.startswith("op_draw_"))
async def on_draw(c: types.CallbackQuery):
    g_id = int(c.data.split("_")[2])
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")
    
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    deck = game['deck'].split(","); hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    if deck:
        hand.append(deck.pop(0))
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
                 (",".join(hand), ",".join(deck), game['p2_id'] if is_p1 else game['p1_id'], g_id), commit=True, fetch=False)
    
    await c.message.delete(); await send_player_hand(game['p1_id'], g_id); await send_player_hand(game['p2_id'], g_id)

async def ask_color(user_id, game_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"sc_{game_id}_🔴"), InlineKeyboardButton(text="🔵", callback_data=f"sc_{game_id}_🔵")],
          [InlineKeyboardButton(text="🟡", callback_data=f"sc_{game_id}_🟡"), InlineKeyboardButton(text="🟢", callback_data=f"sc_{game_id}_🟢")]]
    await bot.send_message(user_id, "🌈 اختر اللون المطلوب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sc_"))
async def set_color_logic(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (int(g_id),))[0]
    next_p = game['p2_id'] if int(c.from_user.id) == int(game['p1_id']) else game['p1_id']
    db_query("UPDATE active_games SET top_card=%s, turn=%s WHERE game_id=%s", (f"{col} (🌈)", next_p, int(g_id)), commit=True, fetch=False)
    await c.message.delete(); await send_player_hand(game['p1_id'], g_id); await send_player_hand(game['p2_id'], g_id)
