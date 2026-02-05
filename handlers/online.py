import random
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. توليد الورق
def generate_deck():
    colors = ["🔴", "🔵", "🟡", "🟢"]
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}", f"{c} {n}"])
        for a in ["🚫", "🔄", "➕2"]: deck.extend([f"{c} {a}", f"{c} {a}"])
    # إضافة الجوكر بأنواعه
    deck.extend(["🌈"] * 4)       # ملون فقط
    deck.extend(["🌈➕1"] * 4)     # جوكر +1
    deck.extend(["🌈➕2"] * 4)     # جوكر +2
    deck.extend(["🌈➕4"] * 4)     # جوكر +4
    random.shuffle(deck)
    return deck

# 2. واجهة اللعب
async def send_player_hand(user_id, game_id):
    res = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not res: return
    game = res[0]
    is_p1 = (int(user_id) == int(game['p1_id']))
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    turn_text = "🟢 دورك!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم"
    
    text = f"🃏 المكشوفة: `{game['top_card']}`\n👤 الخصم: {len(opp_hand)} أوراق\n━━━━━━━━━━━━━━\n{turn_text}"
    kb = []
    row = []
    for i, card in enumerate(my_hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"p_{game_id}_{i}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب", callback_data=f"d_{game_id}"),
               InlineKeyboardButton(text="📢 أونو!", callback_data=f"u_{game_id}")])
    
    opp_uno = game['p2_uno'] if is_p1 else game['p1_uno']
    if len(opp_hand) == 1 and not opp_uno:
        kb.append([InlineKeyboardButton(text="🚨 صيده!", callback_data=f"c_{game_id}")])

    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. معالجة لعب الورقة (القوانين والعقوبات)
@router.callback_query(F.data.startswith("p_"))
async def process_play(callback: types.CallbackQuery):
    _, g_id, idx = callback.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    if int(callback.from_user.id) != int(game['turn']):
        return await callback.answer("مو دورك! ⏳", show_alert=True)
    
    is_p1 = (int(callback.from_user.id) == int(game['p1_id']))
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    deck = [d for d in game['deck'].split(",") if d]
    played_card = my_hand[int(idx)]
    top_card = game['top_card']

    # --- فحص قانونية الورقة (Match Check) ---
    can_play = False
    if "🌈" in played_card or "🌈" in top_card:
        can_play = True
    else:
        p_color = played_card[0]
        t_color = top_card[0]
        p_val = played_card.split()[-1]
        t_val = top_card.split()[-1]
        if p_color == t_color or p_val == t_val:
            can_play = True

    # عقوبة اللعب الخطأ
    if not can_play:
        await callback.answer("❌ ورقة خطأ! عقوبة سحب ورقتين.", show_alert=True)
        for _ in range(2): 
            if deck: my_hand.append(deck.pop(0))
        next_turn = game['p2_id'] if is_p1 else game['p1_id'] # نقل الدور كعقوبة
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s",
                 (",".join(my_hand), ",".join(deck), next_turn, g_id), commit=True)
        await callback.message.delete()
        return await send_player_hand(game['p1_id'], g_id) or await send_player_hand(game['p2_id'], g_id)

    # تنفيذ اللعب الصحيح
    my_hand.pop(int(idx))

    # فحص الفوز
    if not my_hand:
        db_query("UPDATE users SET online_points = online_points + 10 WHERE user_id = %s", (callback.from_user.id,), commit=True)
        user_info = db_query("SELECT online_points FROM users WHERE user_id = %s", (callback.from_user.id,))[0]
        db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
        await callback.message.delete()
        await callback.message.answer(f"🏆 مبروك! فزت بـ 10 نقاط.\n⭐ مجموع نقاطك الحالي: {user_info['online_points']}")
        await bot.send_message(game['p2_id'] if is_p1 else game['p1_id'], f"💀 خسرتم! الخصم فاز ووصلت نقاطه لـ {user_info['online_points']}")
        return

    # منطق الأوراق الخاصة
    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    
    # ➕ أوراق السحب (تأثير فوري)
    if "➕" in played_card:
        plus_val = 0
        if "➕1" in played_card: plus_val = 1
        elif "➕2" in played_card: plus_val = 2
        elif "➕4" in played_card: plus_val = 4
        
        for _ in range(plus_val):
            if deck: opp_hand.append(deck.pop(0))
        next_turn = callback.from_user.id # يبقى الدور عندك بعد السحب
        await callback.answer(f"🔥 سحبت خصمك {plus_val} أوراق!")

    elif any(x in played_card for x in ["🚫", "🔄"]):
        next_turn = callback.from_user.id
        await callback.answer("🚫 منعت الخصم!")

    # تحديث الداتا بيس
    db_query(f'''UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, 
                {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s, p1_uno=FALSE, p2_uno=FALSE WHERE game_id=%s''', 
             (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)
    
    await callback.message.delete()
    
    # طلب اختيار لون إذا كان جوكر ملون (بدون سحب)
    if played_card == "🌈":
        await ask_color(callback.from_user.id, g_id)
    else:
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)

# 4. اختيار اللون
async def ask_color(user_id, game_id):
    kb = [[InlineKeyboardButton(text="🔴", callback_data=f"sc_{game_id}_🔴"), InlineKeyboardButton(text="🔵", callback_data=f"sc_{game_id}_🔵")],
          [InlineKeyboardButton(text="🟡", callback_data=f"sc_{game_id}_🟡"), InlineKeyboardButton(text="🟢", callback_data=f"sc_{game_id}_🟢")]]
    await bot.send_message(user_id, "🌈 اختر اللون الذي تجبر الخصم عليه:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sc_"))
async def set_color_logic(c: types.CallbackQuery):
    _, g_id, col = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    next_p = game['p2_id'] if int(c.from_user.id) == int(game['p1_id']) else game['p1_id']
    # تغيير الورقة المكشوفة للون المختار
    db_query("UPDATE active_games SET top_card=%s, turn=%s WHERE game_id=%s", (f"{col} (🌈)", next_p, g_id), commit=True)
    await c.message.delete()
    await send_player_hand(game['p1_id'], g_id)
    await send_player_hand(game['p2_id'], g_id)

# (دوال السحب d_ والأونو u_ والصيد c_ تبقى كما هي لكن تأكد من تحديث online.py بالكامل)
