import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import (
    bot, IMG_UNO_SAFE_ME, IMG_UNO_SAFE_OPP, 
    IMG_CATCH_SUCCESS, IMG_CATCH_PENALTY
)

router = Router()

# --- 1. محرك الأوراق (الحسبة الدقيقة) ---
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        for n in range(0, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    for j in [("🌈", 50), ("🌈➕1", 10), ("🌈➕2", 30), ("🌈➕4", 50)]:
        deck.extend([j[0]] * 4)
    random.shuffle(deck)
    return deck

def get_card_points(card):
    if "🌈" in card:
        if "➕4" in card or card == "🌈": return 50
        if "➕2" in card: return 30
        return 10
    if any(x in card for x in ["🚫", "🔄", "➕2"]): return 20
    try:
        return int(card.split()[-1])
    except:
        return 5

def sort_uno_hand(hand):
    color_order = {"🔴": 1, "🔵": 2, "🟡": 3, "🟢": 4, "🌈": 5}
    return sorted(hand, key=lambda x: (color_order.get(x[0], 99), x))

# --- 2. دالة إرسال اليد والسيطرة ---
async def send_player_hand(user_id, game_id, old_msg_id=None, extra_text="", is_locked=False):
    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    is_my_turn = (int(game['turn']) == int(user_id))
    
    p1_info = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (game['p1_id'],))[0]
    p2_info = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (game['p2_id'],))[0]
    my_info = p1_info if is_p1 else p2_info
    opp_info = p2_info if is_p1 else p1_info
    
    my_hand = sort_uno_hand([c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c.strip()])
    opp_count = len([c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c.strip()])

    if is_my_turn and not is_locked and "🌈" not in game['top_card']:
        top = game['top_card']
        has_move = any(("🌈" in c or c[0] == top[0] or (len(c.split()) > 1 and len(top.split()) > 1 and c.split()[-1] == top.split()[-1])) for c in my_hand)
        if not has_move:
            return await auto_draw(user_id, game_id)

    db_msg_id = game['p1_last_msg'] if is_p1 else game['p2_last_msg']
    target_to_delete = old_msg_id if old_msg_id else db_msg_id
    if target_to_delete and int(target_to_delete) > 0:
        try: await bot.delete_message(user_id, target_to_delete)
        except: pass

    turn_marker = "🟢 **دورك الآن!**" if is_my_turn else f"⏳ دور: **{opp_info['player_name']}**"
    if is_locked: turn_marker = "⏳ **انتظر رد الخصم على التحدي...**"
    if is_my_turn and "🌈" in game['top_card']: turn_marker = "🔥 **دورك (سيطرة)! نزل أي ورقة**"

    text = (f"👤 **{opp_info['player_name']}**: ({opp_count}) أوراق\n"
            f"👤 **{my_info['player_name']} (أنت)**: ({len(my_hand)}) أوراق | 🏅: `{my_info['online_points']}`\n"
            f"━━━━━━━━━━━━━━\n"
            f"{turn_marker}\n"
            f"🃏 المكشوفة: `{game['top_card']}`\n"
            f"━━━━━━━━━━━━━━\n"
            f"🔔 {extra_text.replace('الخصم', opp_info['player_name']) if extra_text else ''}")

    # تجهيز الأزرار
    kb = []
    row = []
    for card in my_hand:
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{card}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    
    # زر أونو يظهر فقط في دورك وإذا عندك ورقتين (عشان تمن نفسها قبل ما تنزل الورقة القبل أخيرة)
    if is_my_turn and not is_locked and len(my_hand) == 2:
        kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"u_{game_id}")])

    # 🔥 زر الصيدة: يظهر إذا الخصم عنده ورقة واحدة وما مأمن نفسه (بناءً على الداتا بيس)
    opp_is_uno = game['p2_uno'] if is_p1 else game['p1_uno']
    if opp_count == 1 and not opp_is_uno:
        kb.append([InlineKeyboardButton(text=f"🚨 صيد {opp_info['player_name']}!", callback_data=f"c_{game_id}")])

    try:
        sent = await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        col = "p1_last_msg" if is_p1 else "p2_last_msg"
        db_query(f"UPDATE active_games SET {col} = %s WHERE game_id = %s", (sent.message_id, game_id), commit=True)
    except Exception:
        pass

