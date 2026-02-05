import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك توليد الأوراق
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
    game_data = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not game_data: return
    game = game_data[0]
    
    is_p1 = (int(user_id) == int(game['p1_id']))
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    
    my_uno = game['p1_uno'] if is_p1 else game['p2_uno']
    opp_uno = game['p2_uno'] if is_p1 else game['p1_uno']

    turn_text = "🟢 دورك الآن!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم..."
    text = (f"🃏 المكشوفة: `{game['top_card']}`\n"
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
    
    control = [InlineKeyboardButton(text="📥 سحب", callback_data=f"op_draw_{game_id}")]
    
    # يظهر زر أونو إذا بقيت ورقة واحدة ولم تضغط عليه
    if len(my_hand) == 1 and not my_uno:
        control.append(InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}"))
    
    # يظهر زر صيده للخصم إذا اللاعب عنده ورقة وحدة وما قال أونو
    if len(opp_hand) == 1 and not opp_uno:
        control.append(InlineKeyboardButton(text="🚨 صيده!", callback_data=f"op_catch_{game_id}"))
    
    kb.append(control)
    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. محرك البحث عن لاعب (Matchmaking)
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    # إنهاء أي انتظار قديم للاعب
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        g = waiting[0]
        deck = generate_deck()
        p1_h = [deck.pop() for _ in range(7)]
        p2_h = [deck.pop() for _ in range(7)]
        top = deck.pop()
        
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s 
                    WHERE game_id=%s''', 
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        
        await callback.answer("✅ وجدنا خصماً!")
        await callback.message.edit_text("✅ بدأت اللعبة!")
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.answer("🔎 جاري البحث...")
        await callback.message.edit_text("🔎 جاري البحث عن خصم أونلاين...")

# 4. منطق اللعب (قوانين الأكشن والفوز والسحب للخصم)
@router.callback_query(F.data.startswith("op_play_"))
async def process_play(c: types.CallbackQuery):
    g_id = int(c.data.split("_")[2])
    idx = int(c.data.split("_")[3])
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    if int(c.from_user.id) != int(game['turn']):
        return await c.answer("مو دورك! ⏳", show_alert=True)

    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    opp_hand = [h for h in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if h]
    played_card = my_hand.pop(idx)
    deck = game['deck'].split(",")

    # 🏆 فحص الفوز
    if len(my_hand) == 0:
        db_query("UPDATE users SET online_points = online_points + 10 WHERE user_id = %s", (c.from_user.id,), commit=True)
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        await c.message.delete()
        await c.message.answer("🏆 مبروك! فزت باللعبة وحصلت على 10 نقاط.")
        await bot.send_message(game['p2_id'] if is_p1 else game['p1_id'], "💀 خسرتم اللعبة! حظاً أوفر.")
        return

    # ⚡ قوانين الأوراق الخاصة
    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    
    # ➕ أوراق السحب (تسحب للخصم وتخلي الدور عندك)
    if "➕" in played_card:
        plus = 1 if "➕1" in played_card else (2 if "➕2" in played_card else 4)
        for _ in range(plus):
            if deck: opp_hand.append(deck.pop(0))
        next_turn = c.from_user.id
        await c.answer(f"🔥 سحبت خصمك {plus} أوراق!")

    # 🚫 المنع والتبديل (يرجع الدور لك)
    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = c.from_user.id
        await c.answer("🚫 منعت الخصم والدور بقى عندك!")

    # تحديث الداتا بيس
    my_h_str = ",".join(my_hand)
    opp_h_str = ",".join(opp_hand)
    db_query(f'''UPDATE active_games SET top_card=%s, 
                {'p1_hand' if is_p1 else 'p2_hand'}=%s, 
                {'p2_hand' if is_p1 else 'p1_hand'}=%s, 
                deck=%s, turn=%s, p1_uno=FALSE, p2_uno=FALSE WHERE game_id=%s''', 
             (played_card, my_h_str, opp_h_str, ",".join(deck), next_turn, g_id), commit=True)

    await c.message.delete()
    if "🌈" in played_card and "➕" not in played_card:
        await ask_color(c.from_user.id, g_id)
    else:
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)

# 5. زر الصيد والأونو والسحب
@router.callback_query(F.data.startswith("op_uno_"))
async def on_uno(c: types.CallbackQuery):
    g_id = int(c.data.split("_")[2])
    is_p1 = (int(c.from_user.id) == int(db_query("SELECT p1_id FROM active_games WHERE game_id=%s", (g_id,))[0]['p1_id']))
    db_query(f"UPDATE active_games SET {'p1_uno' if is_p1 else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)
    await c.answer("📢 أمنت نفسك!"); await c.message.delete(); await send_player_hand(c.from_user.id, g_id)

@router.callback_query(F.data.startswith("op_catch_"))
async def on_catch(c: types.CallbackQuery):
    g_id = int(c.data.split("_")[2])
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1_catching = (int(c.from_user.id) == int(game['p1_id']))
    victim_id = game['p2_id'] if is_p1_catching else game['p1_id']
    victim_h = (game['p2_hand'] if is_p1_catching else game['p1_hand']).split(",")
    deck = game['deck'].split(",")
    victim_h.extend([deck.pop(0), deck.pop(0)])
    db_query(f"UPDATE active_games SET {'p2_hand' if is_p1_catching else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(victim_h), ",".join(deck), g_id), commit=True)
    await c.answer("🚨 فقسته!"); await bot.send_message(victim_id, "🚨 خصمك صادك! سحبت ورقتين."); await c.message.delete(); await send_player_hand(game['p1_id'], g_id); await send_player_hand(game['p2_id'], g_id)

@router.callback_query(F.data.startswith("op_draw_"))
async def on_draw(c: types.CallbackQuery):
    g_id = int(c.data.split("_")[2])
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    deck = game['deck'].split(","); hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    new_c = deck.pop(0); hand.append(new_c)
    # فحص إذا الورقة المسحوبة ترهم
    can_p = ("🌈" in new_c or new_c[0] == game['top_card'][0] or (len(new_c.split())>1 and len(game['top_card'].split())>1 and new_c.split()[1] == game['top_card'].split()[1]))
    next_t = c.from_user.id if can_p else (game['p2_id'] if is_p1 else game['p1_id'])
    db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", (",".join(hand), ",".join(deck), next_t, g_id), commit=True)
    await c.message.delete(); await send_player_hand(game['p1_id'], g_id); await send_player_hand(game['p2_id'], g_id)

async def ask_color(user_id, game_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"sc_{game_id}_🔴"), InlineKeyboardButton(text="🔵", callback_data=f"sc_{game_id}_🔵")],
          [InlineKeyboardButton(text="🟡", callback_data=f"sc_{game_id}_🟡"), InlineKeyboardButton(text="🟢", callback_data=f"sc_{game_id}_🟢")]]
    await bot.send_message(user_id, "🌈 اختر اللون:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sc_"))
async def set_color_logic(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (int(g_id),))[0]
    next_p = game['p2_id'] if int(c.from_user.id) == int(game['p1_id']) else game['p1_id']
    db_query("UPDATE active_games SET top_card=%s, turn=%s WHERE game_id=%s", (f"{col} (🌈)", next_p, int(g_id)), commit=True)
    await c.message.delete(); await send_player_hand(game['p1_id'], g_id); await send_player_hand(game['p2_id'], g_id)
