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

# --- 1. محرك الأوراق (124 ورقة) ---
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    for j in ["🌈", "🌈➕1", "🌈➕2", "🌈➕4"]:
        deck.extend([j] * 4)
    random.shuffle(deck)
    return deck

def sort_uno_hand(hand):
    color_order = {"🔴": 1, "🔵": 2, "🟡": 3, "🟢": 4, "🌈": 5}
    def sort_key(card):
        color_emoji = card[0]; rank = color_order.get(color_emoji, 99)
        return (rank, card)
    return sorted(hand, key=sort_key)

# --- 2. دالة إرسال اليد (المسح القسري) ---
async def send_player_hand(user_id, game_id, old_msg_id=None, extra_text=""):
    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    is_p1 = (int(user_id) == int(game['p1_id']))

    db_msg_id = game['p1_last_msg'] if is_p1 else game['p2_last_msg']
    target_to_delete = old_msg_id if old_msg_id else db_msg_id
    if target_to_delete and int(target_to_delete) > 0:
        try: await bot.delete_message(user_id, target_to_delete)
        except: pass

    p1_info = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (game['p1_id'],))[0]
    p2_info = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (game['p2_id'],))[0]
    my_info = p1_info if is_p1 else p2_info
    opp_info = p2_info if is_p1 else p1_info
    
    my_hand = sort_uno_hand([c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c])
    opp_count = len([c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c])
    
    is_my_turn = (int(game['turn']) == int(user_id))
    
    # السحب التلقائي
    if is_my_turn:
        top = game['top_card']
        has_playable = any(("🌈" not in c and (c[0] == top[0] or (len(c.split()) > 1 and len(top.split()) > 1 and c.split()[-1] == top.split()[-1]))) for c in my_hand)
        if not has_playable and not any("🌈" in c for c in my_hand):
            return await auto_draw(user_id, game_id)

    turn_text = "🟢 **دورك الآن!**" if is_my_turn else f"⏳ دور: **{opp_info['player_name']}**"
    status_text = f"\n\n🔔 **تنبيه:** {extra_text.replace('الخصم', opp_info['player_name'])}" if extra_text else ""
    
    text = (f"👤 **{opp_info['player_name']}**: ({opp_count}) أوراق\n"
            f"👤 **{my_info['player_name']} (أنت)**: ({len(my_hand)}) أوراق\n"
            f"━━━━━━━━━━━━━━\n"
            f"{turn_text}\n"
            f"🃏 المكشوفة: `{game['top_card']}`\n"
            f"━━━━━━━━━━━━━━"
            f"{status_text}")

    kb = []
    row = []
    for card in my_hand:
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{card}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    
    if len(my_hand) == 2 and is_my_turn:
        kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"u_{game_id}")])
    
    opp_uno_secured = game['p2_uno'] if is_p1 else game['p1_uno']
    if opp_count == 1 and not opp_uno_secured:
        kb.append([InlineKeyboardButton(text=f"🚨 صيد {opp_info['player_name']}!", callback_data=f"c_{game_id}")])

    try:
        sent = await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        col = "p1_last_msg" if is_p1 else "p2_last_msg"
        db_query(f"UPDATE active_games SET {col} = %s WHERE game_id = %s", (sent.message_id, game_id), commit=True)
    except: pass

# --- 3. السحب التلقائي ---
async def auto_draw(user_id, game_id):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    deck = game['deck'].split(","); hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    top = game['top_card']
    new_c = deck.pop(0); hand.append(new_c)
    can_p = ("🌈" in new_c or new_c[0] == top[0] or (len(new_c.split()) > 1 and len(top.split()) > 1 and new_c.split()[-1] == top.split()[-1]))
    nt = user_id if can_p else opp_id
    db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", (",".join(hand), ",".join(deck), nt, game_id), commit=True)
    await send_player_hand(user_id, game_id, None, f"📥 سحبتلك ({new_c})")
    if nt == opp_id: await send_player_hand(opp_id, game_id, None, "الخصم سحب وما رهمت.. دورك!")