# --- 3. دالة نهاية اللعبة وحساب النقاط ---
async def end_game_logic(winner_id, loser_id, game_id):
    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    
    is_p1_loser = (int(loser_id) == int(game['p1_id']))
    loser_hand_raw = game['p1_hand'] if is_p1_loser else game['p2_hand']
    loser_hand = [h.strip() for h in loser_hand_raw.split(",") if h.strip()]
    
    total_round_points = sum(get_card_points(c) for c in loser_hand)
    if total_round_points == 0: total_round_points = 10
    
    db_query("UPDATE users SET online_points = online_points + %s WHERE user_id = %s", (total_round_points, winner_id), commit=True)
    
    winner_data = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (winner_id,))[0]
    loser_data = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (loser_id,))[0]
    
    db_query("DELETE FROM active_games WHERE game_id = %s", (game_id,), commit=True)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 جولة جديدة", callback_data="mode_random")],
        [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
    ])
    
    win_text = (f"🏆 **مبروك الفوز يا بطل!**\n\n💰 نقاط الجولة: `+{total_round_points}`\n🏅 رصيدك الكلي: `{winner_data['online_points']}`\n━━━━━━━━━━━━━━\n👤 الخصم: {loser_data['player_name']}")
    lose_text = (f"💀 **هاردلك! خسر اللعبة أمام {winner_data['player_name']}**\n\n📉 النقاط المسحوبة: `{total_round_points}`\n🏅 رصيدك الكلي: `{loser_data['online_points']}`")

    try:
        await bot.send_message(winner_id, win_text, reply_markup=kb)
        await bot.send_message(loser_id, lose_text, reply_markup=kb)
    except: pass

@router.callback_query(F.data == "home")
async def go_home(c: types.CallbackQuery):
    # هنا نستدعي الدالة اللي تفتح القائمة الرئيسية (تأكد من اسم الملف والدالة عندك)
    from handlers.common import start_command 
    await start_command(c.message) 
    try: await c.message.delete()
    except: pass

# --- 4. نظام السحب التلقائي ---
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
    await send_player_hand(user_id, game_id, None, f"📥 ما عندك، سحبتلك ({new_c})")
    if nt == opp_id: await send_player_hand(opp_id, game_id, None, "الخصم سحب وما رهمت.. دورك!")

