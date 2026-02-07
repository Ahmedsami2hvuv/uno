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

class RoomStates(StatesGroup):
    wait_for_code = State()

class RegisterStates(StatesGroup):
    wait_name = State()
    wait_password = State()

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

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

# --- 2. إدارة الغرف والتصويت ---
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
    await c.message.edit_text(f"🎯 لاعبين: {num}. اختر سقف النقاط:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sets_"))
async def finalize_room_creation(c: types.CallbackQuery):
    _, p_count, s_limit = c.data.split("_")
    code = generate_room_code()
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    db_query("INSERT INTO rooms (room_id, creator_id, max_players, score_limit, current_color) VALUES (%s, %s, %s, %s, '🔴')", 
             (code, c.from_user.id, int(p_count), int(s_limit)), commit=True)
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", (code, c.from_user.id, u_name), commit=True)
    await c.message.edit_text(f"✅ كود الغرفة: `{code}`"); await c.message.answer(f"`{code}`")

@router.callback_query(F.data == "room_join_input")
async def join_room_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.edit_text("📥 أرسل كود الغرفة:")
    await state.set_state(RoomStates.wait_for_code)

@router.message(RoomStates.wait_for_code)
async def process_room_join(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (code,))
    if not room: return await message.answer("❌ الكود غير صحيح.")
    current_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
    if any(p['user_id'] == message.from_user.id for p in current_players): return await message.answer("⚠️ أنت بالداخل!")
    if len(current_players) >= room[0]['max_players']: return await message.answer("🚫 ممتلئة!")
    
    u_data = db_query("SELECT player_name FROM users WHERE user_id = %s", (message.from_user.id,))
    db_query("INSERT INTO room_players (room_id, user_id, player_name) VALUES (%s, %s, %s)", (code, message.from_user.id, u_data[0]['player_name']), commit=True)
    
    new_count, max_p = len(current_players) + 1, room[0]['max_players']
    await state.clear()
    await message.answer(f"✅ تم الانضمام ({new_count}/{max_p})")

    if new_count == max_p:
        if max_p == 2 or max_p % 2 != 0:
            db_query("UPDATE rooms SET game_mode = 'solo', status = 'playing' WHERE room_id = %s", (code,), commit=True)
            await start_private_game(code, message.bot)
        else:
            db_query("UPDATE rooms SET status = 'voting' WHERE room_id = %s", (code,), commit=True)
            kb = [[InlineKeyboardButton(text="👥 فريق", callback_data=f"vote_team_{code}"), InlineKeyboardButton(text="👤 فردي", callback_data=f"vote_solo_{code}")]]
            all_p = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
            for p in all_p: await message.bot.send_message(p['user_id'], "🎉 اكتمل العدد! صوتوا:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("vote_"))
async def handle_voting(c: types.CallbackQuery):
    _, mode, code = c.data.split("_")
    db_query("UPDATE rooms SET game_mode = %s, status = 'playing' WHERE room_id = %s", (mode, code), commit=True)
    if mode == 'team':
        players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (code,))
        for i, p in enumerate(players):
            team = 1 if (i % 2 == 0) else 2
            db_query("UPDATE room_players SET team = %s WHERE room_id = %s AND user_id = %s", (team, code, p['user_id']), commit=True)
    await start_private_game(code, c.bot)

# --- 3. محرك الأونو والواجهة ---
async def start_private_game(room_id, bot):
    colors, numbers = ['🔴', '🔵', '🟡', '🟢'], [str(i) for i in range(10)] + ['🚫', '🔄', '➕2']
    deck = [f"{c} {n}" for c in colors for n in numbers] + [f"{c} {n}" for c in colors for n in numbers if n != '0']
    for _ in range(4): deck.extend(["🌈 جوكر", "🌈 جوكر +4 🔥"])
    random.shuffle(deck)

    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s, said_uno = FALSE WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)

    top_card = deck.pop()
    while any(x in top_card for x in ['🌈', '🚫', '🔄', '➕']): top_card = deck.pop()
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0, current_color = %s WHERE room_id = %s", 
             (top_card, json.dumps(deck), top_card.split()[0], room_id), commit=True)
    await refresh_game_ui(room_id, bot)

