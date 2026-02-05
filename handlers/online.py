import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك توليد الأوراق (7 أوراق)
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

# 2. وظيفة إرسال واجهة اللعب (Hand)
async def send_player_hand(user_id, game_id):
    game_data = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))
    if not game_data: return
    game = game_data[0]
    
    is_p1 = (int(user_id) == int(game['p1_id']))
    my_hand = [c for c in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if c]
    opp_hand = [c for c in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if c]
    
    turn_text = "🟢 دورك الآن!" if int(game['turn']) == int(user_id) else "⏳ دور الخصم..."
    text = (f"🃏 المكشوفة: `{game['top_card']}`\n"
            f"👤 الخصم: {len(opp_hand)} أوراق\n"
            f"━━━━━━━━━━━━━━\n"
            f"{turn_text}")

    kb = []
    row = []
    for i, card in enumerate(my_hand):
        row.append(InlineKeyboardButton(text=card, callback_data=f"op_play_{game_id}_{i}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="📥 سحب", callback_data=f"op_draw_{game_id}"),
               InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}")])
    
    # إضافة زر "صيده" إذا كان الخصم لديه ورقة واحدة ولم يقل أونو
    opp_uno = game['p2_uno'] if is_p1 else game['p1_uno']
    if len(opp_hand) == 1 and not opp_uno:
        kb.append([InlineKeyboardButton(text="🚨 صيده!", callback_data=f"op_catch_{game_id}")])

    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. محرك الربط المطور (Matchmaking)
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # أ. تنظيف أي طلبات انتظار قديمة لهذا المستخدم لضمان عدم حدوث تعليق
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    
    # ب. البحث عن شخص آخر ينتظر حالياً
    waiting = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting:
        # ✅ وجدنا خصماً!
        g = waiting[0]
        deck = generate_deck()
        p1_h = [deck.pop() for _ in range(7)]
        p2_h = [deck.pop() for _ in range(7)]
        top = deck.pop()
        
        # تحديث المباراة لتبدأ
        db_query('''UPDATE active_games SET p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, deck=%s, status='playing', turn=%s 
                    WHERE game_id=%s''', 
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), g['p1_id'], g['game_id']), commit=True)
        
        await callback.message.edit_text("✅ تم الربط! بدأت اللعبة...")
        await send_player_hand(g['p1_id'], g['game_id'])
        await send_player_hand(user_id, g['game_id'])
    else:
        # ⏳ لا يوجد أحد، كن أنت "المنتظر"
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم... أرسل البوت لصديقك ليلعب معك الآن!")

# 4. منطق لعب الورقة (قوانين الأكشن والفوز)
@router.callback_query(F.data.startswith("op_play_"))
async def process_play(c: types.CallbackQuery):
    try:
        data = c.data.split("_")
        g_id, idx = int(data[2]), int(data[3])
        game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
        
        if int(c.from_user.id) != int(game['turn']):
            return await c.answer("مو دورك! ⏳", show_alert=True)

        is_p1 = (int(c.from_user.id) == int(game['p1_id']))
        my_hand = [h for h in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if h]
        opp_hand = [h for h in (game['p2_hand'] if is_p1 else game['p1_hand']).split(",") if h]
        played_card = my_hand.pop(idx)
        deck = game['deck'].split(",")

        # فحص الفوز
        if len(my_hand) == 0:
            db_query("UPDATE users SET online_points = online_points + 10 WHERE user_id = %s", (c.from_user.id,), commit=True)
            db_query("DELETE FROM active_games WHERE game_id = %s", (g_id,), commit=True)
            await c.message.delete()
            await c.message.answer("🏆 مبروك! فزت بـ 10 نقاط.")
            await bot.send_message(game['p2_id'] if is_p1 else game['p1_id'], "💀 خسرتم اللعبة!")
            return

        # تحديد الدور (الأكشن يرجع الدور لك)
        next_turn = game['p2_id'] if is_p1 else game['p1_id']
        if any(x in played_card for x in ["🚫", "🔄", "➕", "🌈➕"]):
            next_turn = c.from_user.id
            if "➕" in played_card:
                plus = 1 if "➕1" in played_card else (2 if "➕2" in played_card else 4)
                for _ in range(plus): 
                    if deck: opp_hand.append(deck.pop(0))
                await c.answer(f"🔥 سحبت خصمك {plus} أوراق!")

        # تحديث الحالة
        db_query(f'''UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, 
                    {'p2_hand' if is_p1 else 'p1_hand'}=%s, deck=%s, turn=%s, p1_uno=FALSE, p2_uno=FALSE WHERE game_id=%s''', 
                 (played_card, ",".join(my_hand), ",".join(opp_hand), ",".join(deck), next_turn, g_id), commit=True)

        await c.message.delete()
        if "🌈" in played_card and "➕" not in played_card:
            await ask_color(c.from_user.id, g_id)
        else:
            await send_player_hand(game['p1_id'], g_id)
            await send_player_hand(game['p2_id'], g_id)
    except: pass

# (دوال السحب، الأونو، الصيد، واختيار اللون تبقى كما في الكود السابق)
# ... (on_draw, on_uno, on_catch, ask_color, set_color_logic)
