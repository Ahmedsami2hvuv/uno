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

# --- 1. محرك الأوراق وترتيبها ---
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

def sort_uno_hand(hand):
    color_order = {"🔴": 1, "🔵": 2, "🟡": 3, "🟢": 4, "🌈": 5}
    def sort_key(card):
        color_emoji = card[0]
        rank = color_order.get(color_emoji, 99)
        return (rank, card)
    return sorted(hand, key=sort_key)

# --- 2. دالة إرسال اليد وتنظيف الشات (الجوهرة) ---
async def send_player_hand(user_id, game_id, old_msg_id=None, extra_text=""):
    # مسح الرسالة القديمة فوراً
    if old_msg_id:
        try: await bot.delete_message(user_id, old_msg_id)
        except: pass

    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    
    # جلب الأسماء الحقيقية
    p1_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (game['p1_id'],))[0]['player_name']
    p2_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (game['p2_id'],))[0]['player_name']

    is_p1 = (int(user_id) == int(game['p1_id']))
    my_name = p1_name if is_p1 else p2_name
    opp_name = p2_name if is_p1 else p1_name
    
    raw_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    my_hand = sort_uno_hand(raw_hand)
    opp_hand_count = len([c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c])
    
    # تنسيق النصوص والأسماء
    turn_text = "🟢 **دورك الآن!**" if int(game['turn']) == int(user_id) else f"⏳ دور: **{opp_name}**"
    formatted_extra = extra_text.replace("الخصم", f"**{opp_name}**")
    status_text = f"\n\n🔔 **تنبيه:** {formatted_extra}" if extra_text else ""
    
    text = (f"🃏 المكشوفة: `{game['top_card']}`\n"
            f"👤 **{opp_name}**: عنده ({opp_hand_count}) أوراق\n"
            f"━━━━━━━━━━━━━━\n"
            f"{turn_text}{status_text}")

    # بناء الكيبورد
    kb = []
    row = []
    for card in my_hand:
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{card}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"d_{game_id}")])
    if len(my_hand) == 2: kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"u_{game_id}")])
    
    opp_uno_secured = game['p2_uno'] if is_p1 else game['p1_uno']
    if opp_hand_count == 1 and not opp_uno_secured:
        kb.append([InlineKeyboardButton(text=f"🚨 صيد {opp_name}!", callback_data=f"c_{game_id}")])

    try:
        sent = await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        # حفظ رقم الرسالة الجديدة لمسحها لاحقاً
        col = "p1_last_msg" if is_p1 else "p2_last_msg"
        db_query(f"UPDATE active_games SET {col} = %s WHERE game_id = %s", (sent.message_id, game_id), commit=True)
        return sent.message_id
    except: return None

