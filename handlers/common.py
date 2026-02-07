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

# --- 1. نظام الحسابات والقائمة الرئيسية ---
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

# --- 2. نظام إنشاء الغرف واللاعبين ---
@router.callback_query(F.data == "private_room_menu")
async def private_room_main(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = [[InlineKeyboardButton(text="➕ إنشاء غرفة", callback_data="room_create")],
          [InlineKeyboardButton(text="🚪 انضمام لغرفة", callback_data="room_join_input")],
          [InlineKeyboardButton(text="🏠 الرجوع", callback_data="home")]]
    await c.message.edit_text("🎮 **غرف اللعب الخاصة**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "room_create")
async def room_create_start(c: types.CallbackQuery):
    kb, row = [], []
    for i in range(2, 11):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"setp_{i}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    await c.message.edit_text("👥 حدد عدد اللاعبين الكلي (2-10):", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("setp_"))
async def set_room_players(c: types.CallbackQuery):
    num = c.data.split("_")[1]
    scores = [100, 150, 200, 250, 300, 350, 400, 450, 500]
    kb, row = [], []
    for s in scores:
        row.append(InlineKeyboardButton(text=str(s), callback_data=f"sets_{num}_{s}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    await c.message.edit_text(f"🎯 لاعبين: {num}. اختر سقف النقاط للجولات:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sets_"))
async def finalize_room_creation(c: types.CallbackQuery):
    _, p_count, s_limit = c.data.split("_")
    code = generate_room_code()
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit, current_color) VALUES (%s, %s, %s, %s, '🔴')", 
             (code, c.from_user.id, int(p_count), int(s_limit)), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", (code, c.from_user.id, u_name), commit=True)
    await c.message.edit_text(f"✅ تم إنشاء الغرفة!\n🔑 الكود: `{code}`\n\nأرسل الكود لأصدقائك."); await c.message.answer(f"`{code}`")

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
        # 🚨 التعديل هنا: إذا كان العدد 2، نبدأ فوراً "فردي" بدون تصويت
        if max_p == 2:
            db_query("UPDATE rooms SET game_mode = 'solo', status = 'playing' WHERE room_id = %s", (code,), commit=True)
            await message.answer("🚀 اكتمل العدد! جاري بدء اللعب (1 ضد 1)...")
            await start_private_game(code, message.bot)
        
        # إذا كان العدد فردي (3، 5، 7...) يلعبون فردي تلقائياً
        elif max_p % 2 != 0: 
            db_query("UPDATE rooms SET game_mode = 'solo', status = 'playing' WHERE room_id = %s", (code,), commit=True)
            await start_private_game(code, message.bot)
            
        # إذا كان العدد زوجي وأكثر من 2 (4، 6، 8...) نسوي تصويت
        else:
            db_query("UPDATE rooms SET status = 'voting' WHERE room_id = %s", (code,), commit=True)
            kb = [[InlineKeyboardButton(text="👥 نظام فريق", callback_data=f"vote_team_{code}"),
                   InlineKeyboardButton(text="👤 نظام فردي", callback_data=f"vote_solo_{code}")]]
            all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
            for p in all_players:
                try: await message.bot.send_message(p['user_id'], "🎉 اكتمل العدد! صوتوا لنظام اللعب:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                except: pass
@router.callback_query(F.data.startswith("vote_"))
async def handle_voting(c: types.CallbackQuery):
    _, mode, code = c.data.split("_")
    db_query("UPDATE rooms SET game_mode = %s, status = 'playing' WHERE room_id = %s", (mode, code), commit=True)
    if mode == 'team': # توزيع الفرق (1 و 3 فريق، 2 و 4 فريق)
        players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (code,))
        for i, p in enumerate(players):
            team = 1 if (i % 2 == 0) else 2
            db_query("UPDATE room_players SET team = %s WHERE room_id = %s AND user_id = %s", (team, code, p['user_id']), commit=True)
    await start_private_game(code, c.bot)

# --- 3. محرك لعبة الأونو (7 أوراق + قوانين قاسية) ---
async def start_private_game(room_id, bot):
    # إنشاء الكومة الرسمية
    colors, numbers = ['🔴', '🔵', '🟡', '🟢'], [str(i) for i in range(10)] + ['🚫', '🔄', '➕2']
    deck = [f"{c} {n}" for c in colors for n in numbers] + [f"{c} {n}" for c in colors for n in numbers if n != '0']
    for _ in range(4): deck.extend(["🌈 جوكر", "🌈 جوكر +4 🔥"])
    random.shuffle(deck)

    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)

    top_card = deck.pop()
    while any(x in top_card for x in ['🌈', '🚫', '🔄', '➕']):
        deck.append(top_card); random.shuffle(deck); top_card = deck.pop()
    
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0, current_color = %s WHERE room_id = %s", 
             (top_card, json.dumps(deck), top_card.split()[0], room_id), commit=True)
    await refresh_game_ui(room_id, bot)

async def refresh_game_ui(room_id, bot):
    try:
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        
        players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
        
        turn_idx = room['turn_index']
        top_card = room['top_card']
        curr_color = room['current_color']
        deck_count = len(json.loads(room['deck']))

        # --- بناء رسالة الحالة ---
        status_text = f"📦 **الكومة:** {deck_count} | 🎯 **السقف:** {room['score_limit']}\n"
        status_text += "━━━━━━━━━━━━━━\n"
        status_text += f"🃏 **الورقة:** [ {top_card} ]\n"
        status_text += f"🎨 **اللون:** {curr_color}\n"
        status_text += "━━━━━━━━━━━━━━\n"
        status_text += "👥 **اللاعبين:**\n"
        
        for i, p in enumerate(players):
            star = "🌟" if i == turn_idx else "⏳"
            team_tag = f" (فريق {p['team']})" if room['game_mode'] == 'team' else ""
            uno_tag = " ✅" if p.get('said_uno') else "" # علامة إذا گال أونو
            status_text += f"{star} {p['player_name'][:10]} | 🃏 {len(json.loads(p['hand']))}{team_tag}{uno_tag}\n"

        for p in players:
            # مسح الرسالة القديمة
            if p.get('last_msg_id'):
                try: await bot.delete_message(p['user_id'], p['last_msg_id'])
                except: pass

            hand = json.loads(p['hand'])
            kb = []
            
            # معلومات الصديق
            friend_info = ""
            if room['game_mode'] == 'team':
                friend = next((f for f in players if f['team'] == p['team'] and f['user_id'] != p['user_id']), None)
                if friend:
                    friend_hand = json.loads(friend['hand'])
                    friend_info = f"\n\n🤝 **صديقك ({friend['player_name']}) عنده:**\n`{', '.join(friend_hand)}`"

            # أزرار الأوراق
            row = []
            for idx, card in enumerate(hand):
                row.append(InlineKeyboardButton(text=card, callback_data=f"play_{room_id}_{idx}"))
                if len(row) == 2:
                    kb.append(row); row = []
            if row: kb.append(row)

            # --- إضافة أزرار الأونو والتبليغ ---
            uno_row = []
            if len(hand) == 1:
                # إذا اللاعب عنده ورقة وحدة وما صرخ أونو يطلعله الزر
                if not p.get('said_uno'):
                    uno_row.append(InlineKeyboardButton(text="📣 أونووووو!", callback_data=f"uno_claim_{room_id}"))
            
            # فحص إذا اكو خصم ناسي يگول أونو حتى نطلع زر التبليغ
            for other_p in players:
                other_hand_len = len(json.loads(other_p['hand']))
                if other_hand_len == 1 and not other_p.get('said_uno') and other_p['user_id'] != p['user_id']:
                    uno_row.append(InlineKeyboardButton(text=f"🚨 بلغ عن {other_p['player_name']}", callback_data=f"uno_report_{room_id}_{other_p['user_id']}"))
                    break # نكتفي بتبليغ واحد
            
            if uno_row:
                kb.append(uno_row)

            # إرسال الرسالة
            final_message = status_text + friend_info
            msg = await bot.send_message(
                p['user_id'], 
                final_message, 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
            )
            
            db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", 
                    (msg.message_id, room_id, p['user_id']), commit=True)
                    
    except Exception as e:
        print(f"❌ خطأ في الواجهة: {e}")
