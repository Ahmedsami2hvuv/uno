import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import (
    bot, 
    IMG_UNO_SAFE_ME, 
    IMG_UNO_SAFE_OPP, 
    IMG_CATCH_SUCCESS, 
    IMG_CATCH_PENALTY
)

router = Router()

# --- 1. توليد الأوراق ---
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    deck.extend(["🌈"] * 4 + ["🌈➕1"] * 4 + ["🌈➕2"] * 4 + ["🌈➕4"] * 4)
    random.shuffle(deck)
    return deck

# --- 2. واجهة اللعب وتنظيف الرسائل ---
async def send_player_hand(user_id, game_id, old_msg_id=None):
    if old_msg_id:
        try: await bot.delete_message(user_id, old_msg_id)
        except: pass

    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    turn_text = "🟢 دورك الآن!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم"
    
    text = f"🃏 المكشوفة: `{game['top_card']}`\n👤 الخصم: {len(opp_hand)} أوراق\n━━━━━━━━━━━━━━\n{turn_text}"
    kb = []
    row = []
    for i, card in enumerate(my_hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{i}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"d_{game_id}")])
    
    if len(my_hand) == 2:
        kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"u_{game_id}")])
    
    opp_uno = game['p2_uno'] if is_p1 else game['p1_uno']
    if len(opp_hand) == 1 and not opp_uno:
        kb.append([InlineKeyboardButton(text="🚨 صيده!", callback_data=f"c_{game_id}")])

    sent = await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    return sent.message_id

# --- 3. اللعب العشوائي (الربط) ---
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
        await callback.message.edit_text("🔎 جاري البحث عن خصم...")

# --- 4. منطق لعب الورقة والعقوبات ---
@router.callback_query(F.data.startswith("p_"))
async def process_play(c: types.CallbackQuery):
    _, g_id, idx = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك! ⏳")

    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    opp_hand = [h for h in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if h]
    deck = [d for d in game['deck'].split(",") if d]
    played_card = my_hand[int(idx)]
    top_card = game['top_card']

    # أ. فحص الجوكر غير القانوني
    if "🌈" in played_card:
        has_match = any(h[0] == top_card[0] for h in my_hand if "🌈" not in h)
        if has_match:
            val = 4 if "➕4" in played_card else (2 if "➕2" in played_card else (1 if "➕1" in played_card else 0))
            penalty = 2 + val
            for _ in range(penalty): 
                if deck: my_hand.append(deck.pop(0))
            await c.answer(f"❌ لعب غير قانوني! لديك لون يطابق الأرض. عوقبت بـ {penalty} أوراق.", show_alert=True)
            db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), g_id), commit=True)
            await bot.send_message(opp_id, f"🚨 خصمك حاول لعب جوكر غير قانوني وعوقب بسحب {penalty} أوراق!")
            return await send_player_hand(c.from_user.id, g_id, c.message.message_id)

    # ب. فحص الورقة الخطأ
    can_play = ("🌈" in played_card or "🌈" in top_card or played_card[0] == top_card[0] or (len(played_card.split()) > 1 and len(top_card.split()) > 1 and played_card.split()[-1] == top_card.split()[-1]))
    if not can_play:
        await c.answer("❌ ورقة خطأ! عقوبة سحب ورقتين والدور يبقى لك.", show_alert=True)
        for _ in range(2): 
            if deck: my_hand.append(deck.pop(0))
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), g_id), commit=True)
        return await send_player_hand(c.from_user.id, g_id, c.message.message_id)

    # تنفيذ اللعب الصحيح
    my_hand.pop(int(idx))

    # فحص الفوز
    if not my_hand:
        db_query("UPDATE users SET online_points = online_points + 10 WHERE user_id = %s", (c.from_user.id,), commit=True)
        pts = db_query("SELECT online_points FROM users WHERE user_id = %s", (c.from_user.id,))[0]['online_points']
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        kb = [[InlineKeyboardButton(text="🏠 القائمة", callback_data="home"), InlineKeyboardButton(text="🎲 مرة أخرى", callback_data="mode_random")]]
        await c.message.delete()
        await bot.send_message(c.from_user.id, f"🏆 مبروك! فزت بـ 10 نقاط. رصيدك: {pts}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await bot.send_message(opp_id, f"💀 خسرت! الخصم فاز وجمع {pts} نقطة.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # الأوراق الخاصة
    next_turn = opp_id
    if "➕" in played_card:
        val = 1 if "➕1" in played_card else (2 if "➕2" in played_card else 4)
        for _ in range(val): 
            if deck: opp_hand.append(deck.pop(0))
        next_turn = c.from_user.id
        await bot.send_message(opp_id, f"📥 سحبك خصمك {val} أوراق وبقي الدور عنده!")
    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = c.from_user.id
        await bot.send_message(opp_id, "🚫 خصمك قام بإيقاف دورك!")

    db_query(f'''UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, 
                {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s, p1_uno=FALSE, p2_uno=FALSE WHERE game_id=%s''', 
             (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)
    
    if "🌈" in played_card and "➕" not in played_card:
        await ask_color(c.from_user.id, g_id)
    else:
        await send_player_hand(game['p1_id'], g_id, c.message.message_id if is_p1 else None)
        await send_player_hand(game['p2_id'], g_id, c.message.message_id if not is_p1 else None)

# --- 5. نظام الصور (أونو وصيد) ---
@router.callback_query(F.data.startswith("u_"))
async def process_uno(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    db_query(f"UPDATE active_games SET {'p1_uno' if True else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    opp_id = game['p2_id'] if int(c.from_user.id) == int(game['p1_id']) else game['p1_id']
    
    await bot.send_photo(c.from_user.id, photo=IMG_UNO_SAFE_ME)
    await bot.send_photo(opp_id, photo=IMG_UNO_SAFE_OPP)
    await send_player_hand(c.from_user.id, g_id, c.message.message_id)

@router.callback_query(F.data.startswith("c_"))
async def process_catch(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    victim_id = game['p2_id'] if is_p1 else game['p1_id']
    hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(",")
    deck = game['deck'].split(",")
    
    hand.extend([deck.pop(0), deck.pop(0)])
    db_query(f"UPDATE active_games SET {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(hand), ",".join(deck), g_id), commit=True)
    
    await bot.send_photo(c.from_user.id, photo=IMG_CATCH_SUCCESS)
    await bot.send_photo(victim_id, photo=IMG_CATCH_PENALTY)
    await send_player_hand(game['p1_id'], g_id, c.message.message_id if is_p1 else None)
    await send_player_hand(game['p2_id'], g_id, c.message.message_id if not is_p1 else None)

@router.callback_query(F.data.startswith("d_"))
async def process_draw(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    deck = game['deck'].split(","); hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    
    new_c = deck.pop(0); hand.append(new_c)
    t = game['top_card']
    can_p = ("🌈" in new_c or new_c[0] == t[0] or new_c.split()[-1] == t.split()[-1])
    nt = c.from_user.id if can_p else (game['p2_id'] if is_p1 else game['p1_id'])
    
    db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
             (",".join(hand), ",".join(deck), nt, g_id), commit=True)
    await send_player_hand(game['p1_id'], g_id, c.message.message_id if is_p1 else None)
    await send_player_hand(game['p2_id'], g_id, c.message.message_id if not is_p1 else None)

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