async def refresh_game_ui(room_id, bot):
    try:
        room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
        players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
        turn_idx, top_card, curr_col = room['turn_index'], room['top_card'], room['current_color']
        deck_count = len(json.loads(room['deck']))

        status_text = f"📦 **الكومة:** {deck_count} | 🎯 **السقف:** {room['score_limit']}\n"
        status_text += f"🃏 **الورقة:** [ {top_card} ] | 🎨 **اللون:** {curr_col}\n"
        status_text += "━━━━━━━━━━━━━━\n👥 **اللاعبين:**\n"
        for i, p in enumerate(players):
            star = "🌟" if i == turn_idx else "⏳"
            team_tag = f" (فريق {p['team']})" if room['game_mode'] == 'team' else ""
            status_text += f"{star} {p['player_name'][:10]} | 🃏 {len(json.loads(p['hand']))}{team_tag}{' ✅' if p['said_uno'] else ''}\n"

        for p in players:
            if p.get('last_msg_id'):
                try: await bot.delete_message(p['user_id'], p['last_msg_id'])
                except: pass
            
            hand = json.loads(p['hand'])
            kb = []
            friend_info = ""
            if room['game_mode'] == 'team':
                friend = next(f for f in players if f['team'] == p['team'] and f['user_id'] != p['user_id'])
                friend_info = f"\n🤝 **أوراق شريكك ({friend['player_name']}):** `{json.loads(friend['hand'])}`"

            row = []
            for idx, card in enumerate(hand):
                row.append(InlineKeyboardButton(text=card, callback_data=f"play_{room_id}_{idx}"))
                if len(row) == 2: kb.append(row); row = []
            if row: kb.append(row)

            uno_row = []
            if len(hand) == 1 and not p['said_uno']: uno_row.append(InlineKeyboardButton(text="📢 أونو!", callback_data=f"uno_claim_{room_id}"))
            for other in players:
                if len(json.loads(other['hand'])) == 1 and not other['said_uno'] and other['user_id'] != p['user_id']:
                    uno_row.append(InlineKeyboardButton(text=f"🚨 بلغ عن {other['player_name']}", callback_data=f"uno_report_{room_id}_{other['user_id']}"))
                    break
            if uno_row: kb.append(uno_row)

            # كود الصور: استبدل 'FILE_ID' بكود الصورة الخاص بك
            # await bot.send_photo(p['user_id'], photo='FILE_ID', caption=status_text + friend_info, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            
            msg = await bot.send_message(p['user_id'], status_text + friend_info, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", (msg.message_id, room_id, p['user_id']), commit=True)
    except Exception as e: print(f"❌ خطأ UI: {e}")

# --- 4. منطق التحدي والجوكر ---
@router.callback_query(F.data.startswith("play_"))
async def play_card(c: types.CallbackQuery, state: FSMContext):
    _, room_id, idx = c.data.split("_")
    idx, user_id = int(idx), c.from_user.id
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    if players[room['turn_index']]['user_id'] != user_id: return await c.answer("⏳ مو دورك!", show_alert=True)
    
    hand = json.loads(players[room['turn_index']]['hand'])
    played_card = hand[idx]

    if '🌈' in played_card:
        await state.update_data(room_id=room_id, card_idx=idx, played_card=played_card)
        kb = [[InlineKeyboardButton(text=col, callback_data=f"setcol_{col}_{room_id}") for col in ['🔴', '🔵', '🟡', '🟢']]]
        await c.message.answer("🎨 اختر اللون الجديد:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return
    if not (played_card.split()[0] == room['current_color'] or played_card.split()[1] == room['top_card'].split()[1]):
        return await c.answer("❌ ما ترهم!", show_alert=True)
    await finalize_move(room_id, user_id, hand, idx, played_card, c.bot)

@router.callback_query(F.data.startswith("setcol_"))
async def handle_wild_color(c: types.CallbackQuery, state: FSMContext):
    _, color, room_id = c.data.split("_")
    data = await state.get_data()
    user_reg = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    next_p = players[(room['turn_index'] + 1) % room['max_players']]
    
    await state.update_data(chosen_color=color)
    kb = [[InlineKeyboardButton(text="⚔️ أتحداه (غشاش)", callback_data=f"dare_{room_id}_yes"),
           InlineKeyboardButton(text="🏳️ استسلام", callback_data=f"dare_{room_id}_no")]]
    
    await c.bot.send_message(next_p['user_id'], f"⚠️ {user_reg} لعب {data['played_card']}!\nهل تشك أنه يغش؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.message.edit_text(f"✅ اخترت {color}. انتظر قرار {next_p['player_name']}...")

@router.callback_query(F.data.startswith("dare_"))
async def handle_challenge_dare(c: types.CallbackQuery, state: FSMContext):
    _, room_id, choice = c.data.split("_")
    data = await state.get_data()
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))
    chall_idx = room['turn_index']
    target_idx = (chall_idx + 1) % room['max_players']
    
    if choice == 'yes':
        hand = json.loads(players[chall_idx]['hand'])
        is_guilty = any(room['current_color'] in card for card in hand if '🌈' not in card)
        penalty = 6 if "🔥" in data['played_card'] else 3
        if is_guilty:
            await apply_draw_penalty(room_id, chall_idx, penalty, c.bot)
            res = f"⚔️ نجح التحدي! {players[chall_idx]['player_name']} غشاش وسحب {penalty}!"; nt = chall_idx
        else:
            await apply_draw_penalty(room_id, target_idx, penalty, c.bot)
            res = f"❌ فشل التحدي! {players[chall_idx]['player_name']} نظيف وسحبت {penalty}!"; nt = (target_idx + 1) % room['max_players']
    else:
        penalty = 4 if "🔥" in data['played_card'] else 0
        if penalty > 0: await apply_draw_penalty(room_id, target_idx, penalty, c.bot)
        u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
        res = f"🏳️ {u_name} استسلم وسحب الأوراق."; nt = (target_idx + 1) % room['max_players'] if penalty > 0 else (chall_idx + 1) % room['max_players']

    hand = json.loads(players[chall_idx]['hand'])
    hand.pop(data['card_idx'])
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, players[chall_idx]['user_id']), commit=True)
    db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s WHERE room_id = %s", (data['played_card'], data['chosen_color'], nt, room_id), commit=True)
    await c.message.edit_text(res); await state.clear(); await refresh_game_ui(room_id, c.bot)