# --- 4. منطق اللعب (الجوكر المرتد) ---
@router.callback_query(F.data.startswith("p_"))
async def process_play(c: types.CallbackQuery):
    _, g_id, played_card = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")

    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    deck = game['deck'].split(","); top_card = game['top_card']
    my_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']

    # فحص غش الجوكر
    has_normal_playable = any(("🌈" not in h and (h[0] == top_card[0] or (len(h.split()) > 1 and len(top_card.split()) > 1 and h.split()[-1] == top_card.split()[-1]))) for h in my_hand)
    
    if "🌈" in played_card and has_normal_playable:
        # عقوبة الارتداد: الورقة تبقى بيدك وتنسحب فوكاها عقوبة
        penalty = 6 if "➕4" in played_card else (4 if "➕2" in played_card else (3 if "➕1" in played_card else 3))
        for _ in range(penalty): 
            if deck: my_hand.append(deck.pop(0))
        
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), g_id), commit=True)
        await c.answer(f"⚠️ غش! الورقة ارتدت ليدك وتعاقبت بـ {penalty} أوراق.", show_alert=True)
        await bot.send_message(opp_id, f"🚨 {my_name} حاول يغش بالجوكر! الورقة ارتدت ليده وعاقبته بـ {penalty} أوراق.")
        return await send_player_hand(c.from_user.id, g_id, c.message.message_id, f"حاولت تغش.. ارتدت {played_card} ليدك وتعاقبت!")

    # فحص إمكانية اللعب
    can_play = ("🌈" in played_card or played_card[0] == top_card[0] or (len(played_card.split()) > 1 and len(top_card.split()) > 1 and played_card.split()[-1] == top_card.split()[-1]))
    if not can_play:
        for _ in range(2): 
            if deck: my_hand.append(deck.pop(0))
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), opp_id, g_id), commit=True)
        return await send_player_hand(c.from_user.id, g_id, c.message.message_id, "لعبت خطأ.. ارتدت الورقة ليدك وتعاقبت بـ 2 وضاع دورك!")

    # إذا اللعب نظامي، نزيل الورقة ونكمل
    my_hand.remove(played_card); next_turn = opp_id
    opp_hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(",")

    if "➕" in played_card:
        val = int(played_card[-1]); 
        for _ in range(val): 
            if deck: opp_hand.append(deck.pop(0))
        next_turn = opp_id # السحب الملون يحول الدور تلقائياً
    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = c.from_user.id

    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
             (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)

    if not my_hand:
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        try: await c.message.delete()
        except: pass
        await bot.send_message(c.from_user.id, "🏆 مبروك الفوز!"); return

    if played_card == "🌈":
        await send_player_hand(opp_id, g_id, None, f"الخصم لعب {played_card}")
        await asyncio.sleep(0.5)
        try: await c.message.delete()
        except: pass
        await ask_color(c.from_user.id, g_id)
    else:
        await send_player_hand(c.from_user.id, g_id, c.message.message_id, f"لعبت {played_card}")
        await send_player_hand(opp_id, g_id, None, f"الخصم لعب {played_card}")

# --- 5. أونو وصيد ---
@router.callback_query(F.data.startswith("u_"))
async def process_uno(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]; game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id'])); opp_id = game['p2_id'] if is_p1 else game['p1_id']
    db_query(f"UPDATE active_games SET {'p1_uno' if is_p1 else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)
    await bot.send_photo(c.from_user.id, photo=IMG_UNO_SAFE_ME); await bot.send_photo(opp_id, photo=IMG_UNO_SAFE_OPP)
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, "قلت أونو!")

@router.callback_query(F.data.startswith("c_"))
async def process_catch(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]; game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id'])); victim_id = game['p2_id'] if is_p1 else game['p1_id']
    if (game['p2_uno'] if is_p1 else game['p1_uno']): return await c.answer("❌ مأمن نفسه!")
    hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(","); deck = game['deck'].split(",")
    for _ in range(2): 
        if deck: hand.append(deck.pop(0))
    db_query(f"UPDATE active_games SET {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(hand), ",".join(deck), g_id), commit=True)
    await bot.send_photo(c.from_user.id, photo=IMG_CATCH_SUCCESS); await bot.send_photo(victim_id, photo=IMG_CATCH_PENALTY)
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, "صيد ناجح!"); await send_player_hand(victim_id, g_id, None, "صادك الخصم!")

# --- البداية والألوان ---
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    if waiting:
        g = waiting[0]; deck = generate_deck()
        p1_h, p2_h, top = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)], deck.pop()
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s, p1_last_msg=0, p2_last_msg=0 WHERE game_id=%s''',
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        await callback.message.edit_text("✅ تم الربط!"); await send_player_hand(g['p1_id'], g['game_id']); await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم...")

async def ask_color(u_id, g_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"sc_{g_id}_🔴"), InlineKeyboardButton(text="🔵", callback_data=f"sc_{g_id}_🔵")],
          [InlineKeyboardButton(text="🟡", callback_data=f"sc_{g_id}_🟡"), InlineKeyboardButton(text="🟢", callback_data=f"sc_{g_id}_🟢")]]
    await bot.send_message(u_id, "🌈 اختر اللون المطلوب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sc_"))
async def set_color_logic(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_"); game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    opp_id = game['p2_id'] if int(c.from_user.id) == int(game['p1_id']) else game['p1_id']
    db_query("UPDATE active_games SET top_card=%s, turn=%s WHERE game_id=%s", (f"{col} (🌈)", opp_id, g_id), commit=True)
    await c.message.delete(); await send_player_hand(c.from_user.id, g_id, None, f"اخترت اللون {col}"); await send_player_hand(opp_id, g_id, None, f"الخصم اختار اللون {col}")
