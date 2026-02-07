from aiogram import Router, types, F

from aiogram.filters import Command

from aiogram.fsm.context import FSMContext

from aiogram.fsm.state import State, StatesGroup

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db_query

import random

import string

import json


router = Router()


def generate_room_code():

    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))


class RoomStates(StatesGroup):

    wait_for_code = State()


class RegisterStates(StatesGroup):

    wait_name = State()

    wait_password = State()


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

    await start_private_game(code, c.bot)


async def start_private_game(room_id, bot):

    colors, numbers = ['🔴', '🔵', '🟡', '🟢'], [str(i) for i in range(10)] + ['🚫', '🔄', '➕2']

    deck = [f"{c} {n}" for c in colors for n in numbers] + [f"{c} {n}" for c in colors for n in numbers if n != '0']

    for _ in range(4): deck.extend(["🌈 جوكر", "➕4 🔥"])

    random.shuffle(deck)

    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))

    for p in players:

        hand = [deck.pop() for _ in range(7)]

        db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)

    top_card = deck.pop()

    while any(x in top_card for x in ['➕', '🌈', '🚫', '🔄']):

        deck.append(top_card); random.shuffle(deck); top_card = deck.pop()

    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0 WHERE room_id = %s", (top_card, json.dumps(deck), room_id), commit=True)

    await refresh_game_ui(room_id, bot)


async def refresh_game_ui(room_id, bot):

    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]

    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))

    turn_idx, top_card = room['turn_index'], room['top_card']

    status_text = f"🃏 **الورقة الحالية:** [ {top_card} ]\n👥 **اللاعبين:**\n"

    for i, p in enumerate(players):

        star = "🌟" if i == turn_idx else "⏳"

        status_text += f"{star} | {p['player_name'][:10]:<10} | 🃏 {len(json.loads(p['hand']))}\n"

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

async def play_card(c: types.CallbackQuery):

    _, room_id, idx = c.data.split("_")

    idx, user_id = int(idx), c.from_user.id

    

    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]

    players_list = db_query("SELECT user_id, hand FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))

    

    # 1. التأكد أن الدور عليه

    if players_list[room['turn_index']]['user_id'] != user_id:

        return await c.answer("⏳ مو دورك! انتظر النجمة 🌟", show_alert=True)

    

    player_hand = json.loads(players_list[room['turn_index']]['hand'])

    played_card = player_hand[idx]

    

    # 2. فحص المطابقة (اللون أو الرقم أو الجوكر)

    if not (any(x in played_card for x in ['🌈', '🔥']) or 

            played_card.split()[0] == room['top_card'].split()[0] or 

            played_card.split()[1] == room['top_card'].split()[1]):

        return await c.answer(f"❌ ما ترهم على {room['top_card']}", show_alert=True)


    # 3. تنزيل الورقة وتحديث اليد

    player_hand.pop(idx)

    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 

             (json.dumps(player_hand), room_id, user_id), commit=True)


    # فحص الفوز فوراً

    if len(player_hand) == 0:

        db_query("UPDATE rooms SET status = 'finished' WHERE room_id = %s", (room_id,), commit=True)

        

        # جلب كل اللاعبين لحساب نقاطهم

        all_players = db_query("SELECT * FROM room_players WHERE room_id = %s", (room_id,))

        result_text = "🏁 **انتهت اللعبة! النتائج النهائية:**\n\n"

        winner_name = c.from_user.full_name

        

        for p in all_players:

            points = calculate_hand_points(p['hand'])

            # تحديث نقاط اللاعب الكلية في جدول الـ users

            db_query("UPDATE users SET online_points = online_points + %s WHERE user_id = %s", 

                     (points if p['user_id'] != user_id else 0, p['user_id']), commit=True)

            

            status = "🏆 فائز" if p['user_id'] == user_id else f"❌ خاسر (+{points})"

            result_text += f"{status} | **{p['player_name']}**\n"


        # إرسال النتيجة للكل

        for p in all_players:

            try:

                # مسح آخر رسالة جدول

                if p['last_msg_id']:

                    await c.bot.delete_message(p['user_id'], p['last_msg_id'])

                await c.bot.send_message(p['user_id'], result_text)

            except: pass

        

        return await c.answer("🏆 مبروك الفوز وحصد النقاط!")


    # 5. منطق الأكشنات (المنع والسحب)

    skip_next = False

    draw_penalty = 0

    

    if "🚫" in played_card:

        skip_next = True

    elif "➕2" in played_card:

        draw_penalty = 2

    elif "➕4" in played_card or "🔥" in played_card:

        draw_penalty = 4

    elif "🔄" in played_card and room['max_players'] == 2:

        skip_next = True # في لاعبين الـ Reverse تشتغل Skip


    # 6. حساب اللاعب القادم وتطبيق العقوبة

    next_idx = (room['turn_index'] + 1) % room['max_players']

    

    if draw_penalty > 0:

        await apply_draw_penalty(room_id, next_idx, draw_penalty, c.bot)

        next_idx = (next_idx + 1) % room['max_players'] # طفرنا اللي انسحبله

    elif skip_next:

        next_idx = (next_idx + 1) % room['max_players'] # طفرنا الممنوع


    # 7. تحديث الغرفة ونقل الدور

    db_query("UPDATE rooms SET top_card = %s, turn_index = %s WHERE room_id = %s", 

             (played_card, next_idx, room_id), commit=True)


    await c.answer(f"✅ لعبت {played_card}")

    

    # 8. الفحص الآلي للاعب القادم (إذا يحتاج يسحب)

    await auto_check_next_player(room_id, next_idx, played_card, c.bot)


# --- 🚨 دالة عقوبة السحب (لازم تضيفها بنهاية الملف) ---

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

    

    try: await bot.send_message(target['user_id'], f"⚠️ أكلت عقوبة سحب {count} أوراق وطار دورك! 🔥")

    except: pass

async def auto_check_next_player(room_id, next_idx, top_card, bot):

    room = db_query("SELECT deck, max_players FROM rooms WHERE room_id = %s", (room_id,))[0]

    players = db_query("SELECT user_id, hand, player_name FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))

    next_player = players[next_idx]

    hand = json.loads(next_player['hand'])

    can_play = any(any(x in c for x in ['🌈', '🔥']) or c.split()[0] == top_card.split()[0] or c.split()[1] == top_card.split()[1] for c in hand)

    if not can_play:

        deck = json.loads(room['deck'])

        if deck:

            new_card = deck.pop(0)

            hand.append(new_card)

            db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, next_player['user_id']), commit=True)

            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)

            try: await bot.send_message(next_player['user_id'], f"📥 سحبنالك آلي: {new_card}")

            except: pass

            # فحص إذا الورقة اللي سحبها ترهم (اختياري، هنا سنعبر الدور)

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

    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit) VALUES (%s, %s, %s, %s)", (code, c.from_user.id, int(p_count), int(s_limit)), commit=True)

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

        if any(x in card for x in ['🚫', '🔄', '➕2']):

            total += 20

        elif any(x in card for x in ['🌈', '➕4', '🔥']):

            total += 50

        else:

            # استخراج الرقم من مثل "🔴 7"

            try:

                num = int(card.split()[1])

                total += num

            except:

                total += 10 # احتياط

    return total
