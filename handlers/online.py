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
    return int(card.split()[-1])

def sort_uno_hand(hand):
    color_order = {"🔴": 1, "🔵": 2, "🟡": 3, "🟢": 4, "🌈": 5}
    return sorted(hand, key=lambda x: (color_order.get(x[0], 99), x))

# --- 2. دالة إرسال اليد (المصححة لعرض الأوراق دائمياً) ---
async def send_player_hand(user_id, game_id, old_msg_id=None, extra_text="", is_locked=False):
    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    
    # تفعيل السحب التلقائي إذا الدور للاعب وما عنده شي
    is_my_turn = (int(game['turn']) == int(user_id))
    my_hand_raw = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    my_hand = sort_uno_hand([c for c in my_hand_raw if c])
    
    if is_my_turn and not is_locked:
        top = game['top_card']
        has_move = any(("🌈" in c or c[0] == top[0] or (len(c.split()) > 1 and len(top.split()) > 1 and c.split()[-1] == top.split()[-1])) for c in my_hand)
        if not has_move:
            return await auto_draw(user_id, game_id)

    # نظام المسح
    db_msg_id = game['p1_last_msg'] if is_p1 else game['p2_last_msg']
    target_to_delete = old_msg_id if old_msg_id else db_msg_id
    if target_to_delete and int(target_to_delete) > 0:
        try: await bot.delete_message(user_id, target_to_delete)
        except: pass

    p1_n = db_query("SELECT player_name FROM users WHERE user_id = %s", (game['p1_id'],))[0]['player_name']
    p2_n = db_query("SELECT player_name FROM users WHERE user_id = %s", (game['p2_id'],))[0]['player_name']
    opp_name = p2_n if is_p1 else p1_n
    opp_count = len([c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c])
    
    turn_text = "🟢 **دورك الآن!**" if is_my_turn else f"⏳ دور: **{opp_name}**"
    if is_locked: turn_text = "⏳ **انتظر رد الخصم على التحدي...**"

    text = (f"👤 **{opp_name}**: ({opp_count}) أوراق\n"
            f"👤 **أنت**: ({len(my_hand)}) أوراق\n"
            f"━━━━━━━━━━━━━━\n"
            f"{turn_text}\n"
            f"🃏 المكشوفة: `{game['top_card']}`\n"
            f"━━━━━━━━━━━━━━\n"
            f"🔔 {extra_text.replace('الخصم', opp_name) if extra_text else ''}")

    kb = []
    row = []
    # 💥 هنا التعديل: الأزرار تظهر دائماً، بس الـ Callback يرفض إذا مو دورك
    for card in my_hand:
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{card}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    
    if len(my_hand) == 2 and is_my_turn:
        kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"u_{game_id}")])
    
    try:
        sent = await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        db_query(f"UPDATE active_games SET {'p1_last_msg' if is_p1 else 'p2_last_msg'} = %s WHERE game_id = %s", (sent.message_id, game_id), commit=True)
    except: pass

# --- 3. نظام السحب التلقائي ---
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