@router.callback_query(F.data.startswith("uno_claim_"))
async def uno_claim(c: types.CallbackQuery):
    room_id = c.data.split("_")[2]
    db_query("UPDATE room_players SET said_uno = TRUE WHERE room_id = %s AND user_id = %s", (room_id, c.from_user.id), commit=True)
    await c.answer("📢 صرخت أونو! بطل 🃏", show_alert=False)
    # نبلغ الكل بالكروب
    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (room_id,))
    for p in players:
        try: await c.bot.send_message(p['user_id'], f"📣 {c.from_user.full_name} يصيح: أونووووو! 🃏🔥")
        except: pass

@router.callback_query(F.data.startswith("uno_report_"))
async def uno_report(c: types.CallbackQuery):
    _, _, room_id, target_id = c.data.split("_")
    target = db_query("SELECT * FROM room_players WHERE room_id = %s AND user_id = %s", (room_id, target_id))[0]
    
    if not target.get('said_uno'):
        # عقوبة: سحب ورقتين
        await apply_draw_penalty(room_id, None, 2, c.bot, target_user_id=target_id)
        await c.answer("✅ تم صيده! سحب ورقتين عقوبة.", show_alert=True)
        await refresh_game_ui(room_id, c.bot)
    else:
        await c.answer("❌ هو گال أونو قبلك! ركز وياه المرة الجاية.", show_alert=True)



