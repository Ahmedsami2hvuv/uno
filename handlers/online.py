import random
import asyncio
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import bot

router = Router()

# 1. محرك الأوراق (كما هو مع الجوكر الجديد)
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

# 2. عرض يد اللاعب مع نظام الأزرار المطور
async def send_player_hand(user_id, game_id, msg_text=None):
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (game_id,))[0]
    is_p1 = (user_id == game['p1_id'])
    
    # تحديد البيانات لكل لاعب
    my_hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    opp_hand = (game['p2_hand'] if is_p1 else game['p1_hand']).split(",")
    if my_hand == ['']: my_hand = []
    if opp_hand == ['']: opp_hand = []

    my_uno = game['p1_uno'] if is_p1 else game['p2_uno']
    opp_uno = game['p2_uno'] if is_p1 else game['p1_uno']

    turn_text = "🟢 دورك الآن!" if game['turn'] == user_id else "⏳ دور الخصم..."
    
    if not msg_text:
        msg_text = f"🃏 الورقة المكشوفة: `{game['top_card']}`\n"
        msg_text += f"👤 الخصم لديه: {len(opp_hand)} أوراق\n{turn_text}"

    kb = []
    # صفوف الأوراق
    row = []
    for i, card in enumerate(my_hand):
        if card:
            row.append(InlineKeyboardButton(text=card, callback_data=f"op_play_{game_id}_{i}"))
            if len(row) == 3:
                kb.append(row)
                row = []
    if row: kb.append(row)
    
    # أزرار التحكم
    control_row = [InlineKeyboardButton(text="📥 سحب ورقة", callback_data=f"op_draw_{game_id}")]
    
    # زر الأونو الذكي
    if len(my_hand) == 2: # أونو وقائي قبل لعب الورقة القبل الأخيرة
        control_row.append(InlineKeyboardButton(text="📢 أونو!", callback_data=f"op_uno_{game_id}"))
    
    # زر الصيد (يظهر للخصم إذا كان اللاعب لديه ورقة واحدة ولم يقل أونو)
    if len(opp_hand) == 1 and not opp_uno:
        control_row.append(InlineKeyboardButton(text="🚨 صيده! (عقوبة)", callback_data=f"op_catch_{game_id}"))
    
    kb.append(control_row)
    await bot.send_message(user_id, msg_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# 3. معالجة سحب الورقة (Draw)
@router.callback_query(F.data.startswith("op_draw_"))
async def process_draw(c: types.CallbackQuery):
    _, _, g_id = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    
    if c.from_user.id != game['turn']:
        return await c.answer("مو دورك تسحب! ⏳", show_alert=True)
    
    is_p1 = (c.from_user.id == game['p1_id'])
    deck = game['deck'].split(",")
    my_hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    
    if not deck: return await c.answer("خلصت الأوراق!")
    
    new_card = deck.pop(0)
    my_hand.append(new_card)
    
    # عند السحب، يسقط خيار "الأونو" الذي كان مفعلاً
    uno_field = "p1_uno" if is_p1 else "p2_uno"
    db_query(f"UPDATE active_games SET {'p1_hand' if is_p1 else 'p2_hand'}=%s, deck=%s, {uno_field}=FALSE, turn=%s WHERE game_id=%s",
             (",".join(my_hand), ",".join(deck), game['p2_id'] if is_p1 else game['p1_id'], g_id), commit=True, fetch=False)
    
    await c.message.delete()
    await send_player_hand(game['p1_id'], g_id)
    await send_player_hand(game['p2_id'], g_id)

# 4. معالجة زر الأونو والتبليغ
@router.callback_query(F.data.startswith("op_uno_"))
async def process_uno_say(c: types.CallbackQuery):
    _, _, g_id = c.data.split("_")
    is_p1 = (c.from_user.id == db_query("SELECT p1_id FROM active_games WHERE game_id = %s", (g_id,))[0]['p1_id'])
    field = "p1_uno" if is_p1 else "p2_uno"
    db_query(f"UPDATE active_games SET {field} = TRUE WHERE game_id = %s", (g_id,), commit=True, fetch=False)
    await c.answer("📢 قلّت أونو! أنت في أمان.", show_alert=True)
    await c.message.delete()
    await send_player_hand(c.from_user.id, g_id)

@router.callback_query(F.data.startswith("op_catch_"))
async def process_catch(c: types.CallbackQuery):
    _, _, g_id = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    is_p1_catching = (c.from_user.id == game['p1_id'])
    
    target_hand_field = "p2_hand" if is_p1_catching else "p1_hand"
    target_hand = (game['p2_hand'] if is_p1_catching else game['p1_hand']).split(",")
    deck = game['deck'].split(",")
    
    # عقوبة ورقتين
    target_hand.extend([deck.pop(0), deck.pop(0)])
    db_query(f"UPDATE active_games SET {target_hand_field}=%s, deck=%s WHERE game_id = %s",
             (",".join(target_hand), ",".join(deck), g_id), commit=True, fetch=False)
    
    await c.answer("🚨 فقسته! سحبته ورقتين عقوبة.")
    await bot.send_message(game['p2_id'] if is_p1_catching else game['p1_id'], "🚨 تم التبليغ عنك لأنك لم تقل أونو! سحبت ورقتين.")
    await c.message.delete()
    await send_player_hand(game['p1_id'], g_id)
    await send_player_hand(game['p2_id'], g_id)

# 5. منطق اللعب ونهاية اللعبة
@router.callback_query(F.data.startswith("op_play_"))
async def process_play(c: types.CallbackQuery):
    _, _, g_id, idx = c.data.split("_")
    game = db_query("SELECT * FROM active_games WHERE game_id = %s", (g_id,))[0]
    if c.from_user.id != game['turn']: return await c.answer("مو دورك!", show_alert=True)
    
    is_p1 = (c.from_user.id == game['p1_id'])
    my_hand = (game['p1_hand'] if is_p1 else game['p2_hand']).split(",")
    played_card = my_hand.pop(int(idx))
    
    # (هنا نضع منطق can_play كما في الكود السابق للتحقق من اللون/الرقم)
    # نختصر هنا لنركز على نهاية اللعبة:
    
    if len(my_hand) == 0:
        # 🎉 إعلان الفائز
        db_query("UPDATE active_games SET status='finished' WHERE game_id=%s", (g_id,), commit=True, fetch=False)
        await c.message.answer(f"🏆 مبروك! الفائز هو {c.from_user.first_name}")
        await bot.send_message(game['p2_id'] if is_p1 else game['p1_id'], f"💀 خسرتم! الفائز هو {c.from_user.first_name}")
        return

    # استمرار اللعبة وتحديث الدور
    next_turn = game['p2_id'] if is_p1 else game['p1_id']
    # إذا كانت ورقة أكشن، الدور يبقى كما اتفقنا...
    
    db_query(f"UPDATE active_games SET top_card=%s, {'p1_hand' if is_p1 else 'p2_hand'}=%s, turn=%s WHERE game_id=%s",
             (played_card, ",".join(my_hand), next_turn, g_id), commit=True, fetch=False)
    
    await c.message.delete()
    await send_player_hand(game['p1_id'], g_id)
    await send_player_hand(game['p2_id'], g_id)
