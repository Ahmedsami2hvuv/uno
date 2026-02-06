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

# --- 1. محرك الأوراق ---
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

# --- دالة ترتيب الأوراق ---
def sort_uno_hand(hand):
    color_order = {"🔴": 1, "🔵": 2, "🟡": 3, "🟢": 4, "🌈": 5}
    def sort_key(card):
        color_emoji = card[0]
        rank = color_order.get(color_emoji, 99)
        return (rank, card)
    return sorted(hand, key=sort_key)

# --- 2. واجهة اللعب وتنظيف الرسائل ---
async def send_player_hand(user_id, game_id, old_msg_id=None, extra_text=""):
    if old_msg_id:
        try: await bot.delete_message(user_id, old_msg_id)
        except: pass

    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    
    raw_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    my_hand = sort_uno_hand(raw_hand)
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    
    turn_text = "🟢 دورك الآن!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم"
    status_text = f"\n\n🔔 **تنبيه:** {extra_text}" if extra_text else ""
    
    text = (f"🃏 المكشوفة: `{game['top_card']}`\n"
            f"👤 الخصم: {len(opp_hand)} أوراق\n"
            f"━━━━━━━━━━━━━━\n"
            f"{turn_text}{status_text}")

    kb = []
    row = []
    for card in my_hand:
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{card}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"d_{game_id}")])
    
    if len(my_hand) == 2:
        kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"u_{game_id}")])
    
    opp_uno_secured = game['p2_uno'] if is_p1 else game['p1_uno']
    if len(opp_hand) == 1 and not opp_uno_secured:
        kb.append([InlineKeyboardButton(text="🚨 صيده!", callback_data=f"c_{game_id}")])

    try:
        sent = await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
        return sent.message_id
    except: return None