@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # 1. تنظيف أي طلبات قديمة للاعب حتى لا يعلق النظام
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    
    # 2. البحث عن خصم ينتظر
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        g = waiting[0]
        game_id = g['game_id']
        p1_id = g['p1_id']
        p2_id = user_id # اللاعب الحالي هو الخصم الثاني
        
        # 3. تجهيز المخزن وتوزيع الأوراق (7 لكل لاعب)
        deck = generate_deck()
        p1_hand = [deck.pop() for _ in range(7)]
        p2_hand = [deck.pop() for _ in range(7)]
        
        # 4. سحب أول ورقة من الكومة (بشرط ما تكون جوكر للبداية)
        top_card = deck.pop()
        while "🌈" in top_card:
            deck.append(top_card)
            random.shuffle(deck)
            top_card = deck.pop()
            
        # 5. تحديث قاعدة البيانات وبدء الجولة (تصفير عداد الرسائل مهم جداً للمسح)
        db_query('''UPDATE active_games SET 
                    p2_id = %s, 
                    p1_hand = %s, 
                    p2_hand = %s, 
                    top_card = %s, 
                    deck = %s, 
                    status = 'playing', 
                    turn = %s, 
                    p1_last_msg = 0, 
                    p2_last_msg = 0 
                    WHERE game_id = %s''',
                 (p2_id, ",".join(p1_hand), ",".join(p2_hand), top_card, ",".join(deck), p1_id, game_id), commit=True)
        
        # 6. إبلاغ اللاعبين وبدء عرض الأوراق
        await callback.message.edit_text("✅ تم إيجاد خصم! بدأت اللعبة...")
        
        # إرسال يد اللاعب الأول ويد اللاعب الثاني
        await send_player_hand(p1_id, game_id)
        await send_player_hand(p2_id, game_id)
        
    else:
        # إذا لم يوجد خصم، يفتح غرفة انتظار جديدة
        db_query("INSERT INTO active_games (p1_id, status, p1_last_msg, p2_last_msg) VALUES (%s, 'waiting', 0, 0)", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم عشوائي...")

# --- 4. منطق اللعب والتحدي ---
@router.callback_query(F.data.startswith("p_"))
async def process_play(c: types.CallbackQuery):
    _, g_id, played_card = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")

    is_p1 = (int(c.from_user.id) == int(game['p1_id'])); opp_id = game['p2_id'] if is_p1 else game['p1_id']
    my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    deck = game['deck'].split(","); top_card = game['top_card']

    # فحص قابلية اللعب (الارتداد الشامل)
    can_play = ("🌈" in played_card or played_card[0] == top_card[0] or (len(played_card.split()) > 1 and len(top_card.split()) > 1 and played_card.split()[-1] == top_card.split()[-1]))
    if not can_play:
        for _ in range(2): 
            if deck: my_hand.append(deck.pop(0))
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(my_hand), ",".join(deck), g_id), commit=True)
        await c.answer("❌ ورقة خطأ! ارتدت وتعاقبت بـ 2.", show_alert=True)
        await send_player_hand(opp_id, g_id, None, "الخصم لعب غلط وتعاقب بـ 2 أوراق!")
        return await send_player_hand(c.from_user.id, g_id, c.message.message_id, "لعبت غلط.. ارتدت ليدك وتعاقبت!")

    # فحص غش الجوكر
    has_playable = any(("🌈" not in h and (h[0] == top_card[0] or (len(h.split()) > 1 and len(top_card.split()) > 1 and h.split()[-1] == top_card.split()[-1]))) for h in my_hand)
    
    if "🌈" in played_card:
        # نظام التحدي
        kb = [[InlineKeyboardButton(text="⚔️ تحدي", callback_data=f"chal_{g_id}_{played_card}"),
               InlineKeyboardButton(text="✅ لا أتحدى", callback_data=f"nochal_{g_id}_{played_card}")]]
        await send_player_hand(c.from_user.id, g_id, c.message.message_id, f"نزلت {played_card}.. انتظر الخصم يتحدى لو لا.", is_locked=True)
        # مسح رسالة الخصم القديمة وإرسال أزرار التحدي
        game_latest = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
        opp_msg_id = game_latest['p2_last_msg' if is_p1 else 'p1_last_msg']
        try: await bot.delete_message(opp_id, opp_msg_id)
        except: pass
        sent = await bot.send_message(opp_id, f"🚨 الخصم نزل `{played_card}`! هل تشك أنه غشاش؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        db_query(f"UPDATE active_games SET {'p2_last_msg' if is_p1 else 'p1_last_msg'} = %s WHERE game_id = %s", (sent.message_id, g_id), commit=True)
        return

    # اللعب النظامي للأوراق العادية
    my_hand.remove(played_card); next_turn = opp_id
    opp_hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(",")
    if "➕" in played_card:
        val = int(played_card[-1]); [opp_hand.append(deck.pop(0)) for _ in range(val) if deck]
        next_turn = c.from_user.id
    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = c.from_user.id

    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
             (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)

    # فحص الفوز وحساب النقاط
    if not my_hand:
        opp_pts = sum(get_card_points(x) for x in opp_hand if x)
        db_query("UPDATE users SET online_points = online_points + %s WHERE user_id = %s", (opp_pts, c.from_user.id), commit=True)
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        kb_win = [[InlineKeyboardButton(text="🎲 جولة جديدة", callback_data="mode_random")]]
        await bot.send_message(c.from_user.id, f"🏆 مبروك! فزت بـ {opp_pts} نقطة.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_win))
        await bot.send_message(opp_id, f"💀 خسرت! الخصم جمع {opp_pts} نقطة.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_win))
        return

    await send_player_hand(c.from_user.id, g_id, c.message.message_id, f"لعبت {played_card}")
    await send_player_hand(opp_id, g_id, None, f"الخصم لعب {played_card}")

# --- 5. معالجة التحدي (الحكم العادل ⚖️) ---
@router.callback_query(F.data.startswith("chal_") | F.data.startswith("nochal_"))
async def handle_challenge(c: types.CallbackQuery):
    data = c.data.split("_")
    is_challenge = (data[0] == "chal")
    g_id = data[1]
    played_card = data[2]
    
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    challenger_id = c.from_user.id
    
    # 🆔 تحديد من هو الغشاش المحتمل ومن هو المتحدي
    is_p2_challenger = (int(challenger_id) == int(game['p2_id']))
    player_id = game['p1_id'] if is_p2_challenger else game['p2_id']
    
    # جلب الأيدي وتنظيفها من الفراغات
    p_hand = [h.strip() for h in (game['p1_hand'] if is_p1_player := (int(player_id) == int(game['p1_id'])) else game['p2_hand']).split(",") if h.strip()]
    o_hand = [h.strip() for h in (game['p2_hand'] if is_p1_player else game['p1_hand']).split(",") if h.strip()]
    deck = [d.strip() for d in game['deck'].split(",") if d.strip()]
    top_before = game['top_card']
    
    # 🚨 فحص الغش: هل كان اللاعب يملك ورقة أخرى صالحة غير الجوكر؟
    is_cheat = any(("🌈" not in h and (h[0] == top_before[0] or (len(h.split()) > 1 and h.split()[-1] == top_before.split()[-1]))) for h in p_hand if h != played_card)
    
    penalty_val = 6 if "➕4" in played_card else (4 if "➕2" in played_card else 3)

    if is_challenge:
        if is_cheat: # ✅ اللاعب غشاش -> يتعاقب player_id
            for _ in range(penalty_val):
                if deck: p_hand.append(deck.pop(0))
            
            # تحديث الداتا بيس: العقوبة ليد اللاعب (p_hand) والدور يبقى عنده
            db_query(f"UPDATE active_games SET {'p1_hand' if is_p1_player else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
                     (",".join(p_hand), ",".join(deck), player_id, g_id), commit=True)
            
            await bot.send_message(player_id, f"❌ انكشفت! الخصم تحداك وطلعت غشاش.. ارتدت الورقة ليدك وتعاقبت بـ {penalty_val} أوراق.")
            await send_player_hand(challenger_id, g_id, c.message.message_id, "🎯 كفشته! الخصم طلع غشاش وتعاقب.")
            await send_player_hand(player_id, g_id, None, "❌ غشيت وانكشفت! ارتدت الورقة ليدك وتعاقبت.")
        
        else: # ❌ اللاعب صادق -> المتحدي (challenger_id) يتعاقب
            final_pen = penalty_val + 2
            for _ in range(final_pen):
                if deck: o_hand.append(deck.pop(0))
            
            if played_card in p_hand: p_hand.remove(played_card)
            
            # تحديث الداتا بيس: العقوبة ليد المتحدي (o_hand) واللاعب يكمل
            db_query(f"UPDATE active_games SET {'p1_hand' if is_p1_player else 'p2_hand'}=%s, {'p2_hand' if is_p1_player else 'p1_hand'}=%s, deck=%s, top_card=%s, turn=%s WHERE game_id=%s", 
                     (",".join(p_hand), ",".join(o_hand), ",".join(deck), played_card, player_id, g_id), commit=True)
            
            await bot.send_message(player_id, "✅ الخصم فشل بالتحدي! إنت صادق وهو انضرب بالعقوبة.. كمل لعبك.")
            await send_player_hand(challenger_id, g_id, c.message.message_id, f"❌ فشلت بالتحدي! اللاعب صادق وانضربت إنت بـ {final_pen} أوراق.")
            await send_player_hand(player_id, g_id, None, f"لعبت {played_card} والخصم خسر التحدي.")

    else: # ✅ زر "لا أتحدى" (عبور طبيعي)
        if played_card in p_hand: p_hand.remove(played_card)
        s_val = int(played_card[-1]) if "➕" in played_card else 0
        for _ in range(s_val):
            if deck: o_hand.append(deck.pop(0))
            
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1_player else 'p2_hand'}=%s, {'p2_hand' if is_p1_player else 'p1_hand'}=%s, deck=%s, top_card=%s, turn=%s WHERE game_id=%s", 
                 (",".join(p_hand), ",".join(o_hand), ",".join(deck), played_card, player_id, g_id), commit=True)
        
        await send_player_hand(player_id, g_id, None, "✅ الخصم ما تحدى، كمل لعبك!")
        await send_player_hand(challenger_id, g_id, c.message.message_id, "الخصم لعب جوكر وما تحديت.")

    # طلب اللون فقط إذا كان جوكر ملون سادة ولم ينكشف كغشاش
    if played_card == "🌈" and not (is_challenge and is_cheat):
        await ask_color(player_id, g_id)


# --- 6. أونو وصيد ---
@router.callback_query(F.data.startswith("u_"))
async def process_uno(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]; game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id'])); opp_id = game['p2_id'] if is_p1 else game['p1_id']
    db_query(f"UPDATE active_games SET {'p1_uno' if is_p1 else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)
    await bot.send_photo(c.from_user.id, photo=IMG_UNO_SAFE_ME); await bot.send_photo(opp_id, photo=IMG_UNO_SAFE_OPP)

@router.callback_query(F.data.startswith("c_"))
async def process_catch(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]; game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(c.from_user.id) == int(game['p1_id'])); victim_id = game['p2_id'] if is_p1 else game['p1_id']
    if (game['p2_uno'] if is_p1 else game['p1_uno']): return await c.answer("❌ مأمن نفسه!")
    hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(","); deck = game['deck'].split(",")
    [hand.append(deck.pop(0)) for _ in range(2) if deck]
    db_query(f"UPDATE active_games SET {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", (",".join(hand), ",".join(deck), g_id), commit=True)
    await bot.send_photo(c.from_user.id, photo=IMG_CATCH_SUCCESS); await bot.send_photo(victim_id, photo=IMG_CATCH_PENALTY)
    await send_player_hand(c.from_user.id, g_id, c.message.message_id, "صيد ناجح!")
    await send_player_hand(victim_id, g_id, None, "صادك الخصم!")

# --- الألوان والبداية ---
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