# --- 5. الدوال المساعدة وفوز الجولة ---
async def finalize_move(room_id, user_id, hand, idx, played_card, bot):
    hand.pop(idx)
    db_query("UPDATE room_players SET hand = %s, said_uno = FALSE WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, user_id), commit=True)
    if len(hand) == 0: await handle_win_logic(room_id, user_id, bot); return
    
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    next_idx = (room['turn_index'] + 1) % room['max_players']
    if "🚫" in played_card: next_idx = (next_idx + 1) % room['max_players']
    elif "➕2" in played_card: await apply_draw_penalty(room_id, next_idx, 2, bot); next_idx = (next_idx + 1) % room['max_players']
    elif "🔄" in played_card and room['max_players'] == 2: next_idx = (next_idx + 1) % room['max_players']
    
    db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s WHERE room_id = %s", (played_card, played_card.split()[0], next_idx, room_id), commit=True)
    await auto_check_next_player(room_id, next_idx, played_card, bot)

async def apply_draw_penalty(room_id, p_idx, count, bot, target_user_id=None):
    room = db_query("SELECT deck FROM rooms WHERE room_id = %s", (room_id,))[0]
    p = db_query("SELECT * FROM room_players WHERE room_id = %s AND user_id = %s", (room_id, target_user_id))[0] if target_user_id else db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))[p_idx]
    deck, hand = json.loads(room['deck']), json.loads(p['hand'])
    for _ in range(count): 
        if deck: hand.append(deck.pop(0))
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)
    db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)

async def handle_win_logic(room_id, user_id, bot):
    players = db_query("SELECT * FROM room_players WHERE room_id = %s", (room_id,))
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    winner = next(p for p in players if p['user_id'] == user_id)
    round_pts = sum(calculate_hand_points(p['hand']) for p in players if p['user_id'] != user_id)
    db_query("UPDATE room_players SET points = points + %s WHERE room_id = %s AND user_id = %s", (round_pts, room_id, user_id), commit=True)
    total_pts = db_query("SELECT points FROM room_players WHERE room_id = %s AND user_id = %s", (room_id, user_id))[0]['points']
    
    if total_pts >= room['score_limit']:
        res = f"🏆 **الفائز النهائي: {winner['player_name']}**\nوصل لـ {total_pts} نقطة!"
        for p in players: await bot.send_message(p['user_id'], res)
        db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
    else:
        for p in players: await bot.send_message(p['user_id'], f"🎉 {winner['player_name']} فاز بالجولة (+{round_pts})!")
        await asyncio.sleep(3); await start_private_game(room_id, bot)

async def auto_check_next_player(room_id, next_idx, top_card, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    p = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order ASC", (room_id,))[next_idx]
    hand, curr = json.loads(p['hand']), room['current_color']
    can = any('🌈' in c or c.split()[0] == curr or c.split()[1] == top_card.split()[1] for c in hand)
    if not can:
        deck = json.loads(room['deck'])
        if deck:
            new = deck.pop(0); hand.append(new)
            db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            await bot.send_message(p['user_id'], f"📥 سحب آلي: {new}")
            nt = (next_idx + 1) % room['max_players']
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (nt, room_id), commit=True)
            await auto_check_next_player(room_id, nt, top_card, bot)
    else: await refresh_game_ui(room_id, bot)

def calculate_hand_points(hand_json):
    total = 0
    for card in json.loads(hand_json):
        if any(x in card for x in ['🚫', '🔄', '➕2']): total += 20
        elif '🌈' in card: total += 50
        else:
            try: total += int(card.split()[1])
            except: total += 10
    return total

@router.callback_query(F.data == "home")
async def go_home(c: types.CallbackQuery, state: FSMContext):
    await state.clear(); u = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    await show_main_menu(c.message, u[0]['player_name'])

@router.callback_query(F.data.startswith("uno_claim_"))
async def uno_claim(c: types.CallbackQuery):
    room_id = c.data.split("_")[2]
    db_query("UPDATE room_players SET said_uno = TRUE WHERE room_id = %s AND user_id = %s", (room_id, c.from_user.id), commit=True)
    await c.answer("📢 أونووووو! 🃏🔥")

@router.callback_query(F.data.startswith("uno_report_"))
async def uno_report(c: types.CallbackQuery):
    _, _, room_id, target_id = c.data.split("_")
    target = db_query("SELECT * FROM room_players WHERE room_id = %s AND user_id = %s", (room_id, target_id))[0]
    if not target.get('said_uno'):
        await apply_draw_penalty(room_id, None, 2, c.bot, target_user_id=target_id)
        await c.answer("✅ صيد موفق! سحب 2.", show_alert=True)
        await refresh_game_ui(room_id, c.bot)
    else: await c.answer("❌ صرخها قبلك!")