# --- 3. اللعب العشوائي ---
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    # تنظيف أي طلبات سابقة معلقة لهذا المستخدم
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    
    # البحث عن خصم ينتظر
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        g = waiting[0]
        deck = generate_deck()
        # توزيع الأوراق (7 لكل لاعب)
        p1_h, p2_h = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)]
        top = deck.pop()
        
        # 🟢 جلب بيانات الخصم (اللاعب الأول اللي جان ينتظر)
        p1_info = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (g['p1_id'],))[0]
        # 🔵 جلب بياناتك أنت (اللاعب الثاني اللي دخلت هسة)
        p2_info = db_query("SELECT player_name, online_points FROM users WHERE user_id = %s", (user_id,))[0]
        
        # تحديث بيانات اللعبة في الداتا بيس
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s WHERE game_id=%s''',
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        
        # 📢 تبليغ اللاعب الأول ببياناتك
        await bot.send_message(
            g['p1_id'], 
            f"✅ تم العثور على خصم!\n\n👤 الخصم: **{p2_info['player_name']}**\n🏅 نقاطه: `{p2_info['online_points']}`\n\nبدأت اللعبة.. ركز زين! 🔥"
        )
        
        # 📢 تبليغك أنت ببيانات اللاعب الأول
        await callback.message.edit_text(
            f"✅ تم الربط بنجاح!\n\n👤 الخصم: **{p1_info['player_name']}**\n🏅 نقاطه: `{p1_info['online_points']}`\n\nبدأت اللعبة.. بالتوفيق! 🔥"
        )
        
        # إرسال أوراق اللعب للطرفين
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        # إذا لم يوجد خصم، يوضع اللاعب في قائمة الانتظار
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم قوي ينافسك... انتظر لحظة.")

# --- 4. منطق اللعب ---
@router.callback_query(F.data.startswith("p_"))
async def process_play(c: types.CallbackQuery):
    data = c.data.split("_")
    g_id, played_card = data[1], data[2]
    
    game_res = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))
    if not game_res: return
    game = game_res[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك! ⏳")

    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    opp_hand = [h for h in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if h]
    deck = [d for d in game['deck'].split(",") if d]
    top_card = game['top_card']

    can_play = ("🌈" in played_card or "🌈" in top_card or played_card[0] == top_card[0] or 
                (len(played_card.split()) > 1 and len(top_card.split()) > 1 and played_card.split()[-1] == top_card.split()[-1]))
    
    # 🚨 تبليغ الطرفين عند اللعب الخطأ
    if not can_play:
        await c.answer("❌ ورقة خطأ! عقوبة سحب ورقتين.", show_alert=True)
        for _ in range(2): 
            if deck: my_hand.append(deck.pop(0))
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), g_id), commit=True)
        
        await send_player_hand(c.from_user.id, g_id, c.message.message_id, "لعبت ورقة خطأ وتسحبت ورقتين!")
        await send_player_hand(opp_id, g_id, None, "الخصم لعب ورقة خطأ وتسحب ورقتين والدور لسه عنده!")
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
        extra_me, extra_opp = f"🔥 سحبت خصمك {val} أوراق!", f"📥 سحبك الخصم {val} أوراق والدور عنده!"
        uno_reset += f", {'p2_uno' if is_p1 else 'p1_uno'}=FALSE"
    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = c.from_user.id
        extra_me, extra_opp = "🚫 منعت الخصم!", "🚫 الخصم منع دورك!"

    db_query(f'''UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, 
                {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s {uno_reset} WHERE game_id=%s''', 
             (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)
    
    # 🚨 فحص الفوز مع عرض النقاط والأزرار
    if not my_hand:
        db_query("UPDATE users SET online_points = online_points + 10 WHERE user_id = %s", (c.from_user.id,), commit=True)
        total_pts = db_query("SELECT online_points FROM users WHERE user_id = %s", (c.from_user.id,))[0]['online_points']
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        
        # أزرار النهاية
        end_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎲 جولة جديدة", callback_data="mode_random")],
            [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
        ])

        await c.message.delete()
        await bot.send_message(c.from_user.id, f"🏆 مبروك الفوز!\n✅ حصلت على: +10 نقاط\n💰 مجموع نقاطك الكلي: {total_pts}", reply_markup=end_kb)
        await bot.send_message(opp_id, "💀 هاردلك! لقد خسرتم هذه الجولة.", reply_markup=end_kb)
        return

    if "🌈" in played_card and "➕" not in played_card:
        await ask_color(c.from_user.id, g_id)
    else:
        await send_player_hand(c.from_user.id, g_id, c.message.message_id, extra_me)
        await send_player_hand(opp_id, g_id, None, extra_opp)

# --- 5. نظام السحب التنبيهي ---
@router.callback_query(F.data.startswith("d_"))
async def process_draw(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")
    
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    deck = [x for x in game['deck'].split(",") if x]; hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    
    new_c = deck.pop(0); hand.append(new_c)
    t = game['top_card']
    can_p = ("🌈" in new_c or new_c[0] == t[0] or (len(new_c.split()) > 1 and len(t.split()) > 1 and new_c.split()[-1] == t.split()[-1]))
    
    nt = c.from_user.id if can_p else opp_id
    msg_me = f"سحبت ({new_c}) وترهم باللعب!" if can_p else f"سحبت ({new_c}) وما ترهم.. تحول الدور!"
    msg_opp = "خصمك سحب ورقة ولعبها!" if can_p else "خصمك سحب وما رهمت.. هسة دورك!"
    
    db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s, {'p1_uno' if is_p1 else 'p2_uno'}=FALSE WHERE game_id=%s", 
             (",".join(hand), ",".join(deck), nt, g_id), commit=True)
    
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, msg_me)
    await send_player_hand(opp_id, g_id, None, msg_opp)

# --- 6. نظام الصور (أونو وصيد) ---
@router.callback_query(F.data.startswith("u_"))
async def process_uno(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']
    
    db_query(f"UPDATE active_games SET {'p1_uno' if is_p1 else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)
    
    try: await bot.send_photo(c.from_user.id, photo=IMG_UNO_SAFE_ME)
    except: pass
    try: await bot.send_photo(opp_id, photo=IMG_UNO_SAFE_OPP)
    except: pass
    
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, "قلت أونو وأمنت نفسك!")
    await send_player_hand(opp_id, g_id, None, "خصمك أمن نفسه وقال أونو!")

@router.callback_query(F.data.startswith("c_"))
async def process_catch(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id']))
    victim_id = game['p2_id'] if is_p1 else game['p1_id']
    hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(",")
    deck = game['deck'].split(",")
    
    if len(deck) >= 2: hand.extend([deck.pop(0), deck.pop(0)])
    db_query(f"UPDATE active_games SET {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(hand), ",".join(deck), g_id), commit=True)
    
    try: await bot.send_photo(c.from_user.id, photo=IMG_CATCH_SUCCESS)
    except: pass
    try: await bot.send_photo(victim_id, photo=IMG_CATCH_PENALTY)
    except: pass
    
    await send_player_hand(game['p1_id'], g_id, c.message.message_id if is_p1 else None, "تم صيد الخصم!")
    await send_player_hand(game['p2_id'], g_id, c.message.message_id if not is_p1 else None, "صادك الخصم!")

# --- 7. اختيار اللون ---
async def ask_color(u_id, g_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"sc_{g_id}_🔴"), InlineKeyboardButton(text="🔵", callback_data=f"sc_{g_id}_🔵")],
          [InlineKeyboardButton(text="🟡", callback_data=f"sc_{g_id}_🟡"), InlineKeyboardButton(text="🟢", callback_data=f"sc_{g_id}_🟢")]]
    await bot.send_message(u_id, "🌈 اختر اللون المطلوب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sc_"))
async def set_color_logic(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    opp_id = game['p2_id'] if int(c.from_user.id) == int(game['p1_id']) else game['p1_id']
    db_query("UPDATE active_games SET top_card=%s, turn=%s WHERE game_id=%s", (f"{col} (🌈)", opp_id, g_id), commit=True)
    await c.message.delete()
    await send_player_hand(c.from_user.id, g_id, None, f"اخترت اللون {col}!")
    await send_player_hand(opp_id, g_id, None, f"الخصم اختار اللون {col}!")
