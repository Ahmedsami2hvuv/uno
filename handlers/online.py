import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. توليد الأوراق (مع الجوكر الجديد)
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

# 2. عرض يد اللاعب
async def send_player_hand(user_id, game_id, msg_text=None):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (user_id == game['p1_id'])
    hand = (game['p1_hand'] or "").split(",") if is_p1 else (game['p2_hand'] or "").split(",")
    if not hand or hand == ['']: hand = []
    
    turn_text = "🟢 دورك الآن!" if game['turn'] == user_id else "⏳ دور الخصم..."
    opp_hand = (game['p2_hand'] or "").split(",") if is_p1 else (game['p1_hand'] or "").split(",")
    opp_count = len(opp_hand) if opp_hand != [''] else 0

    if not msg_text:
        msg_text = f"🃏 الورقة المكشوفة: `{game['top_card']}`\n"
        msg_text += f"👤 الخصم لديه: {opp_count} أوراق\n{turn_text}"

    kb = []
    row = []
    for i, card in enumerate(hand):
        if card:
            row.append(InlineKeyboardButton(text=card, callback_data=f"op_play_{game_id}_{i}"))
            if len(row) == 3:
                kb.append(row)
                row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"op_draw_{game_id}")])
    kb.append([InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}")])

    await bot.send_message(user_id, msg_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. اختيار اللون (لورقة الألوان فقط)
@router.callback_query(F.data.startswith("setcol_"))
async def set_color(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    # تحديث الورقة المكشوفة للون المختار
    db_query("UPDATE active_games SET top_card = %s WHERE game_id = %s", (f"{col} (🌈)", g_id), commit=True, fetch=False)
    
    await c.message.delete()
    # بعد اختيار اللون في ورقة "الألوان العادية"، ينتقل الدور للخصم
    next_player = game['p2_id'] if c.from_user.id == game['p1_id'] else game['p1_id']
    db_query("UPDATE active_games SET turn = %s WHERE game_id = %s", (next_player, g_id), commit=True, fetch=False)
    
    await send_player_hand(game['p1_id'], g_id)
    await send_player_hand(game['p2_id'], g_id)

# 4. منطق اللعب (التحكم الكامل)
@router.callback_query(F.data.startswith("op_play_"))
async def process_play(c: types.CallbackQuery):
    _, _, g_id, idx = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    if c.from_user.id != game['turn']:
        return await c.answer("مو دورك! ⏳", show_alert=True)
    
    is_p1 = (c.from_user.id == game['p1_id'])
    hand = game['p1_hand'].split(",") if is_p1 else game['p2_hand'].split(",")
    played_card = hand[int(idx)]
    top_card = game['top_card']
    deck = game['deck'].split(",")

    # التحقق من صحة الورقة
    can_play = False
    if "🌈" in played_card: can_play = True
    else:
        t_color = top_card[0]
        t_val = top_card.split(" ")[1] if " " in top_card else top_card
        p_color = played_card[0]
        p_val = played_card.split(" ")[1] if " " in played_card else played_card
        if p_color == t_color or p_val == t_val or "🌈" in top_card: can_play = True

    if not can_play:
        await c.answer("❌ ورقة خطأ! سحب ورقتين عقوبة.", show_alert=True)
        hand.extend([deck.pop(), deck.pop()])
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s WHERE game_id=%s", 
                 (",".join(hand), ",".join(deck), g_id), commit=True, fetch=False)
        await c.message.delete()
        return await send_player_hand(c.from_user.id, g_id)

    # تنفيذ اللعب
    hand.pop(int(idx))
    # افتراضياً: الدور ينتقل للخصم (للأرقام فقط)
    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    
    # --- تطبيق قوانينك الجديدة ---
    # أي ورقة أكشن (ليست رقماً) تعيد الدور لك
    is_action = any(x in played_card for x in ["🚫", "🔄", "➕", "🌈➕"])
    # استثناء ورقة الألوان العادية (بدون سحب) فهي تنقل الدور بعد اختيار اللون
    is_plain_wild = ("🌈" in played_card and "➕" not in played_card)

    if is_action:
        next_turn = c.from_user.id # الدور يبقى عندك
        
        # إذا كانت ورقة سحب، اسحب للخصم تلقائياً
        if "➕" in played_card:
            plus = 1 if "➕1" in played_card else (2 if "➕2" in played_card else 4)
            opp_id = game['p2_id'] if is_p1 else game['p1_id']
            opp_hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(",")
            for _ in range(plus): opp_hand.append(deck.pop())
            db_query(f"UPDATE active_games SET {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", 
                     (",".join(opp_hand), ",".join(deck), g_id), commit=True, fetch=False)
            await bot.send_message(opp_id, f"⚠️ سحبت {plus} أوراق بسبب خصمك!")

    # تحديث الداتا بيس
    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, turn=%s WHERE game_id=%s",
             (played_card, ",".join(hand), next_turn, g_id), commit=True, fetch=False)

    await c.message.delete()

    if is_plain_wild:
        # ورقة ألوان عادية -> اطلب لوناً ثم سينتقل الدور للخصم (عبر set_color)
        await ask_color(c.from_user.id, g_id)
    else:
        # بقية الأوراق -> حدث الشاشات فوراً
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)

async def ask_color(user_id, game_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"setcol_{game_id}_🔴"), 
           InlineKeyboardButton(text="🔵", callback_data=f"setcol_{game_id}_🔵")],
          [InlineKeyboardButton(text="🟡", callback_data=f"setcol_{game_id}_🟡"), 
           InlineKeyboardButton(text="🟢", callback_data=f"setcol_{game_id}_🟢")]]
    await bot.send_message(user_id, "🌈 اختر اللون المطلوب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# (كود البحث عن لاعب يبقى كما هو...)
@router.callback_query(F.data == "mode_random")
async def start_matchmaking(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    if waiting:
        g = waiting[0]; d = generate_deck()
        p1_h, p2_h = [d.pop() for _ in range(7)], [d.pop() for _ in range(7)]
        top = d.pop()
        db_query("UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s WHERE game_id=%s",
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(d), g['p1_id'], g['game_id']), commit=True, fetch=False)
        await send_player_hand(g['p1_id'], g['game_id']); await send_player_hand(user_id, g['game_id'])
    else:
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True, fetch=False)
        await callback.message.edit_text("🔎 جاري البحث عن لاعب...")
