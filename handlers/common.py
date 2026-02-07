from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
import random
import string
import json
import asyncio

router = Router()

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

class RoomStates(StatesGroup):
    wait_for_code = State()

class RegisterStates(StatesGroup):
    wait_name = State()
    wait_password = State()

class GameStates(StatesGroup):
    waiting_for_color = State()
    waiting_for_challenge = State()

@router.message(F.photo)
async def get_photo_id(message: types.Message):
    await message.reply(f"✅ كود الصورة: `{message.photo[-1].file_id}`", parse_mode="Markdown")

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    if not user or not user[0].get('is_registered'):
        if not user:
            db_query("INSERT INTO users (user_id, username, is_registered) VALUES (%s, %s, FALSE)", 
                     (message.from_user.id, message.from_user.username), commit=True)
        await message.answer("👋 أهلاً بك! لإنشاء حسابك، أرسل اسم اللاعب الذي تريده:")
        await state.set_state(RegisterStates.wait_name)
    else:
        await show_main_menu(message, user[0]['player_name'])

@router.message(RegisterStates.wait_name)
async def get_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if db_query("SELECT user_id FROM users WHERE player_name = %s", (name,)):
        return await message.answer("❌ الاسم محجوز! اختر غيره:")
    await state.update_data(p_name=name)
    await message.answer(f"أهلاً {name}! اختر رمزاً سرياً لحسابك:")
    await state.set_state(RegisterStates.wait_password)

@router.message(RegisterStates.wait_password)
async def get_pass(message: types.Message, state: FSMContext):
    password, data = message.text.strip(), await state.get_data()
    db_query("UPDATE users SET player_name = %s, password = %s, is_registered = TRUE WHERE user_id = %s",
             (data['p_name'], password, message.from_user.id), commit=True)
    await message.answer("✅ تم تفعيل حسابك!")
    await show_main_menu(message, data['p_name'])

async def show_main_menu(message, name):
    kb = [[InlineKeyboardButton(text="🎲 لعب عشوائي", callback_data="mode_random"), 
           InlineKeyboardButton(text="🏠 غرفة لعب", callback_data="private_room_menu")],
          [InlineKeyboardButton(text="🧮 حاسبة اونو", callback_data="mode_calc")]]
    text = f"🃏 مرحباً بك {name}\nاختر ما تريد فعله:"
    if hasattr(message, "answer"): await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "private_room_menu")
