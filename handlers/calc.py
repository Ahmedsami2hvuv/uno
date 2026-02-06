import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# --- 1. حسبة الأوراق (مثل ما طلبتها بالببط) ---
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0") # صفر واحد
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"]) # بطاقتين من 1-9
        for action in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {action}", f"{c} {action}"]) # بطاقتين أكشن
    # الجوكرات (4 من كل نوع)
    for j in ["🌈", "🌈➕1", "🌈➕2", "🌈➕4"]: deck.extend([j] * 4)
    random.shuffle(deck)
    return deck

def sort_uno_hand(hand):
    color_order = {"🔴": 1, "🔵": 2, "🟡": 3, "🟢": 4, "🌈": 5}
    return sorted(hand, key=lambda x: (color_order.get(x[0], 99), x))

# --- 2. دالة التعديل (نسخة طبق الأصل من منطق الحاسبة) ---
async def update_ui(user_id, game_id, extra_text=""):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    
    # جلب الأسماء
    p1_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (game['p1_id'],))[0]['player_name']
    p2_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (game['p2_id'],))[0]['player_name']
    opp_name = p2_name if is_p1 else p1_name
    
    hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    my_hand = sort_uno_hand(hand)
    opp_count = len([c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c])
    
    text = (f"🃏 المكشوفة: `{game['top_card']}`\n"
            f"👤 **{opp_name}**: ({opp_count}) أوراق\n"
            f"━━━━━━━━━━━━━━\n"
            f"{'🟢 **دورك!**' if int(game['turn']) == int(user_id) else f'⏳ دور: {opp_name}'}")
    
    if extra_text: text += f"\n\n🔔 {extra_text.replace('الخصم', opp_name)}"

    kb = []
    row = []
    for card in my_hand:
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{card}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"d_{game_id}")])
    
    # هنا "قفل" التعديل (مثل الحاسبة)
    msg_id = game['p1_last_msg' if is_p1 else 'p2_last_msg']
    
    try:
        # تعديل حصراً!
        await bot.edit_message_text(text, user_id, msg_id, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except Exception as e:
        # إذا فشل التعديل (فقط في أول مرة)، يرسل ويخزن الرقم فوراً
        sent = await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        db_query(f"UPDATE active_games SET {'p1_last_msg' if is_p1 else 'p2_last_msg'} = %s WHERE game_id = %s", (sent.message_id, game_id), commit=True)

# --- 3. البداية والربط ---
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        g = waiting[0]
        deck = generate_deck()
        p1_h, p2_h, top = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)], deck.pop()
        
        # أهم خطوة: تسجيل الدخول للعبة
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s WHERE game_id=%s''',
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        
        await callback.message.edit_text("✅ تم الربط! بدأت اللعبة.")
        # إرسال أول رسالة لتثبيت الـ ID
        await update_ui(g['p1_id'], g['game_id'])
        await update_ui(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم...")

# --- 4. منطق اللعب (تعديل لحظي مثل الحاسبة) ---
@router.callback_query(F.data.startswith("p_"))
async def process_play(c: types.CallbackQuery):
    _, g_id, played_card = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")

    is_p1 = (int(c.from_user.id) == int(game['p1_id'])); opp_id = game['p2_id'] if is_p1 else game['p1_id']
    my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    opp_hand = [h for h in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if h]
    deck = [d for d in game['deck'].split(",") if d]; top_card = game['top_card']

    # فحص القانون
    can_play = ("🌈" in played_card or "🌈" in top_card or played_card[0] == top_card[0] or 
                (len(played_card.split()) > 1 and len(top_card.split()) > 1 and played_card.split()[-1] == top_card.split()[-1]))
    
    if not can_play: return await c.answer("❌ ورقة خطأ!")

    my_hand.remove(played_card); next_turn = opp_id
    extra_me, extra_opp = f"لعبت {played_card}", f"الخصم لعب {played_card}"

    # أوراق الأكشن
    if "➕" in played_card:
        val = int(played_card[-1]) if played_card[-1].isdigit() else 2
        for _ in range(val): 
            if deck: opp_hand.append(deck.pop(0))
        next_turn = c.from_user.id
        extra_me, extra_opp = f"🔥 سحبت الخصم {val}!", f"📥 سحبك الخصm {val}!"
    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = c.from_user.id
        extra_me, extra_opp = "🚫 منعت دور الخصم!", "🚫 الخصم منعك!"

    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
             (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)
    
    if not my_hand:
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        await c.message.edit_text("🏆 مبروك الفوز!")
        await bot.send_message(opp_id, "💀 هاردلك.. خسرت!")
        return

    # التعديل اللحظي (مثل الحاسبة)
    await update_ui(c.from_user.id, g_id, extra_me)
    await update_ui(opp_id, g_id, extra_opp)

# --- 5. السحب (تعديل لحظي) ---
@router.callback_query(F.data.startswith("d_"))
async def process_draw(c: types.CallbackQuery):
    g_id = c.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")
    
    is_p1 = (int(c.from_user.id) == int(game['p1_id'])); opp_id = game['p2_id'] if is_p1 else game['p1_id']
    deck = [x for x in game['deck'].split(",") if x]; hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
    
    new_c = deck.pop(0); hand.append(new_c)
    top = game['top_card']
    can_p = ("🌈" in new_c or new_c[0] == top[0] or (len(new_c.split()) > 1 and len(top.split()) > 1 and new_c.split()[-1] == top.split()[-1]))
    
    nt = c.from_user.id if can_p else opp_id
    db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
             (",".join(hand), ",".join(deck), nt, g_id), commit=True)
    
    await update_ui(c.from_user.id, g_id, f"سحبت {new_c}")
    if nt == opp_id: await update_ui(opp_id, g_id, "الخصم سحب!")
