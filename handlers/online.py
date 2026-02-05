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

# 2. واجهة عرض اليد
async def send_player_hand(user_id, game_id, msg_text=None):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (user_id == game['p1_id'])
    hand = game['p1_hand'].split(",") if is_p1 else game['p2_hand'].split(",")
    
    turn_text = "🟢 دورك الآن!" if game['turn'] == user_id else "⏳ دور الخصم..."
    opp_hand_count = len(game['p2_hand'].split(',')) if is_p1 else len(game['p1_hand'].split(','))

    if not msg_text:
        msg_text = f"🃏 الورقة المكشوفة: `{game['top_card']}`\n"
        msg_text += f"👤 الخصم لديه: {opp_hand_count} أوراق\n{turn_text}"

    kb = []
    row = []
    for i, card in enumerate(hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"op_play_{game_id}_{i}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"op_draw_{game_id}")])
    kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}")])

    await bot.send_message(user_id, msg_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. نظام اختيار اللون بعد الجوكر
async def ask_color(user_id, game_id):
    kb = [
        [InlineKeyboardButton(text="🔴 أحمر", callback_data=f"setcol_{game_id}_🔴"),
         InlineKeyboardButton(text="🔵 أزرق", callback_data=f"setcol_{game_id}_🔵")],
        [InlineKeyboardButton(text="🟡 أصفر", callback_data=f"setcol_{game_id}_🟡"),
         InlineKeyboardButton(text="🟢 أخضر", callback_data=f"setcol_{game_id}_🟢")]
    ]
    await bot.send_message(user_id, "🌈 اختر اللون المطلوب من الخصم:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("setcol_"))
async def set_color(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_")
    db_query("UPDATE active_games SET top_card = %s WHERE game_id = %s", (f"{col} (🌈)", g_id), commit=True, fetch=False)
    await c.message.delete()
    await c.answer(f"تم تغيير اللون إلى {col}")
    # بعد اختيار اللون، الدور يبقى عند اللاعب ليلعب ورقة إضافية فوق الجوكر
    await send_player_hand(c.from_user.id, g_id, msg_text=f"✅ اخترت اللون {col}. يمكنك الآن لعب ورقة أخرى!")

# 4. منطق اللعب المطور
@router.callback_query(F.data.startswith("op_play_"))
async def process_play(c: types.CallbackQuery):
    _, _, g_id, idx = c.data.split("_")
    idx = int(idx)
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    if c.from_user.id != game['turn']:
        return await c.answer("مو دورك! ⏳", show_alert=True)
    
    is_p1 = (c.from_user.id == game['p1_id'])
    hand = game['p1_hand'].split(",") if is_p1 else game['p2_hand'].split(",")
    played_card = hand[idx]
    top_card = game['top_card']
    deck = game['deck'].split(",")
    
    # قانون "الأوراق القديمة فقط" عند العقوبة
    # سنفترض أن أي ورقة تم سحبها حديثاً ستكون في آخر القائمة
    # (هذا يحتاج تطوير مستقبلي لإضافة عمود في الداتا بيس، لكن حالياً سنطبق المنطق العام)

    # التحقق من الصحة
    can_play = False
    if "🌈" in played_card:
        can_play = True
    else:
        t_color = top_card[0] # يأخذ أول إيموجي كـ لون
        t_val = top_card.split(" ")[1] if " " in top_card else top_card
        p_color = played_card[0]
        p_val = played_card.split(" ")[1] if " " in played_card else played_card
        
        if p_color == t_color or p_val == t_val or "🌈" in top_card:
            can_play = True

    if not can_play:
        await c.answer("❌ ورقة خطأ! سحب ورقتين عقوبة.", show_alert=True)
        hand.extend([deck.pop(), deck.pop()])
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", 
                 (",".join(hand), ",".join(deck), g_id), commit=True, fetch=False)
        await c.message.delete()
        return await send_player_hand(c.from_user.id, g_id)

    # تنفيذ الأكشن (Action Cards)
    hand.pop(idx)
    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    opp_id = next_turn
    
    # 1. منع (🚫) -> الدور يرجع لك
    if "🚫" in played_card:
        next_turn = c.from_user.id
        await c.answer("🚫 منعت الخصم! الدور لك مجدداً.")

    # 2. أوراق السحب (+) -> سحب تلقائي للخصم والدور يرجع لك
    elif "➕" in played_card:
        plus_val = 1 if "➕1" in played_card else (2 if "➕2" in played_card else 4)
        opp_hand = game['p2_hand'].split(",") if is_p1 else game['p1_hand'].split(",")
        for _ in range(plus_val): opp_hand.append(deck.pop())
        
        db_query(f"UPDATE active_games SET {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", 
                 (",".join(opp_hand), ",".join(deck), g_id), commit=True, fetch=False)
        
        await bot.send_message(opp_id, f"⚠️ خصمك نزل {played_card}! سحبت {plus_val} أوراق تلقائياً.")
        next_turn = c.from_user.id # الدور يرجع لك بعد السحب

    # تحديث الداتا بيس
    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, turn=%s WHERE game_id=%s",
             (played_card, ",".join(hand), next_turn, g_id), commit=True, fetch=False)

    await c.message.delete()

    # إذا كانت ملونة، اطلب منه اختيار لون
    if "🌈" in played_card:
        await ask_color(c.from_user.id, g_id)
    else:
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)

# 5. البحث عن لاعب (Matchmaking) - كما هو
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    if waiting:
        g = waiting[0]; d = generate_deck()
        p1_h, p2_h = [d.pop() for _ in range(7)], [d.pop() for _ in range(7)]
        db_query("UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s WHERE game_id=%s",
                 (user_id, ",".join(p1_h), ",".join(p2_h), d.pop(), ",".join(d), g['p1_id'], g['game_id']), commit=True, fetch=False)
        await send_player_hand(g['p1_id'], g['game_id']); await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True, fetch=False)
        await callback.message.edit_text("🔎 جاري البحث عن لاعب...")