# --- 4. معالجة لعب الورق والتحدي ---
@router.callback_query(F.data.startswith("play_"))
async def play_card(c: types.CallbackQuery, state: FSMContext):
    _, room_id, idx = c.data.split("_")
    idx, user_id = int(idx), c.from_user.id
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    if players[room['turn_index']]['user_id'] != user_id:
        return await c.answer("⏳ مو دورك! تفرج على أوراق صديقك وخطط 🌟", show_alert=True)
    
    hand = json.loads(players[room['turn_index']]['hand'])
    played_card = hand[idx]

    # الجوكر و نظام التحدي
    if '🌈' in played_card:
        await state.update_data(room_id=room_id, card_idx=idx, played_card=played_card)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔴", callback_data=f"wild_🔴_{room_id}"), InlineKeyboardButton(text="🔵", callback_data=f"wild_🔵_{room_id}")],
            [InlineKeyboardButton(text="🟡", callback_data=f"wild_🟡_{room_id}"), InlineKeyboardButton(text="🟢", callback_data=f"wild_🟢_{room_id}")]
        ])
        await c.message.answer(f"🎨 لعبت {played_card}! اختر اللون:", reply_markup=kb)
        return

    # فحص المطابقة
    if not (played_card.split()[0] == room['current_color'] or played_card.split()[1] == room['top_card'].split()[1]):
        return await c.answer("❌ الورقة لا تطابق اللون أو الرقم!", show_alert=True)

    await finalize_move(room_id, user_id, hand, idx, played_card, c.bot)

@router.callback_query(F.data.startswith("wild_"))
async def handle_wild(c: types.CallbackQuery, state: FSMContext):
    _, color, room_id = c.data.split("_")
    data = await state.get_data()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    next_idx = (room['turn_index'] + 1) % room['max_players']
    target = players[next_idx]
    
    await state.update_data(chosen_color=color)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ أتحداك (غشاش)", callback_data=f"dare_{room_id}_yes"),
         InlineKeyboardButton(text="🏳️ استسلام", callback_data=f"dare_{room_id}_no")]
    ])
    await c.bot.send_message(target['user_id'], f"⚠️ {c.from_user.full_name} لعب {data['played_card']} وغير اللون لـ {color}!\nهل تشك أنه يغش؟", reply_markup=kb)
    await c.message.delete()

