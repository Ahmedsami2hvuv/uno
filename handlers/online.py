import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك توليد الأوراق
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

# 2. إرسال واجهة اللعب
async def send_player_hand(user_id, game_id):
    try:
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
        
        opp_uno = game['p2_uno'] if is_p1 else game['p1_uno']
        if len(opp_hand) == 1 and not opp_uno:
            kb.append([InlineKeyboardButton(text="🚨 صيده!", callback_data=f"op_catch_{game_id}")])

        await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except Exception as e:
        print(f"❌ Error in send_hand: {e}")

# 3. محرك الربط المطور (Matchmaking)
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # أ. حذف أي محاولة بحث قديمة لنفس اللاعب لم تكتمل
    db_query("DELETE FROM active_games WHERE p1_id = %s AND status = 'waiting'", (user_id,), commit=True)
    
    # ب. البحث عن خصم "حقيقي" (لا يكون هو نفسه المستخدم) وحالته 'waiting'
    waiting_game = db_query("SELECT * FROM active_games WHERE status = 'waiting' AND p1_id != %s LIMIT 1", (user_id,))
    
    if waiting_game:
        # ✅ وجدنا خصماً!
        g = waiting_game[0]
        g_id = g['game_id']
        opponent_id = g['p1_id']
        
        # توزيع الأوراق
        deck = generate_deck()
        p1_h = [deck.pop() for _ in range(7)]
        p2_h = [deck.pop() for _ in range(7)]
        top = deck.pop()
        
        # تحديث قاعدة البيانات وبدء اللعبة فوراً
        db_query('''UPDATE active_games SET 
                    p2_id=%s, p1_hand=%s, p2_hand=%s, top_card=%s, 
                    deck=%s, status='playing', turn=%s 
                    WHERE game_id=%s''', 
                 (user_id, ",".join(p1_h), ",".join(p2_h), top, ",".join(deck), opponent_id, g_id), commit=True)
        
        await callback.message.edit_text("✅ تم العثور على خصم! جاري توزيع الأوراق...")
        
        # إرسال أوراق اللعب لكل منهما
        await send_player_hand(opponent_id, g_id)
        await send_player_hand(user_id, g_id)
        print(f"🎮 Game Started: {g_id} between {opponent_id} and {user_id}")
        
    else:
        # ⏳ لا يوجد أحد، افتح غرفة انتظار
        db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, 'waiting')", (user_id,), commit=True)
        await callback.message.edit_text("🔎 جاري البحث عن خصم... أرسل البوت لصديقك ليدخل معك الآن!")
        print(f"⏳ Player {user_id} is waiting for opponent...")

# 4. زر سحب الورقة (on_draw)
@router.callback_query(F.data.startswith("op_draw_"))
async def on_draw(c: types.CallbackQuery):
    try:
        g_id = int(c.data.split("_")[2])
        game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
        if int(c.from_user.id) != int(game['turn']): return await c.answer("مو دورك!")
        
        is_p1 = (int(c.from_user.id) == int(game['p1_id']))
        deck = [x for x in game['deck'].split(",") if x]
        hand = [x for x in (game['p1_hand'] if is_p1 else game['p2_hand']).split(",") if x]
        
        if not deck: return await c.answer("خلصت الأوراق!")
        
        new_c = deck.pop(0)
        hand.append(new_c)
        
        # إذا الورقة المسحوبة ترهم يبقى الدور عندك، وإلا ينتقل
        t_card = game['top_card']
        can_p = ("🌈" in new_c or new_c[0] == t_card[0] or (len(new_c.split())>1 and len(t_card.split())>1 and new_c.split()[1] == t_card.split()[1]))
        next_t = c.from_user.id if can_p else (game['p2_id'] if is_p1 else game['p1_id'])
        
        db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, turn=%s WHERE game_id=%s", 
                 (",".join(hand), ",".join(deck), next_t, g_id), commit=True)
        
        await c.message.delete()
        await send_player_hand(game['p1_id'], g_id)
        await send_player_hand(game['p2_id'], g_id)
    except Exception as e: print(f"Draw Error: {e}")

# (بقية الأكشن: op_play, op_uno, op_catch تبقى كما هي في الكود السابق)