async def private_room_main(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = [[InlineKeyboardButton(text="➕ إنشاء غرفة", callback_data="room_create")],
          [InlineKeyboardButton(text="🚪 انضمام لغرفة", callback_data="room_join_input")],
          [InlineKeyboardButton(text="🏠 الرجوع", callback_data="home")]]
    await c.message.edit_text("🎮 **غرف اللعب الخاصة**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "room_join_input")
async def join_room_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("📥 أرسل كود الغرفة (5 رموز):")
    await state.set_state(RoomStates.wait_for_code)

@router.message(RoomStates.wait_for_code)
async def process_room_join(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room: return await message.answer("❌ الكود غير صحيح.")
    current_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
    if any(p['user_id'] == message.from_user.id for p in current_players):
        return await message.answer("⚠️ أنت موجود أصلاً بالغرفة!")
    if len(current_players) >= room[0]['max_players']:
        return await message.answer("🚫 الغرفة ممتلئة!")
    
    user_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", 
             (code, message.from_user.id, user_data[0]['player_name']), commit=True)
    
    new_count, max_p = len(current_players) + 1, room[0]['max_players']
    await state.clear()
    await message.answer(f"✅ دخلت الغرفة `{code}`. ({new_count}/{max_p})")

    if new_count == max_p:
        if max_p == 2 or max_p % 2 != 0:
            db_query("UPDATE rooms SET game_mode = 'solo', status = 'playing' WHERE room_id = %s", (code,), commit=True)
            await start_private_game(code, message.bot)
        else:
            db_query("UPDATE rooms SET status = 'voting' WHERE room_id = %s", (code,), commit=True)
            kb = [[InlineKeyboardButton(text="👥 نظام فريق", callback_data=f"vote_team_{code}"),
                   InlineKeyboardButton(text="👤 نظام فردي", callback_data=f"vote_solo_{code}")]]
            all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
            for p in all_players:
                try: await message.bot.send_message(p['user_id'], "🎉 اكتمل العدد! صوتوا للنمط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                except: pass

@router.callback_query(F.data.startswith("vote_"))
async def handle_voting(c: types.CallbackQuery):
    _, mode, code = c.data.split("_")
    db_query("UPDATE rooms SET game_mode = %s, status = 'playing' WHERE room_id = %s", (mode, code), commit=True)
    
    # توزيع الفرق تلقائياً إذا اختاروا نظام فريق
    if mode == 'team':
        players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order", (code,))
        for i, p in enumerate(players):
            team = 1 if (i % 2 == 0) else 2
            db_query("UPDATE room_players SET team = %s WHERE room_id = %s AND user_id = %s", (team, code, p['user_id']), commit=True)
            
    await start_private_game(code, c.bot)

async def start_private_game(room_id, bot):
    colors, numbers = ['🔴', '🔵', '🟡', '🟢'], [str(i) for i in range(10)] + ['🚫', '🔄', '➕2']
    deck = [f"{c} {n}" for c in colors for n in numbers] + [f"{c} {n}" for c in colors for n in numbers if n != '0']
    for _ in range(4): deck.extend(["🌈 جوكر", "➕4 🔥"])
    random.shuffle(deck)

    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
                 (json.dumps(hand), room_id, p['user_id']), commit=True)

    top_card = deck.pop()
    # أهم سطر: نحدد اللون الابتدائي بناءً على أول ورقة
    start_color = top_card.split()[0] 
    
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0, current_color = %s, status = 'playing' WHERE room_id = %s", 
             (top_card, json.dumps(deck), start_color, room_id), commit=True)
    
    await refresh_game_ui(room_id, bot)

async def refresh_game_ui(room_id, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    turn_idx, top_card = room['turn_index'], room['top_card']
    curr_color = room.get('current_color', top_card.split()[0])
    
    status_text = f"🃏 **الورقة:** [ {top_card} ]\n🎨 **اللون المطلوب:** {curr_color}\n👥 **اللاعبين:**\n"
    for i, p in enumerate(players):
        star = "🌟" if i == turn_idx else "⏳"
        team_tag = f" (فريق {p['team']})" if p['team'] > 0 else ""
        status_text += f"{star} | {p['player_name'][:10]:<10} | 🃏 {len(json.loads(p['hand']))}{team_tag}\n"

    for p in players:
        if p.get('last_msg_id'):
            try: await bot.delete_message(p['user_id'], p['last_msg_id'])
            except: pass
        hand = json.loads(p['hand'])
        kb = []
        row = []
        for idx, card in enumerate(hand):
            row.append(InlineKeyboardButton(text=card, callback_data=f"play_{room_id}_{idx}"))
            if len(row) == 2: kb.append(row); row = []
        if row: kb.append(row)
        msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", (msg.message_id, room_id, p['user_id']), commit=True)

@router.callback_query(F.data.startswith("play_"))
async def play_card(c: types.CallbackQuery, state: FSMContext):
    _, room_id, idx = c.data.split("_")
    idx, user_id = int(idx), c.from_user.id
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players_list = db_query("SELECT user_id, hand FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    if players_list[room['turn_index']]['user_id'] != user_id:
        return await c.answer("⏳ مو دورك! انتظر النجمة 🌟", show_alert=True)
    
    player_hand = json.loads(players_list[room['turn_index']]['hand'])
    played_card = player_hand[idx]
    curr_color = room['current_color']

    # فحص المطابقة (اللون المطلوب أو الرقم أو الجوكر)
    if not (any(x in played_card for x in ['🌈', '🔥']) or 
            played_card.split()[0] == curr_color or 
            played_card.split()[1] == room['top_card'].split()[1]):
        return await c.answer(f"❌ ما ترهم على {room['top_card']} (اللون: {curr_color})", show_alert=True)

    # إذا لعب جوكر أو +4
    if any(x in played_card for x in ['🌈', '🔥']):
        await state.update_data(room_id=room_id, card_idx=idx, played_card=played_card)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔴 أحمر", callback_data=f"setcol_🔴_{room_id}"),
             InlineKeyboardButton(text="🔵 أزرق", callback_data=f"setcol_🔵_{room_id}")],
            [InlineKeyboardButton(text="🟡 أصفر", callback_data=f"setcol_🟡_{room_id}"),
             InlineKeyboardButton(text="🟢 أخضر", callback_data=f"setcol_🟢_{room_id}")]
        ])
        await c.message.answer("🎨 اختر اللون الجديد للجولة:", reply_markup=kb)
        return await c.answer()

    # تنفيذ اللعب العادي
    await finalize_move(room_id, user_id, player_hand, idx, played_card, c.bot)