@router.callback_query(F.data.startswith("dare_"))
async def handle_dare(c: types.CallbackQuery, state: FSMContext):
    _, room_id, choice = c.data.split("_")
    data = await state.get_data()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    
    challenger_idx = room['turn_index']
    target_idx = (challenger_idx + 1) % room['max_players']
    
    if choice == 'yes':
        # فحص الغش: هل كان يملك لون الساحة قبل لعب الجوكر؟
        hand = json.loads(players[challenger_idx]['hand'])
        cheating = any(room['current_color'] in card for card in hand if '🌈' not in card)
        if cheating:
            penalty = 6 if "+4" in data['played_card'] else 3
            await apply_draw_penalty(room_id, challenger_idx, penalty, c.bot)
            msg = f"⚔️ نجح التحدي! {players[challenger_idx]['player_name']} غشاش وسحب {penalty} أوراق!"
            next_turn = challenger_idx # الدور يبقى عنده لأنه غش
        else:
            penalty = 6 if "+4" in data['played_card'] else 3
            await apply_draw_penalty(room_id, target_idx, penalty, c.bot)
            msg = "❌ فشل التحدي! الخصم نظيف. سحبت عقوبة مضاعفة!"
            next_turn = (target_idx + 1) % room['max_players']
    else:
        penalty = 4 if "+4" in data['played_card'] else 0
        if penalty > 0: await apply_draw_penalty(room_id, target_idx, penalty, c.bot)
        msg = "🏳️ تم قبول الورقة."; next_turn = (target_idx + 1) % room['max_players'] if penalty > 0 else (challenger_idx + 1) % room['max_players']

    # تحديث اليد وإكمال الحركة
    hand = json.loads(players[challenger_idx]['hand'])
    hand.pop(data['card_idx'])
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, players[challenger_idx]['user_id']), commit=True)
    db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s WHERE room_id = %s", (data['played_card'], data['chosen_color'], next_turn, room_id), commit=True)
    await c.message.answer(msg); await state.clear(); await refresh_game_ui(room_id, c.bot)

async def finalize_move(room_id, user_id, hand, idx, played_card, bot):
    # حذف الورقة من اليد
    hand.pop(idx)
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
             (json.dumps(hand), room_id, user_id), commit=True)
    
    # فحص الفوز بالجولة
    if len(hand) == 0:
        await handle_win_logic(room_id, user_id, bot)
        return

    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    next_idx = (room['turn_index'] + 1) % room['max_players']
    
    # تطبيق الأكشنات (المنع، السحب، الـ Reverse)
    if "🚫" in played_card:
        next_idx = (next_idx + 1) % room['max_players']
    elif "➕2" in played_card:
        await apply_draw_penalty(room_id, next_idx, 2, bot)
        next_idx = (next_idx + 1) % room['max_players']
    elif "🔄" in played_card:
        if room['max_players'] == 2:
            next_idx = (next_idx + 1) % room['max_players'] # بالـ 2 لاعبين تصير Skip
        else:
            # هنا ممكن تبرمج نظام عكس الاتجاه (Direction) إذا ردت مستقبلاً
            pass

    # تحديث الساحة ونقل الدور واللون
    db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s WHERE room_id = %s", 
             (played_card, played_card.split()[0], next_idx, room_id), commit=True)
    
    # فحص إذا اللاعب الجاي يحتاج سحب آلي
    await auto_check_next_player(room_id, next_idx, played_card, bot)


async def apply_draw_penalty(room_id, player_idx, count, bot):
    room = db_query("SELECT deck FROM rooms WHERE room_id = %s", (room_id,))[0]
    player = db_query("SELECT user_id, hand FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))[player_idx]
    deck, hand = json.loads(room['deck']), json.loads(player['hand'])
    for _ in range(count): 
        if deck: hand.append(deck.pop(0))
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, player['user_id']), commit=True)
    db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)