# --- 3. البداية والربط ---
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
        
        p1_info = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (g['p1_id'],))[0]
        p2_info = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (user_id,))[0]

        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s WHERE game_id=%s''',
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        
        await bot.send_message(g['p1_id'], f"✅ تم ربطك مع: **{p2_info['player_name']}** (نقاطه: {p2_info['online_points']})")
        await callback.message.edit_text(f"✅ تم ربطك مع: **{p1_info['player_name']}** (نقاطه: {p1_info['online_points']})")
        
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم...")

# --- 4. منطق اللعب (process_play) ---
@router.callback_query(F.data.startswith("p_"))
async def process_play(c: types.CallbackQuery):
    data = c.data.split("_")
    g_id, played_card = data[1], data[2]
    
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك! ⏳", show_alert=True)

    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    
    p1_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (game['p1_id'],))[0]['player_name']
    p2_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (game['p2_id'],))[0]['player_name']
    my_name, opp_name = (p1_name, p2_name) if is_p1 else (p2_name, p1_name)

    my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    opp_hand = [h for h in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if h]
    deck = [d for d in game['deck'].split(",") if d]
    top_card = game['top_card']

    can_play = ("🌈" in played_card or "🌈" in top_card or played_card[0] == top_card[0] or 
                (len(played_card.split()) > 1 and len(top_card.split()) > 1 and played_card.split()[-1] == top_card.split()[-1]))
    
    if not can_play:
        await c.answer("❌ ورقة خطأ! سحبنا لك ورقتين.", show_alert=True)
        for _ in range(2): 
            if deck: my_hand.append(deck.pop(0))
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), g_id), commit=True)
        await send_player_hand(c.from_user.id, g_id, c.message.message_id, "لعبت ورقة خطأ وتسحبت ورقتين!")
        return

    my_hand.remove(played_card)
    next_turn = opp_id
    extra_me, extra_opp = f"لعبت {played_card}", f"الخصم لعب {played_card}"
    uno_reset = f", {'p1_uno' if is_p1 else 'p2_uno'}=FALSE" if len(my_hand) != 1 else ""

    if "➕" in played_card:
        val = 1 if "➕1" in played_card else (2 if "➕2" in played_card else 4)
        for _ in range(val): 
            if deck: opp_hand.append(deck.pop(0))
        next_turn = c.from_user.id
        extra_me, extra_opp = f"🔥 سحبت {opp_name} {val} أوراق!", f"📥 سحبك {my_name} {val} أوراق والدور عنده!"
        uno_reset += f", {'p2_uno' if is_p1 else 'p1_uno'}=FALSE"
    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = c.from_user.id
        extra_me, extra_opp = f"🚫 منعت دور {opp_name}!", f"🚫 {my_name} منع دورك!"

    db_query(f'''UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, 
                {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s {uno_reset} WHERE game_id=%s''', 
             (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)
    
    if not my_hand:
        db_query("UPDATE users SET online_points = online_points + 10 WHERE user_id = %s", (c.from_user.id,), commit=True)
        new_pts = db_query("SELECT online_points FROM users WHERE user_id = %s", (c.from_user.id,))[0]['online_points']
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        
        end_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎲 جولة جديدة", callback_data="mode_random")],[InlineKeyboardButton(text="🏠 الرئيسية", callback_data="home")]])
        await c.message.delete()
        await bot.send_message(c.from_user.id, f"🏆 مبروك الفوز على **{opp_name}**!\n✅ نقاطك أصبحت: `{new_pts}`", reply_markup=end_kb)
        await bot.send_message(opp_id, f"💀 هاردلك.. فاز عليك **{my_name}**!\n📈 نقاطه صارت: `{new_pts}`", reply_markup=end_kb)
        return

    # 🚨 تعديل منطق الجوكر لضمان مسح الرسالة القديمة
    if "🌈" in played_card and "➕" not in played_card:
        # مسح رسالة اللعب الحالية قبل طلب اللون
        try: await c.message.delete()
        except: pass
        await ask_color(c.from_user.id, g_id)
    else:
        # اللعب العادي
        await send_player_hand(c.from_user.id, g_id, c.message.message_id, extra_me)
        await send_player_hand(opp_id, g_id, last_opp_msg, extra_opp)

# --- 5. نظام السحب الذكي وتنظيف الشات ---
@router.callback_query(F.data.startswith("d_"))
async def process_draw(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")
    
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    deck = [x for x in game['deck'].split(",") if x]
    hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    top = game['top_card']
    
    # فحص: هل عنده ورقة ترهم أصلاً؟
    has_match = any(("🌈" in card or card[0] == top[0] or (len(card.split()) > 1 and len(top.split()) > 1 and card.split()[-1] == top.split()[-1])) for card in hand)

    new_c = deck.pop(0); hand.append(new_c)
    can_p_new = ("🌈" in new_c or new_c[0] == top[0] or (len(new_c.split()) > 1 and len(top.split()) > 1 and new_c.split()[-1] == top.split()[-1]))
    
    # إذا الجديدة ما ترهم + القديمة ما ترهم = يضيع الدور
    nt = c.from_user.id if (can_p_new or has_match) else opp_id
    msg_me = f"سحبت {new_c} وترهم!" if can_p_new else (f"سحبت {new_c} والعب بغيرها!" if has_match else f"سحبت {new_c} وما ترهم.. ضاع دورك!")
    msg_opp = "الخصم سحب ورقة ولعبها!" if can_p_new else (f"الخصم سحب والعب بغيرها!" if has_match else "الخصم سحب وما رهمت.. هسة دورك!")
    
    db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s, {'p1_uno' if is_p1 else 'p2_uno'}=FALSE WHERE game_id=%s", 
             (",".join(hand), ",".join(deck), nt, g_id), commit=True)
    
    last_opp_msg = game['p2_last_msg' if is_p1 else 'p1_last_msg']
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, msg_me)
    if nt == opp_id: # نمسح رسالة الخصم فقط إذا تحول الدور إله
        await send_player_hand(opp_id, g_id, last_opp_msg, msg_opp)

# --- 6. أونو وصيد (مع الأسماء) ---
@router.callback_query(F.data.startswith("u_"))
async def process_uno(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    db_query(f"UPDATE active_games SET {'p1_uno' if is_p1 else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)
    try: await bot.send_photo(c.from_user.id, photo=IMG_UNO_SAFE_ME); await bot.send_photo(opp_id, photo=IMG_UNO_SAFE_OPP)
    except: pass
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, "قلت أونو وأمنت نفسك!")
    await send_player_hand(opp_id, g_id, game['p2_last_msg' if is_p1 else 'p1_last_msg'], "خصمك أمن نفسه وقال أونو!")

@router.callback_query(F.data.startswith("c_"))
async def process_catch(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    victim_id = game['p2_id'] if is_p1 else game['p1_id']
    hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(","); deck = game['deck'].split(",")
    if len(deck) >= 2: hand.extend([deck.pop(0), deck.pop(0)])
    db_query(f"UPDATE active_games SET {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(hand), ",".join(deck), g_id), commit=True)
    try: await bot.send_photo(c.from_user.id, photo=IMG_CATCH_SUCCESS); await bot.send_photo(victim_id, photo=IMG_CATCH_PENALTY)
    except: pass
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, "تم صيد الخصم!")
    await send_player_hand(victim_id, g_id, game['p2_last_msg' if is_p1 else 'p1_last_msg'], "صادك الخصم وتسحبت ورقتين!")

# --- 7. اختيار اللون ---
async def ask_color(u_id, g_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"sc_{g_id}_🔴"), InlineKeyboardButton(text="🔵", callback_data=f"sc_{g_id}_🔵")],[InlineKeyboardButton(text="🟡", callback_data=f"sc_{g_id}_🟡"), InlineKeyboardButton(text="🟢", callback_data=f"sc_{g_id}_🟢")]]
    await bot.send_message(u_id, "🌈 اختر اللون المطلوب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sc_"))
async def set_color_logic(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    
    # تحديث الكرت المكشوف وتحويل الدور
    db_query("UPDATE active_games SET top_card=%s, turn=%s WHERE game_id=%s", 
             (f"{col} (🌈)", opp_id, g_id), commit=True)
    
    # 1. مسح رسالة "اختر اللون"
    try: await c.message.delete()
    except: pass
    
    # 2. إرسال اليد الجديدة لك (بدون مسح قديم لأننا مسحناه فوق)
    await send_player_hand(c.from_user.id, g_id, None, f"اخترت اللون {col}!")
    
    # 3. مسح رسالة الخصم القديمة وتنبيهه باللون الجديد
    last_opp_msg = game['p2_last_msg' if is_p1 else 'p1_last_msg']
    await send_player_hand(opp_id, g_id, last_opp_msg, f"الخصم اختار اللون {col}!")
