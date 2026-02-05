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

# 2. واجهة اللعب المحدثة
async def send_player_hand(user_id, game_id):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    
    my_uno = game['p1_uno'] if is_p1 else game['p2_uno']
    opp_uno = game['p2_uno'] if is_p1 else game['p1_uno']

    turn_text = "🟢 دورك!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم"
    text = (f"🃏 المكشوفة: `{game['top_card']}`\n"
            f"👤 الخصم: {len(opp_hand)} أوراق\n"
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
    
    # أزرار التحكم
    control = [InlineKeyboardButton(text="📥 سحب", callback_data=f"op_draw_{game_id}")]
    if len(my_hand) == 1 and not my_uno: # زر الأونو يظهر لما تبقى ورقة واحدة ولم تضغط عليه
        control.append(InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}"))
    
    # زر الصيد يظهر للخصم إذا كان اللاعب لديه ورقة واحدة ولم يقل أونو
    if len(opp_hand) == 1 and not opp_uno:
        control.append(InlineKeyboardButton(text="🚨 صيده!", callback_data=f"op_catch_{game_id}"))
    
    kb.append(control)
    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. معالجة لعب الورقة (وتحديث الخصم)
@router.callback_query(F.data.startswith("op_play_"))
async def process_play(c: types.CallbackQuery):
    g_id = int(c.data.split("_")[2])
    idx = int(c.data.split("_")[3])
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")

    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    played_card = my_hand.pop(idx)
    deck = game['deck'].split(",")

    # فحص الفوز
    if len(my_hand) == 0:
        db_query("UPDATE users SET online_points = online_points + 10 WHERE user_id = %s", (c.from_user.id,), commit=True)
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        await c.message.answer("🏆 مبروك! فزت باللعبة وحصلت على 10 نقاط.")
        await bot.send_message(game['p2_id'] if is_p1 else game['p1_id'], "💀 خسرتم اللعبة!")
        return

    # منطق الأوراق الخاصة (السحب للخصم)
    opp_hand = [h for h in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if h]
    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    
    if "➕" in played_card:
        plus = 1 if "➕1" in played_card else (2 if "➕2" in played_card else 4)
        for _ in range(plus): 
            if deck: opp_hand.append(deck.pop(0))
        next_turn = c.from_user.id # الدور يبقى لك
        await bot.send_message(next_turn, f"🔥 سحبت خصمك {plus} أوراق والدور بقى عندك!")

    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = c.from_user.id
        await c.answer("🚫 منعت الخصم!")

    # تحديث الداتا بيس (تحديث يد اللاعب ويد الخصم)
    my_hand_str = ",".join(my_hand)
    opp_hand_str = ",".join(opp_hand)
    
    db_query(f'''UPDATE active_games SET 
                top_card=%s, 
                {'p1_hand' if is_p1 else 'p2_hand'}=%s, 
                {'p2_hand' if is_p1 else 'p1_hand'}=%s, 
                deck=%s, turn=%s, p1_uno=FALSE, p2_uno=FALSE 
                WHERE game_id=%s''', 
             (played_card, my_hand_str, opp_hand_str, ",".join(deck), next_turn, g_id), commit=True)

    await c.message.delete()
    if "🌈" in played_card and "➕" not in played_card:
        await ask_color(c.from_user.id, g_id)
    else:
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)

# 4. زر الصيد (🚨 صيده!)
@router.callback_query(F.data.startswith("op_catch_"))
async def on_catch(c: types.CallbackQuery):
    g_id = int(c.data.split("_")[2])
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    # من الذي يتم صيده؟ (الذي ليس هو صاحب النقرة ولديه ورقة واحدة)
    is_p1_catching = (int(c.from_user.id) == int(game['p1_id']))
    victim_id = game['p2_id'] if is_p1_catching else game['p1_id']
    victim_hand = (game['p2_hand'] if is_p1_catching else game['p1_hand']).split(",")
    deck = game['deck'].split(",")
    
    if len(victim_hand) == 1:
        victim_hand.extend([deck.pop(0), deck.pop(0)]) # عقوبة سحب ورقتين
        db_query(f"UPDATE active_games SET {'p2_hand' if is_p1_catching else 'p1_hand'}=%s, deck=%s WHERE game_id=%s",
                 (",".join(victim_hand), ",".join(deck), g_id), commit=True)
        await c.answer("🚨 فقسته! سحبته ورقتين عقوبة.")
        await bot.send_message(victim_id, "🚨 خصمك صادك! سحبت ورقتين لأنك لم تقل أونو.")
        await c.message.delete()
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)

# 5. زر الأونو (📢 أونو!)
@router.callback_query(F.data.startswith("op_uno_"))
async def on_uno(c: types.CallbackQuery):
    g_id = int(c.data.split("_")[2])
    is_p1 = (int(c.from_user.id) == int(db_query("SELECT p1_id FROM active_games WHERE game_id=%s", (g_id,))[0]['p1_id']))
    db_query(f"UPDATE active_games SET {'p1_uno' if is_p1 else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)
    await c.answer("📢 أمنت نفسك! قلت أونو.")
    await c.message.delete()
    await send_player_hand(c.from_user.id, g_id)

# (بقية الدوال: on_draw, start_random, ask_color تبقى كما هي)
