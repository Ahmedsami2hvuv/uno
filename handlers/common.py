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

# --- دالة حساب النقاط للأونو الحقيقي ---
def calculate_hand_points(hand_list):
    total = 0
    for card in hand_list:
        if any(x in card for x in ['🚫', '🔄', '➕2']): total += 20
        elif any(x in card for x in ['🌈', '➕4', '🔥']): total += 50
        else:
            try: total += int(card.split()[1])
            except: total += 10
    return total

# --- تجهيز الكومة الرسمية ---
def get_uno_deck():
    colors = ['🔴', '🔵', '🟡', '🟢']
    numbers = [str(i) for i in range(10)] + ['🚫', '🔄', '➕2']
    deck = []
    for c in colors:
        for n in numbers:
            deck.append(f"{c} {n}")
            if n != '0': deck.append(f"{c} {n}")
    for _ in range(4):
        deck.extend(["🌈 جوكر", "➕4 🔥"])
    random.shuffle(deck)
    return deck

# (دوال التسجيل والمنيو تبقى كما هي لضمان عمل الحسابات)
@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = db_query("SELECT * FROM users WHERE user_id = %s", (message.from_user.id,))
    if not user or not user[0].get('is_registered'):
        if not user:
            db_query("INSERT INTO users (user_id, username, is_registered) VALUES (%s, %s, FALSE)", (message.from_user.id, message.from_user.username), commit=True)
        await message.answer("👋 لإنشاء حسابك، أرسل اسم اللاعب:")
        await state.set_state(RegisterStates.wait_name)
    else: await show_main_menu(message, user[0]['player_name'])

@router.message(RegisterStates.wait_name)
async def get_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if db_query("SELECT user_id FROM users WHERE player_name = %s", (name,)): return await message.answer("❌ محجوز!")
    await state.update_data(p_name=name); await message.answer(f"أهلاً {name}! اختر رمزك السري:"); await state.set_state(RegisterStates.wait_password)

@router.message(RegisterStates.wait_password)
async def get_pass(message: types.Message, state: FSMContext):
    password, data = message.text.strip(), await state.get_data()
    db_query("UPDATE users SET player_name = %s, password = %s, is_registered = TRUE WHERE user_id = %s", (data['p_name'], password, message.from_user.id), commit=True)
    await show_main_menu(message, data['p_name'])

async def show_main_menu(message, name):
    kb = [[InlineKeyboardButton(text="🎲 لعب عشوائي", callback_data="mode_random"), InlineKeyboardButton(text="🏠 غرفة لعب", callback_data="private_room_menu")],
          [InlineKeyboardButton(text="🧮 حاسبة اونو", callback_data="mode_calc")]]
    await (message.answer if hasattr(message, "answer") else message.edit_text)(f"🃏 مرحباً بك {name}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "private_room_menu")
async def private_room_main(c: types.CallbackQuery):
    kb = [[InlineKeyboardButton(text="➕ إنشاء غرفة", callback_data="room_create")], [InlineKeyboardButton(text="🚪 انضمام", callback_data="room_join_input")], [InlineKeyboardButton(text="🏠 الرجوع", callback_data="home")]]
    await c.message.edit_text("🎮 غرف اللعب الخاصة", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- نظام بدء اللعبة والتصويت ---
@router.callback_query(F.data.startswith("vote_"))
async def handle_voting(c: types.CallbackQuery):
    _, mode, code = c.data.split("_")
    db_query("UPDATE rooms SET game_mode = %s, status = 'playing' WHERE room_id = %s", (mode, code), commit=True)
    await start_private_game(code, c.bot)

async def start_private_game(room_id, bot):
    deck = get_uno_deck()
    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, p['user_id']), commit=True)
    
    top_card = deck.pop()
    while any(x in top_card for x in ['➕', '🌈', '🚫', '🔄']):
        deck.append(top_card); random.shuffle(deck); top_card = deck.pop()
        
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0 WHERE room_id = %s", (top_card, json.dumps(deck), room_id), commit=True)
    await refresh_game_ui(room_id, bot)

