from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query
from config import IMG_UNO_SAFE_ME, IMG_UNO_SAFE_OPP, IMG_CATCH_SUCCESS, IMG_CATCH_PENALTY
import json, random, asyncio, uuid
from collections import Counter

router = Router()
turn_timers = {}
TURN_TIMEOUT = 20

class GameStates(StatesGroup):
    choosing_color = State()

def safe_load(data):
    if data is None: return []
    if isinstance(data, list): return data
    try: return json.loads(data)
    except: return []

def get_ordered_players(room_id):
    players = db_query("SELECT * FROM room_players WHERE room_id = %s", (room_id,))
    players.sort(key=lambda x: (x.get('join_order') or 0, x['user_id']))
    return players

def make_end_kb(players, room, mode='2p', for_user_id=None):
    from handlers.common import replay_data
    replay_id = str(uuid.uuid4())[:8]
    replay_data[replay_id] = {
        'players': [(p['user_id'], p.get('player_name') or 'لاعب') for p in players],
        'max_players': room.get('max_players', 2),
        'score_limit': room.get('score_limit', 0),
        'mode': mode,
        'creator_id': room.get('creator_id')
    }
    kb = []
    if for_user_id:
        for p in players:
            if p['user_id'] != for_user_id:
                p_name = p.get('player_name') or 'لاعب'
                kb.append([InlineKeyboardButton(text=f"➕ إضافة {p_name}", callback_data=f"addfrnd_{p['user_id']}")])
    kb.append([InlineKeyboardButton(text="🔄 لعب مرة أخرى", callback_data=f"replay_{replay_id}")])
    kb.append([InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def generate_h2o_deck():
    colors = ['🔴', '🔵', '🟡', '🟢']
    deck = []
    for c in colors:
        deck.append(f"{c} 0")
        for n in range(1, 10): deck.extend([f"{c} {n}"] * 2)
        deck.extend([f"{c} 🚫", f"{c} 🔄", f"{c} ⬆️2"] * 2)
    deck.extend(["🌈 جوكر"] * 4)
    deck.extend(["🔥 جوكر+4"] * 4)
    deck.append("💧 جوكر+1")
    deck.append("🌊 جوكر+2")
    random.shuffle(deck)
    return deck

def check_validity(card, top_card, current_color):
    if any(x in card for x in ["🌈", "🔥", "💧", "🌊"]): return True
    parts = card.split()
    if len(parts) < 2: return False
    c_color, c_value = parts[0], parts[1]
    if c_color == current_color: return True
    top_parts = top_card.split()
    top_value = top_parts[1] if len(top_parts) > 1 else top_parts[0]
    if c_value == top_value: return True
    print(f"⚠️ رفض الورقة: لعبت ({card}) | الساحة ({top_card}) | اللون المطلوب ({current_color})")
    return False

def calculate_points(hand):
    total = 0
    for card in hand:
        if any(x in card for x in ["🌈", "🔥", "💧", "🌊"]): total += 50
        elif any(x in card for x in ["🚫", "🔄", "⬆️2"]): total += 20
        else:
            try: total += int(card.split()[-1])
            except: total += 10
    return total

def sort_hand(hand):
    card_counts = Counter(card.split()[0] for card in hand if card.split()[0] in ['🔴', '🔵', '🟡', '🟢'])
    def card_sort_key(card):
        parts = card.split()
        color = parts[0]
        if any(x in card for x in ["🌈", "🔥", "💧", "🌊"]): return (3, 0, card)
        if color in ['🔴', '🔵', '🟡', '🟢']:
            count = card_counts.get(color, 0)
            return (0, -count, color, card) if count > 1 else (1, color, card)
        return (2, card)
    hand.sort(key=card_sort_key)
    return hand

countdown_msgs = {}
challenge_timers = {}
challenge_countdown_msgs = {}
color_timers = {}
color_countdown_msgs = {}
pending_color_data = {}
color_timed_out = set()

def cancel_color_timer(room_id):
    task = color_timers.pop(room_id, None)
    if task and not task.done(): task.cancel()
    cd = color_countdown_msgs.pop(room_id, None)
    if cd: asyncio.create_task(_delete_countdown(cd['bot'], cd['chat_id'], cd['msg_id']))
    pending_color_data.pop(room_id, None)

def cancel_challenge_timer(room_id):
    task = challenge_timers.pop(room_id, None)
    if task and not task.done(): task.cancel()
    cd = challenge_countdown_msgs.pop(room_id, None)
    if cd: asyncio.create_task(_delete_countdown(cd['bot'], cd['chat_id'], cd['msg_id']))

def cancel_timer(room_id):
    task = turn_timers.pop(room_id, None)
    if task and not task.done():
        task.cancel()
    cd = countdown_msgs.pop(room_id, None)
    if cd:
        asyncio.create_task(_delete_countdown(cd['bot'], cd['chat_id'], cd['msg_id']))
    cancel_color_timer(room_id)
    cancel_challenge_timer(room_id)
    color_timed_out.discard(room_id)

async def _delete_countdown(bot, chat_id, msg_id):
    try: await bot.delete_message(chat_id, msg_id)
    except: pass

async def _send_temp_photo(bot, chat_id, photo_id, delay=3):
    try:
        msg = await bot.send_photo(chat_id, photo_id)
        await asyncio.sleep(delay)
        try: await bot.delete_message(chat_id, msg.message_id)
        except: pass
    except: pass

async def _send_photo_then_schedule_delete(bot, chat_id, photo_id, delay=3):
    try:
        msg = await bot.send_photo(chat_id, photo_id)
        async def _del():
            await asyncio.sleep(delay)
            try: await bot.delete_message(chat_id, msg.message_id)
            except: pass
        asyncio.create_task(_del())
    except: pass

async def turn_timeout_2p(room_id, bot, expected_turn):
    try:
        cd_info = countdown_msgs.get(room_id)
        for step in range(10, 0, -1):
            remaining = step * 2
            bar = "🟢" * step + "⚫" * (10 - step)
            
            if cd_info:
                try:
                    # حذف الرسالة القديمة
                    await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
                except:
                    pass
                
                try:
                    # إرسال رسالة جديدة
                    new_msg = await bot.send_message(
                        cd_info['chat_id'],
                        f"⏳ باقي {remaining} ثانية\n{bar}"
                    )
                    cd_info['msg_id'] = new_msg.message_id
                except Exception as e:
                    print(f"Countdown send error: {e}")
            
            await asyncio.sleep(2)
            
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        if room['status'] != 'playing': return
        players = get_ordered_players(room_id)
        curr_idx = room['turn_index']
        if curr_idx != expected_turn: return
        curr_p = players[curr_idx]
        p_name = curr_p.get('player_name') or "لاعب"
        curr_hand = safe_load(curr_p['hand'])
        deck = safe_load(room['deck'])
        if not deck:
            discard = safe_load(room['discard_pile'])
            if discard:
                deck = discard
                random.shuffle(deck)
                db_query("UPDATE rooms SET discard_pile = '[]' WHERE room_id = %s", (room_id,), commit=True)
            else:
                deck = generate_h2o_deck()
        new_card = deck.pop(0)
        curr_hand.append(new_card)
        next_turn = (curr_idx + 1) % 2
        db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(curr_hand), curr_p['user_id']), commit=True)
        db_query("UPDATE rooms SET deck = %s, turn_index = %s WHERE room_id = %s", (json.dumps(deck), next_turn, room_id), commit=True)
        opp_id = players[(curr_idx + 1) % 2]['user_id']
        msgs = {
            curr_p['user_id']: f"⏰ انتهى وقتك! سحبت ورقة ({new_card}) وعبر الدور",
            opp_id: f"⏰ {p_name} ما لعب بالوقت! سحب ورقة والدور رجع لك ✅"
        }
        turn_timers.pop(room_id, None)
        cd_del = countdown_msgs.pop(room_id, None)
        if cd_del:
            try: await bot.delete_message(cd_del['chat_id'], cd_del['msg_id'])
            except: pass
        await refresh_ui_2p(room_id, bot, msgs)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Timer error 2p: {e}")

# Continue with rest of file...