async def handle_win_logic(room_id, user_id, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s", (room_id,))
    winner = next(p for p in players if p['user_id'] == user_id)
    
    # حساب النقاط للجولة
    round_points = sum(calculate_hand_points(p['hand']) for p in players if p['user_id'] != user_id)
    db_query("UPDATE room_players SET points = points + %s WHERE room_id = %s AND user_id = %s", (round_points, room_id, user_id), commit=True)
    
    new_points = db_query("SELECT points FROM room_players WHERE room_id = %s AND user_id = %s", (room_id, user_id))[0]['points']
    
    if new_points >= room['score_limit']: # فوز نهائي
        result = f"🏆 **الفائز النهائي: {winner['player_name']}**\nوصل للسقف بـ {new_points} نقطة!"
        db_query("UPDATE rooms SET status = 'finished' WHERE room_id = %s", (room_id,), commit=True)
        for p in players:
            try: await bot.send_message(p['user_id'], result)
            except: pass
    else: # جولة جديدة
        for p in players:
            try: await bot.send_message(p['user_id'], f"🎉 {winner['player_name']} فاز بالجولة وحصل على {round_points} نقطة!\nجاري بدء جولة جديدة...")
            except: pass
        await asyncio.sleep(3); await start_private_game(room_id, bot)

# دالة فحص الغش (هل يملك اللاعب اللون المطلوب؟)
def check_if_cheating(player_hand, current_color):
    hand = json.loads(player_hand)
    # إذا اللاعب عنده ورقة من نفس اللون المطلوب فهو "غشاش" إذا لعب الجوكر
    return any(current_color in card for card in hand if '🌈' not in card)

# معالج التحدي
@router.callback_query(F.data.startswith("dare_"))
async def handle_challenge(c: types.CallbackQuery, state: FSMContext):
    _, room_id, choice = c.data.split("_")
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    challenger_idx = room['turn_index'] # اللاعب اللي لعب الجوكر
    victim_idx = (challenger_idx + 1) % room['max_players']
    
    if choice == 'yes': # اللاعب قرر يتحدى
        is_guilty = check_if_cheating(players[challenger_idx]['hand'], room['current_color'])
        
        if is_guilty:
            # نجح التحدي: الغشاش يسحب 6 أوراق والدور يرجعله يلعب صح
            await apply_draw_penalty(room_id, challenger_idx, 6, c.bot)
            msg = f"⚔️ نجح التحدي! {players[challenger_idx]['player_name']} طلع غشاش وسحب 6 أوراق! الدور إلك مرة ثانية تلعب صح."
            next_turn = challenger_idx
        else:
            # فشل التحدي: المتحدي يسحب 6 أوراق ويطفر دوره
            await apply_draw_penalty(room_id, victim_idx, 6, c.bot)
            msg = f"❌ فشل التحدي! {players[challenger_idx]['player_name']} نظيف. {players[victim_idx]['player_name']} سحب 6 أوراق عقوبة!"
            next_turn = (victim_idx + 1) % room['max_players']
    else:
        # استسلام: سحب 4 أوراق طبيعي
        await apply_draw_penalty(room_id, victim_idx, 4, c.bot)
        msg = f"🏳️ {players[victim_idx]['player_name']} استسلم وسحب 4 أوراق."
        next_turn = (victim_idx + 1) % room['max_players']

    db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_turn, room_id), commit=True)
    await c.message.answer(msg)
    await refresh_game_ui(room_id, c.bot)

async def auto_check_next_player(room_id, next_idx, top_card, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    player = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))[next_idx]
    hand, curr_col = json.loads(player['hand']), room['current_color']
    can_play = any('🌈' in c or c.split()[0] == curr_col or c.split()[1] == top_card.split()[1] for c in hand)
    if not can_play:
        deck = json.loads(room['deck'])
        if deck:
            new_card = deck.pop(0); hand.append(new_card)
            db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, player['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            try: await bot.send_message(player['user_id'], f"📥 ما عندك ورقة؟ سحبنالك آلي: {new_card}")
            except: pass
            next_turn = (next_idx + 1) % room['max_players']
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_turn, room_id), commit=True)
            await auto_check_next_player(room_id, next_turn, top_card, bot)
    else: await refresh_game_ui(room_id, bot)

def calculate_hand_points(hand_json):
    hand = json.loads(hand_json); total = 0
    for card in hand:
        if any(x in card for x in ['🚫', '🔄', '➕2']): total += 20
        elif '🌈' in card: total += 50
        else:
            try: total += int(card.split()[1])
            except: total += 10
    return total

@router.callback_query(F.data == "home")
async def go_home(c: types.CallbackQuery, state: FSMContext):
    await state.clear(); user = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    await show_main_menu(c.message, user[0]['player_name'])