async def finalize_move(room_id, user_id, hand, idx, played_card, bot):
    hand.pop(idx)
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, user_id), commit=True)
    
    if len(hand) == 0:
        await handle_win_logic(room_id, user_id, bot)
        return

    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    skip_next = False
    draw_penalty = 0
    if "🚫" in played_card: skip_next = True
    elif "➕2" in played_card: draw_penalty = 2
    elif "🔄" in played_card and room['max_players'] == 2: skip_next = True

    next_idx = (room['turn_index'] + 1) % room['max_players']
    if draw_penalty > 0:
        await apply_draw_penalty(room_id, next_idx, draw_penalty, bot)
        next_idx = (next_idx + 1) % room['max_players']
    elif skip_next:
        next_idx = (next_idx + 1) % room['max_players']

    db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s WHERE room_id = %s", 
             (played_card, played_card.split()[0], next_idx, room_id), commit=True)
    await auto_check_next_player(room_id, next_idx, played_card, bot)

@router.callback_query(F.data.startswith("setcol_"))
async def handle_wild_color(c: types.CallbackQuery, state: FSMContext):
    _, color, room_id = c.data.split("_")
    data = await state.get_data()
    played_card = data['played_card']
    
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT user_id, hand, player_name FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    # "حكم قاسي" - إرسال خيار التحدي للاعب التالي
    next_idx = (room['turn_index'] + 1) % room['max_players']
    target_player = players[next_idx]
    
    await state.update_data(chosen_color=color)
    
    challenge_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ أتحداه (غشاش)", callback_data=f"dare_{room_id}_yes"),
         InlineKeyboardButton(text="🏳️ استسلام", callback_data=f"dare_{room_id}_no")]
    ])
    
    await c.bot.send_message(target_player['user_id'], 
        f"⚠️ {c.from_user.full_name} لعب {played_card}!\nاللون المختار: {color}\n"
        f"هل تعتقد أنه يملك لون الساحة السابق؟ (إذا خسرت تسحب أوراق مضاعفة!)", reply_markup=challenge_kb)
    
    await c.message.delete()
    await c.answer("تم اختيار اللون وبانتظار قرار الخصم...")

@router.callback_query(F.data.startswith("dare_"))
async def handle_challenge_dare(c: types.CallbackQuery, state: FSMContext):
    _, room_id, choice = c.data.split("_")
    data = await state.get_data()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    challenger_idx = room['turn_index'] # اللاعب اللي لعب الجوكر
    target_idx = (challenger_idx + 1) % room['max_players'] # اللاعب اللي انطلب منه التحدي
    
    played_card = data['played_card']
    chosen_color = data['chosen_color']
    penalty = 4 if "🔥" in played_card else 0 # الـ +4 حصراً تخضع لتحدي الغش البرمجي
    
    if choice == 'yes' and penalty == 4:
        # فحص غش اللاعب: هل كان يملك لون الساحة قبل لعب الـ +4؟
        challenger_hand = json.loads(players[challenger_idx]['hand'])
        old_color = room['current_color']
        cheating = any(old_color in card for card in challenger_hand if '🌈' not in card)
        
        if cheating:
            await apply_draw_penalty(room_id, challenger_idx, 6, c.bot)
            msg = "⚔️ نجح التحدي! اللاعب كان يملك اللون وسحب 6 أوراق عقوبة!"
        else:
            await apply_draw_penalty(room_id, target_idx, 6, c.bot)
            msg = "⚔️ فشل التحدي! اللاعب لم يكن يملك اللون، سحبت 6 أوراق عقوبة!"
    else:
        if penalty == 4: await apply_draw_penalty(room_id, target_idx, 4, c.bot)
        msg = "🏳️ تم قبول الورقة دون تحدي."

    # إنهاء الحركة
    hand = json.loads(players[challenger_idx]['hand'])
    hand.pop(data['card_idx'])
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, players[challenger_idx]['user_id']), commit=True)
    
    next_idx = (target_idx + 1) % room['max_players'] if penalty == 4 else target_idx
    db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s WHERE room_id = %s", 
             (played_card, chosen_color, next_idx, room_id), commit=True)
    
    await c.message.answer(msg)
    await state.clear()
    await refresh_game_ui(room_id, c.bot)