# --- 5. البداية والربط ---
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    if waiting:
        g = waiting[0]
        deck = generate_deck()
        p1_h, p2_h, top = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)], deck.pop()
        while "🌈" in top:
            deck.append(top); random.shuffle(deck); top = deck.pop()
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s, p1_last_msg=0, p2_last_msg=0 WHERE game_id=%s''',
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        await callback.message.edit_text("✅ تم إيجاد خصم!")
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status, p1_last_msg, p2_last_msg) VALUES (%s, 'waiting', 0, 0)", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم...")

# --- 6. منطق اللعب ---
@router.callback_query(F.data.startswith("p_"))
async def process_play(c: types.CallbackQuery):
    _, g_id, played_card = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")

    is_p1 = (int(c.from_user.id) == int(game['p1_id'])); opp_id = game['p2_id'] if is_p1 else game['p1_id']
    my_hand = [h.strip() for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h.strip()]
    deck = [d.strip() for d in game['deck'].split(",") if d.strip()]; top_card = game['top_card']
    
    is_dominating = "🌈" in top_card
    if not is_dominating:
        can_p = ("🌈" in played_card or played_card[0] == top_card[0] or (len(played_card.split()) > 1 and len(top_card.split()) > 1 and played_card.split()[-1] == top_card.split()[-1]))
        if not can_p:
            [my_hand.append(deck.pop(0)) for _ in range(2) if deck]
            db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), g_id), commit=True)
            return await send_player_hand(c.from_user.id, g_id, c.message.message_id, "لعبت غلط.. ارتدت وتعاقبت!")

    if "🌈" in played_card and not is_dominating:
        kb = [[InlineKeyboardButton(text="⚔️ تحدي", callback_data=f"chal_{g_id}_{played_card}"),
               InlineKeyboardButton(text="✅ لا أتحدى", callback_data=f"nochal_{g_id}_{played_card}")]]
        await send_player_hand(c.from_user.id, g_id, c.message.message_id, f"نزلت {played_card}.. انتظر الخصم.", is_locked=True)
        return await bot.send_message(opp_id, f"🚨 الخصم نزل `{played_card}`! تتحداه؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

    my_hand.remove(played_card)
    if not my_hand:
        return await end_game_logic(c.from_user.id, opp_id, g_id)

    next_turn = opp_id
    if "➕" in played_card:
        val = int(played_card[-1]); opp_h = [h.strip() for h in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if h.strip()]
        [opp_h.append(deck.pop(0)) for _ in range(val) if deck]
        db_query(f"UPDATE active_games SET {'p2_hand' if is_p1 else 'p1_hand'}=%s WHERE game_id=%s", (",".join(opp_h), g_id), commit=True)
        next_turn = c.from_user.id
    elif any(x in played_card for x in ["🚫", "🔄"]): next_turn = c.from_user.id

    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", (played_card, ",".join(my_hand), ",".join(deck), next_turn, g_id), commit=True)
    await send_player_hand(c.from_user.id, g_id, c.message.message_id); await send_player_hand(opp_id, g_id, None)

# --- 7. التحدي ---
@router.callback_query(F.data.startswith("chal_") | F.data.startswith("nochal_"))
async def handle_challenge(c: types.CallbackQuery):
    data = c.data.split("_"); is_chal = (data[0] == "chal"); g_id = data[1]; played_card = data[2]
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    challenger_id = c.from_user.id
    is_p2_chal = (int(challenger_id) == int(game['p2_id']))
    player_id = game['p1_id'] if is_p2_chal else game['p2_id']
    is_p1_player = (int(player_id) == int(game['p1_id']))

    p_hand = [h.strip() for h in (game['p1_hand'] if is_p1_player else game['p2_hand']).split(",") if h.strip()]
    o_hand = [h.strip() for h in (game['p2_hand'] if is_p1_player else game['p1_hand']).split(",") if h.strip()]
    deck = [d.strip() for d in game['deck'].split(",") if d.strip()]; top_before = game['top_card']
    
    is_cheat = any(("🌈" not in h and (h[0] == top_before[0] or (len(h.split()) > 1 and h.split()[-1] == top_before.split()[-1]))) for h in p_hand if h != played_card)
    penalty = 6 if "➕4" in played_card else (4 if "➕2" in played_card else 3)

    if is_chal:
        if is_cheat:
            [p_hand.append(deck.pop(0)) for _ in range(penalty) if deck]
            db_query(f"UPDATE active_games SET {'p1_hand' if is_p1_player else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", (",".join(p_hand), ",".join(deck), player_id, g_id), commit=True)
            await send_player_hand(player_id, g_id, None, "❌ انكشفت وتعاقبت!"); await send_player_hand(challenger_id, g_id, c.message.message_id, "🎯 كفشته!")
        else:
            [o_hand.append(deck.pop(0)) for _ in range(penalty + 2) if deck]
            if played_card in p_hand: p_hand.remove(played_card)
            db_query(f"UPDATE active_games SET {'p1_hand' if is_p1_player else 'p2_hand'}=%s, {'p2_hand' if is_p1_player else 'p1_hand'}=%s, deck=%s, top_card=%s, turn=%s WHERE game_id=%s", (",".join(p_hand), ",".join(o_hand), ",".join(deck), played_card, player_id, g_id), commit=True)
            await send_player_hand(player_id, g_id, None, "✅ صدقت والخصم تعاقب!"); await send_player_hand(challenger_id, g_id, c.message.message_id, "❌ فشلت وتعاقبت!")
    else:
        if played_card in p_hand: p_hand.remove(played_card)
        s_val = int(played_card[-1]) if "➕" in played_card else 0
        [o_hand.append(deck.pop(0)) for _ in range(s_val) if deck]
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1_player else 'p2_hand'}=%s, {'p2_hand' if is_p1_player else 'p1_hand'}=%s, deck=%s, top_card=%s, turn=%s WHERE game_id=%s", (",".join(p_hand), ",".join(o_hand), ",".join(deck), played_card, player_id, g_id), commit=True)
        await send_player_hand(player_id, g_id, None, "✅ الخصم ما تحدى!"); await send_player_hand(challenger_id, g_id, c.message.message_id, "لعب جوكر وما تحديت.")

    if not p_hand: await end_game_logic(player_id, challenger_id, g_id)
    elif played_card == "🌈" and not (is_chal and is_cheat): await ask_color(player_id, g_id)

# --- 8. أونو وصيد وألوان ---
@router.callback_query(F.data.startswith("u_"))
async def process_uno(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    
    # تحديث حالة الأمان للاعب في قاعدة البيانات
    col = "p1_uno" if is_p1 else "p2_uno"
    db_query(f"UPDATE active_games SET {col} = TRUE WHERE game_id=%s", (g_id,), commit=True)
    
    await c.answer("📢 أونو! أمنت نفسك من الصيدة.")
    
    # إرسال تنبيه بالصور (اختياري)
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    try:
        await bot.send_photo(c.from_user.id, photo=IMG_UNO_SAFE_ME)
        await bot.send_photo(opp_id, photo=IMG_UNO_SAFE_OPP)
    except: pass

    # تحديث اليد لإخفاء زر الأونو بعد الضغط عليه
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, "صحت أونو! أمنت نفسك.")

@router.callback_query(F.data.startswith("c_"))
async def process_catch(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    victim_id = game['p2_id'] if is_p1 else game['p1_id']
    
    # جلب يد الضحية الحقيقية
    v_hand_raw = game['p2_hand'] if is_p1 else game['p1_hand']
    v_hand = [h.strip() for h in v_hand_raw.split(",") if h.strip()]
    v_is_uno = game['p2_uno'] if is_p1 else game['p1_uno']

    # التأكد من شروط الصيد (ورقة واحدة وغير مؤمن)
    if len(v_hand) != 1 or v_is_uno:
        return await c.answer("❌ الخصم مأمن نفسه أو أوراقه مو وحدة!")

    # العقوبة: سحب 2
    deck = game['deck'].split(",")
    for _ in range(2):
        if deck: v_hand.append(deck.pop(0))
    
    # تحديث الداتا بيس (تصفير الأونو للضحية ضروري)
    v_col_hand = "p2_hand" if is_p1 else "p1_hand"
    v_col_uno = "p2_uno" if is_p1 else "p1_uno"
    db_query(f"UPDATE active_games SET {v_col_hand}=%s, {v_col_uno}=FALSE, deck=%s WHERE game_id=%s", 
             (",".join(v_hand), ",".join(deck), g_id), commit=True)
    
    await c.answer("🎯 صيد ناجح!")
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, "صدت الخصم! تعاقب بورقتين.")
    await send_player_hand(victim_id, g_id, None, "صادك الخصم لأنك ما صحت أونو!")

async def ask_color(u_id, g_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"sc_{g_id}_🔴"), InlineKeyboardButton(text="🔵", callback_data=f"sc_{g_id}_🔵")],
          [InlineKeyboardButton(text="🟡", callback_data=f"sc_{g_id}_🟡"), InlineKeyboardButton(text="🟢", callback_data=f"sc_{g_id}_🟢")]]
    await bot.send_message(u_id, "🌈 اختر اللون المطلوب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sc_"))
async def set_color_logic(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_"); game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    opp_id = game['p2_id'] if int(c.from_user.id) == int(game['p1_id']) else game['p1_id']
    db_query("UPDATE active_games SET top_card=%s, turn=%s WHERE game_id=%s", (f"{col} (🌈)", opp_id, g_id), commit=True)
    await c.message.delete(); await send_player_hand(c.from_user.id, g_id, None, f"اخترت {col}"); await send_player_hand(opp_id, g_id, None, f"الخصم اختار {col}")