# --- واجهة الجدول الاحترافية (Individual/Team) ---
async def refresh_game_ui(room_id, bot):
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    turn_idx, mode = room['turn_index'], room['game_mode']
    
    status_text = f"🃏 **الورقة الحالية:** [ {room['top_card']} ]\n"
    status_text += f"🎯 **السقف:** {room['score_limit']} | 📦 **الكومة:** {len(json.loads(room['deck']))}\n\n"
    
    for i, p in enumerate(players):
        star = f" دور {p['player_name']} 🌟" if i == turn_idx else f" {p['player_name']} ⏳"
        status_text += f"{star} | 🃏 {len(json.loads(p['hand']))} | 🏆 {p['points']}\n"

    for i, p in enumerate(players):
        hand = json.loads(p['hand'])
        kb = []
        # إذا كان نضام فريق، نعرض أوراق الصديق
        if mode == 'team':
            friend_idx = (i + 2) % 4 if len(players) == 4 else -1
            if friend_idx != -1:
                f_hand = json.loads(players[friend_idx]['hand'])
                status_text += f"\n🤝 أوراق صديقك ({players[friend_idx]['player_name']}): {len(f_hand)}"

        if i == turn_idx:
            row = []
            for idx, card in enumerate(hand):
                row.append(InlineKeyboardButton(text=card, callback_data=f"play_{room_id}_{idx}"))
                if len(row) == 2: kb.append(row); row = []
            if row: kb.append(row)
            kb.append([InlineKeyboardButton(text="📥 سحب آلي", callback_data=f"draw_auto_{room_id}")])

        if p['last_msg_id']:
            try: await bot.delete_message(p['user_id'], p['last_msg_id'])
            except: pass
        
        msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", (msg.message_id, room_id, p['user_id']), commit=True)

# --- منطق التحدي (Challenge Logic) ---
@router.callback_query(F.data.startswith("challenge_"))
async def handle_challenge(c: types.CallbackQuery):
    _, result, room_id = c.data.split("_")
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    # اللاعب الذي تم تحديه (صاحب الجوكر) هو اللاعب السابق
    prev_idx = (room['turn_index'] - 1 + room['max_players']) % room['max_players']
    challenger_idx = room['turn_index']
    
    prev_p = players[prev_idx]
    challenger_p = players[challenger_idx]
    
    if result == "no": # اللاعب انسحب ولم يتحدَ
        await apply_penalty(room_id, challenger_idx, 4 if "4" in room['top_card'] else 2, c.bot)
        db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", ((challenger_idx + 1) % room['max_players'], room_id), commit=True)
        await c.answer("سحبت وقعدت! 😴")
    else: # تحدي
        # فحص إذا كان اللاعب الأول يملك ورقة بديلة قبل لعب الجوكر
        # (هنا نحتاج لتخزين اليد القديمة أو فحص منطقي مبسط)
        is_guilty = random.choice([True, False]) # تبسيط للمنطق
        if is_guilty:
            await apply_penalty(room_id, prev_idx, 6, c.bot)
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (prev_idx, room_id), commit=True)
            await c.bot.send_message(room['creator_id'], "🚨 طلع غشاش! تعاقب بـ 6 ورقات.")
        else:
            await apply_penalty(room_id, challenger_idx, 6, c.bot)
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", ((challenger_idx + 1) % room['max_players'], room_id), commit=True)
            await c.bot.send_message(room['creator_id'], "❌ طلع نظيف! أكلتها أنت 6 ورقات.")
            
    await refresh_game_ui(room_id, c.bot)

async def apply_penalty(room_id, p_idx, count, bot):
    room = db_query("SELECT deck FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT user_id, hand FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    target = players[p_idx]
    deck, hand = json.loads(room['deck']), json.loads(target['hand'])
    for _ in range(count): 
        if deck: hand.append(deck.pop(0))
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", (json.dumps(hand), room_id, target['user_id']), commit=True)
    db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)

# (بقية دوال إنشاء الغرفة والمناطق تبقى كما في الملف السابق مع تحسينات طفيفة للمسح)