async def handle_win_logic(room_id, user_id, bot):
    db_query("UPDATE rooms SET status = 'finished' WHERE room_id = %s", (room_id,), commit=True)
    all_players = db_query("SELECT * FROM room_players WHERE room_id = %s", (room_id,))
    result_text = "🏁 **انتهت اللعبة!**\n\n"
    for p in all_players:
        pts = calculate_hand_points(p['hand'])
        db_query("UPDATE users SET online_points = online_points + %s WHERE user_id = %s", (pts if p['user_id'] != user_id else 0, p['user_id']), commit=True)
        status = "🏆 فائز" if p['user_id'] == user_id else f"❌ خاسر (+{pts})"
        result_text += f"{status} | **{p['player_name']}**\n"
    for p in all_players:
        try: await bot.send_message(p['user_id'], result_text)
        except: pass

async def apply_draw_penalty(room_id, player_idx, count, bot):
    room = db_query("SELECT deck FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT user_id, hand FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    target = players[player_idx]
    deck = json.loads(room['deck'])
    hand = json.loads(target['hand'])
    for _ in range(count):
        if deck: hand.append(deck.pop(0))
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, target['user_id']), commit=True)
    db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
    try: await bot.send_message(target['user_id'], f"⚠️ عقوبة سحب {count} أوراق!")
    except: pass

async def auto_check_next_player(room_id, next_idx, top_card, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT user_id, hand, player_name FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    next_player = players[next_idx]
    hand = json.loads(next_player['hand'])
    curr_color = room['current_color']
    can_play = any(any(x in c for x in ['🌈', '🔥']) or c.split()[0] == curr_color or c.split()[1] == top_card.split()[1] for c in hand)
    if not can_play:
        deck = json.loads(room['deck'])
        if deck:
            new_card = deck.pop(0)
            hand.append(new_card)
            db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, next_player['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            try: await bot.send_message(next_player['user_id'], f"📥 سحب آلي: {new_card}")
            except: pass
            final_turn = (next_idx + 1) % room['max_players']
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (final_turn, room_id), commit=True)
            return await auto_check_next_player(room_id, final_turn, top_card, bot)
    await refresh_game_ui(room_id, bot)

@router.callback_query(F.data == "room_create")
async def room_create_start(c: types.CallbackQuery):
    kb, row = [], []
    for i in range(2, 11):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"setp_{i}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    await c.message.edit_text("👥 حدد عدد اللاعبين:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("setp_"))
async def set_room_players(c: types.CallbackQuery):
    num, scores = c.data.split("_")[1], [100, 200, 300, 400, 500]
    kb, row = [], []
    for s in scores:
        row.append(InlineKeyboardButton(text=str(s), callback_data=f"sets_{num}_{s}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    await c.message.edit_text(f"🎯 لاعبين: {num}. حدد السقف:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sets_"))
async def finalize_room_creation(c: types.CallbackQuery):
    _, p_count, s_limit = c.data.split("_")
    code = generate_room_code()
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit, current_color) VALUES (%s, %s, %s, %s, '🔴')", (code, c.from_user.id, int(p_count), int(s_limit)), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", (code, c.from_user.id, u_name), commit=True)
    await c.message.edit_text(f"✅ الغرفة: `{code}`"); await c.message.answer(f"`{code}`")

@router.callback_query(F.data == "home")
async def go_home(c: types.CallbackQuery, state: FSMContext):
    await state.clear(); user = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    await show_main_menu(c.message, user[0]['player_name'])

def calculate_hand_points(hand_json):
    hand = json.loads(hand_json)
    total = 0
    for card in hand:
        if any(x in card for x in ['🚫', '🔄', '➕2']): total += 20
        elif any(x in card for x in ['🌈', '➕4', '🔥']): total += 50
        else:
            try: total += int(card.split()[1])
            except: total += 10
    return total
