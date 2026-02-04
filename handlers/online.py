import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك الأوراق المحدث (أضفنا الجوكر الجديد)
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    
    deck.extend(["🌈"] * 4)       # 50 نقطة
    deck.extend(["🌈➕1"] * 4)     # 10 نقاط
    deck.extend(["🌈➕2"] * 4)     # 20 نقطة
    deck.extend(["🌈➕4"] * 4)     # 50 نقطة
    random.shuffle(deck)
    return deck

# 2. واجهة عرض يد اللاعب (أزرار الأوراق)
async def send_hand(user_id, game_id):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (user_id == game['p1_id'])
    hand = game['p1_hand'].split(",") if is_p1 else game['p2_hand'].split(",")
    
    # تنسيق الرسالة
    turn_mark = "🟢 دورك الآن!" if game['turn'] == user_id else "⏳ دور الخصم..."
    opp_count = len(game['p2_hand'].split(',')) if is_p1 else len(game['p1_hand'].split(','))
    
    text = (f"🃏 **الورقة المكشوفة:** {game['top_card']}\n"
            f"{turn_mark}\n"
            f"🎴 أوراق الخصم: {opp_count}")

    # تحويل الأوراق لأزرار (3 في كل سطر)
    kb = []
    row = []
    for i, card in enumerate(hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"play_{game_id}_{i}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    # أزرار التحكم
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"draw_{game_id}")])
    kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"uno_{game_id}")])

    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. نظام البحث عن لاعب (Matchmaking)
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        g = waiting[0]
        deck = generate_deck()
        p1_h, p2_h = [deck.pop() for _ in range(7)], [deck.pop() for _ in range(7)]
        top = deck.pop()
        
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, 
                   deck=%s, status='playing', turn=%s WHERE game_id=%s''', 
                (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True, fetch=False)
        
        await callback.message.edit_text("✅ وجدنا خصماً! بدأت اللعبة...")
        await send_hand(g['p1_id'], g['game_id'])
        await send_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True, fetch=False)
        await callback.message.edit_text("🔎 جاري البحث عن لاعب... (سيلعب البوت معك بعد 30ث)")
        
        # مؤقت الذكاء الاصطناعي (AI)
        await asyncio.sleep(30)
        game_check = db_query("SELECT status FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,))
        if game_check:
            await callback.message.answer("🤖 لم نجد أحداً، سألعب معك أنا (البوت)!")
            # كود تشغيل الـ AI يوضع هنا

# 4. منطق لعب الورقة (التحقق والصد)
@router.callback_query(F.data.startswith("play_"))
async def process_play(c: types.CallbackQuery):
    _, g_id, idx = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    if c.from_user.id != game['turn']:
        return await c.answer("مو دورك! اصبر شوية ⏳", show_alert=True)
    
    is_p1 = (c.from_user.id == game['p1_id'])
    hand = game['p1_hand'].split(",") if is_p1 else game['p2_hand'].split(",")
    played = hand[int(idx)]
    top = game['top_card']
    
    # التحقق من صحة الورقة (Logic)
    valid = False
    if "🌈" in played: valid = True
    else:
        t_col, t_val = top.split(" ")[0], top.split(" ")[1] if " " in top else top
        p_col, p_val = played.split(" ")[0], played.split(" ")[1] if " " in played else played
        if p_col == t_col or p_val == t_val: valid = True

    if not valid:
        # عقوبة الغش
        await c.answer("❌ ورقة غلط! خذ ورقتين عقوبة 🌚", show_alert=True)
        deck = game['deck'].split(",")
        hand.extend([deck.pop(), deck.pop()])
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", 
                 (",".join(hand), ",".join(deck), g_id), commit=True, fetch=False)
        await c.message.delete()
        return await send_hand(c.from_user.id, g_id)

    # تنفيذ اللعبة الصحيحة
    hand.pop(int(idx))
    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    
    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, turn=%s WHERE game_id=%s",
             (played, ",".join(hand), next_turn, g_id), commit=True, fetch=False)
    
    await c.message.delete()
    # تحديث الشاشة للاثنين
    await send_hand(game['p1_id'], g_id)
    await send_hand(game['p2_id'], g_id)
