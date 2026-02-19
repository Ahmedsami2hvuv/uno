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
AUTO_DRAW_DELAY = 5  # Seconds to wait before auto-drawing a card
SKIP_TIMEOUT = 12    # Seconds to wait before auto-passing turn after drawing non-playable card

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
                    # التعديل هنا: نستخدم edit_message_text بدلاً من الحذف والإرسال
                    await bot.edit_message_text(
                        chat_id=cd_info['chat_id'],
                        message_id=cd_info['msg_id'],
                        text=f"⏳ باقي {remaining} ثانية\n{bar}"
                    )
                except Exception as e:
                    # إذا انمسحت الرسالة بالخطأ، نرسل وحدة جديدة ونحدث الـ ID
                    if "message to edit not found" in str(e).lower():
                        try:
                            new_msg = await bot.send_message(
                                cd_info['chat_id'],
                                f"⏳ باقي {remaining} ثانية\n{bar}"
                            )
                            cd_info['msg_id'] = new_msg.message_id
                        except: pass
                    # تجاهل خطأ "لم يتم تعديل الرسالة"
                    elif "message is not modified" in str(e).lower():
                        pass
                    else:
                        print(f"Countdown edit error: {e}")
            
            await asyncio.sleep(2)
            
        # --- بقية المنطق الخاص بسحب الورقة عند انتهاء الوقت يبقى كما هو ---
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
        # عند النهاية فقط نحذف رسالة العداد
        if cd_del:
            try: await bot.delete_message(cd_del['chat_id'], cd_del['msg_id'])
            except: pass
            
        await refresh_ui_2p(room_id, bot, msgs)
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Timer error 2p: {e}")

async def challenge_timeout_2p(room_id, bot, opp_id, chosen_color, challenge_msg_id):
    try:
        cd_info = challenge_countdown_msgs.get(room_id)
        for step in range(9, -1, -1):
            await asyncio.sleep(2)
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
                        f"⏳ باقي {remaining} ثانية للرد\n{bar}"
                    )
                    cd_info['msg_id'] = new_msg.message_id
                except Exception as e:
                    print(f"Challenge countdown send error: {e}")
                    
        ch_cd = challenge_countdown_msgs.pop(room_id, None)
        if ch_cd:
            try: await bot.delete_message(ch_cd['chat_id'], ch_cd['msg_id'])
            except: pass
        challenge_timers.pop(room_id, None)
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        if room['status'] != 'playing': return
        players = get_ordered_players(room_id)
        p_idx = room['turn_index']
        opp_idx = (p_idx + 1) % 2
        deck = safe_load(room['deck'])
        if not deck:
            discard = safe_load(room['discard_pile'])
            if discard:
                deck = discard
                random.shuffle(deck)
                db_query("UPDATE rooms SET discard_pile = '[]' WHERE room_id = %s", (room_id,), commit=True)
            else:
                deck = generate_h2o_deck()
        opp_h = safe_load(players[opp_idx]['hand'])
        for _ in range(4):
            if deck: opp_h.append(deck.pop(0))
        db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(opp_h), players[opp_idx]['user_id']), commit=True)
        db_query("UPDATE rooms SET deck = %s, turn_index = %s, current_color = %s, top_card = %s WHERE room_id = %s", (json.dumps(deck), p_idx, chosen_color, f"🔥 جوكر+4 {chosen_color}", room_id), commit=True)
        try: await bot.delete_message(opp_id, challenge_msg_id)
        except: pass
        alerts = {
            players[p_idx]['user_id']: "⏰ الخصم ما رد بالوقت! قبل السحب تلقائياً والدور رجع لك!",
            players[opp_idx]['user_id']: "⏰ انتهى الوقت! قبلت السحب تلقائياً وسحبت 4 ورقات."
        }
        turn_timers.pop(room_id, None)
        countdown_msgs.pop(room_id, None)
        await refresh_ui_2p(room_id, bot, alerts)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Challenge timer error 2p: {e}")
        

async def color_timeout_2p(room_id, bot, player_id):
    try:
        cd_info = color_countdown_msgs.get(room_id)
        for step in range(9, -1, -1):
            await asyncio.sleep(2)
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
                        f"⏳ باقي {remaining} ثانية لاختيار اللون\n{bar}"
                    )
                    cd_info['msg_id'] = new_msg.message_id
                except Exception as e:
                    print(f"Color countdown send error: {e}")
                    
        cl_cd = color_countdown_msgs.pop(room_id, None)
        if cl_cd:
            try: await bot.delete_message(cl_cd['chat_id'], cl_cd['msg_id'])
            except: pass
        color_timers.pop(room_id, None)
        pdata = pending_color_data.pop(room_id, None)
        if not pdata: return
        color_timed_out.add(room_id)
        card = pdata['card_played']
        p_idx = pdata['p_idx']
        prev_color = pdata['prev_color']
        chosen_color = random.choice(['🔴', '🔵', '🟡', '🟢'])
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        if room['status'] != 'playing': return
        players = get_ordered_players(room_id)
        opp_idx = (p_idx + 1) % 2
        opp_id = players[opp_idx]['user_id']
        p_name = players[p_idx].get('player_name') or "لاعب"
        if "🔥" in card:
            db_query("UPDATE rooms SET top_card = %s, current_color = %s WHERE room_id = %s", (f"{card} {chosen_color}", chosen_color, room_id), commit=True)
            kb = [[InlineKeyboardButton(text="🕵️‍♂️ أتحداك", callback_data=f"rs_y_{room_id}_{prev_color}_{chosen_color}"), InlineKeyboardButton(text="✅ قبول", callback_data=f"rs_n_{room_id}_{chosen_color}")]]
            msg_sent = await bot.send_message(opp_id, f"🚨 {p_name} لعب 🔥 +4 وغير اللون لـ {chosen_color}!", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            cd_msg = await bot.send_message(opp_id, "⏳ باقي 20 ثانية للرد\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
            challenge_countdown_msgs[room_id] = {'bot': bot, 'chat_id': opp_id, 'msg_id': cd_msg.message_id}
            challenge_timers[room_id] = asyncio.create_task(challenge_timeout_2p(room_id, bot, opp_id, chosen_color, msg_sent.message_id))
            await bot.send_message(player_id, f"⏰ انتهى الوقت! تم اختيار اللون {chosen_color} تلقائياً. بانتظار رد الخصم...")
            return
        deck = safe_load(room['deck'])
        alerts = {}
        penalty = 1 if "💧" in card else (2 if "🌊" in card else 0)
        if penalty > 0:
            if not deck:
                discard = safe_load(room['discard_pile'])
                if discard:
                    deck = discard
                    random.shuffle(deck)
                    db_query("UPDATE rooms SET discard_pile = '[]' WHERE room_id = %s", (room_id,), commit=True)
                else:
                    deck = generate_h2o_deck()
            opp_h = safe_load(players[opp_idx]['hand'])
            for _ in range(penalty):
                if deck: opp_h.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(opp_h), opp_id), commit=True)
            next_turn = p_idx
            alerts[opp_id] = f"⏰ {p_name} ما اختار اللون بالوقت! تم اختيار {chosen_color} تلقائياً وسحبك {penalty} ورقة والدور رجع له!"
            alerts[player_id] = f"⏰ انتهى الوقت! تم اختيار اللون {chosen_color} تلقائياً."
        else:
            next_turn = (p_idx + 1) % 2
            alerts[opp_id] = f"⏰ {p_name} ما اختار اللون بالوقت! تم اختيار {chosen_color} تلقائياً والدور صار لك!"
            alerts[player_id] = f"⏰ انتهى الوقت! تم اختيار اللون {chosen_color} تلقائياً."
        db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, deck = %s WHERE room_id = %s", (f"{card} {chosen_color}", chosen_color, next_turn, json.dumps(deck), room_id), commit=True)
        turn_timers.pop(room_id, None)
        countdown_msgs.pop(room_id, None)
        await refresh_ui_2p(room_id, bot, alerts)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Color timer error 2p: {e}")

async def start_new_round(room_id, bot, start_turn_idx=0, alert_msgs=None):
    try:
        room_res = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_res: return
        players = get_ordered_players(room_id)
        deck = generate_h2o_deck()
        
        # توزيع الأوراق على كل اللاعبين
        for p in players:
            hand = [deck.pop(0) for _ in range(7)]
            db_query("UPDATE room_players SET hand = %s, said_uno = FALSE, last_msg_id = NULL, is_ready = FALSE WHERE user_id = %s", (json.dumps(hand), p['user_id']), commit=True)
        
        # اختيار ورقة البداية (ما تكون جوكر)
        while any(x in deck[0] for x in ["🌈", "🔥", "💧", "🌊"]): 
            random.shuffle(deck)
        top_card = deck.pop(0)
        current_color = top_card.split()[0]
        
        # تحديث الغرفة في قاعدة البيانات
        db_query("UPDATE rooms SET deck = %s, top_card = %s, current_color = %s, turn_index = %s, discard_pile = '[]', status = 'playing' WHERE room_id = %s", 
                 (json.dumps(deck), top_card, current_color, start_turn_idx, room_id), commit=True)
        
        # إرسال رسالة بداية اللعبة للاعبين الاثنين
        for p in players:
            try:
                await bot.send_message(p['user_id'], "🎮 بدأت اللعبة! استعد...")
            except:
                pass
        
        # تحديث الواجهة للاعبين الاثنين
        await refresh_ui_2p(room_id, bot, alert_msgs)
        
    except Exception as e: 
        print(f"Error in start_new_round: {e}")

async def refresh_ui_2p(room_id, bot, alert_msg_dict=None):
    try:
        cancel_timer(room_id)
        await asyncio.sleep(0)
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        players = get_ordered_players(room_id)
        score_limit = room.get('score_limit')
        if score_limit is None: score_limit = 500

        for p_idx, p_check in enumerate(players):
            p_hand = safe_load(p_check['hand'])
            if len(p_hand) == 0:
                opp_idx = (p_idx + 1) % 2
                opponent = players[opp_idx]
                opp_hand = safe_load(opponent['hand'])
                round_points = calculate_points(opp_hand)
                opp_name = opponent.get('player_name') or "لاعب"
                breakdown_text = f"📉 {opp_name}: -{round_points} نقطة ({len(opp_hand)} ورقة)"
                current_score = p_check.get('points') or 0
                new_total_score = current_score + round_points
                db_query("UPDATE room_players SET points = %s WHERE room_id = %s AND user_id = %s", (new_total_score, room_id, p_check['user_id']), commit=True)
                p_name = p_check.get('player_name') or "لاعب"

                if score_limit > 0 and new_total_score >= score_limit:
                    winner_name = p_name
                    loser = players[opp_idx]
                    loser_name = loser.get('player_name') or "لاعب"
                    loser_score = loser.get('points') or 0
                    summary = f"🏆 انتهت اللعبة!\n\n"
                    summary += f"🥇 الفائز: {winner_name}\n💰 النقاط: {new_total_score}\n\n"
                    summary += f"🥈 الخاسر: {loser_name}\n💰 النقاط: {loser_score}\n\n"
                    summary += f"📊 نقاط الجولة الأخيرة:\n{breakdown_text}\n\n"
                    summary += f"🎯 سقف اللعب: {score_limit} نقطة"
                    for target_p in players:
                        end_kb = make_end_kb(players, room, '2p', for_user_id=target_p['user_id'])
                        try:
                            await bot.send_message(target_p['user_id'], summary, reply_markup=end_kb)
                        except Exception as send_err:
                            print(f"❌ ما قدرت أرسل رسالة نهاية اللعبة لـ {target_p['user_id']}: {send_err}")
                    db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
                    return
                elif score_limit == 0:
                    summary = f"🏆 {p_name} فاز بالجولة! (+{round_points} نقطة)\n\n📊 النقاط المأخوذة:\n{breakdown_text}\n\n🎯 الوضع: جولة واحدة"
                    for target_p in players:
                        end_kb = make_end_kb(players, room, '2p', for_user_id=target_p['user_id'])
                        try:
                            await bot.send_message(target_p['user_id'], summary, reply_markup=end_kb)
                        except Exception as send_err:
                            print(f"❌ ما قدرت أرسل رسالة نهاية الجولة لـ {target_p['user_id']}: {send_err}")
                    db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
                    return
                else:
                    from handlers.common import pending_next_round, _next_round_timeout
                    pending_next_round[room_id] = {'mode': '2p', 'start_turn': opp_idx}
                    round_text = f"🎉 {p_name} فاز بالجولة (+{round_points} نقطة)!\n💰 مجموعه: {new_total_score}/{score_limit}\n\n📊 النقاط المأخوذة:\n{breakdown_text}\n\n⏳ اضغط كمل خلال 20 ثانية"
                    next_kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 كمل جولة جديدة", callback_data=f"nextround_{room_id}")]
                    ])
                    for tp in players:
                        try:
                            await bot.send_message(tp['user_id'], round_text, reply_markup=next_kb)
                        except Exception as send_err:
                            print(f"❌ ما قدرت أرسل رسالة جولة جديدة لـ {tp['user_id']}: {send_err}")
                    asyncio.create_task(_next_round_timeout(room_id, bot))
                    return

        curr_idx = room['turn_index']
        curr_p = players[curr_idx]
        curr_hand = safe_load(curr_p['hand'])

        if not any(check_validity(c, room['top_card'], room['current_color']) for c in curr_hand):
            # Step 1: Notify player - no suitable card, will draw in 5 seconds
            p_name = curr_p.get('player_name') or "لاعب"
            opp_id = players[(curr_idx+1)%2]['user_id']
            
            try:
                await bot.send_message(curr_p['user_id'], "❌ ماعندك ورقة مناسبة! راح اسحبلك ورقة خلال 5 ثواني...")
                await bot.send_message(opp_id, f"⏳ {p_name} ماعنده ورقة مناسبة، البوت راح يسحبله ورقة...")
            except:
                pass
            
            # Step 2: Wait 5 seconds
            await asyncio.sleep(AUTO_DRAW_DELAY)
            
            # Step 3: Draw card
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
            is_playable = check_validity(new_card, room['top_card'], room['current_color'])
            
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(curr_hand), curr_p['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            
            msgs = {}
            if is_playable:
                # Card is playable - keep turn with player
                msgs[curr_p['user_id']] = f"✅ سحبتلك ({new_card}) ومناسبة للعب! العبها 👍"
                msgs[opp_id] = f"📥 {p_name} سحب ورقة ({new_card}) والورقة مناسبة وسيلعبها 🔄"
                return await refresh_ui_2p(room_id, bot, msgs)
            else:
                # Card is NOT playable - need to show skip button
                # Mark this state in the database so we know skip is available
                db_query("UPDATE room_players SET can_skip = 1 WHERE user_id = %s", (curr_p['user_id'],), commit=True)
                msgs[curr_p['user_id']] = f"❌ الورقة الي سحبتها ({new_card}) غير مناسبة للعب. راح يعبر دورك خلال 12 ثانية او دوس على زر مرر ⏭"
                msgs[opp_id] = f"📥 {p_name} سحب ورقة ({new_card}) وماهي مناسبة، راح يعبر دوره قريب..."
                
                # Refresh UI with skip button
                await refresh_ui_2p(room_id, bot, msgs)
                
                # Step 4: Wait 12 seconds for skip or auto-pass
                await asyncio.sleep(SKIP_TIMEOUT)
                
                # Check if player already skipped manually (can_skip would be 0 if they did)
                # If can_skip is still 1, player did NOT skip manually, so auto-pass their turn
                check_skip = db_query("SELECT can_skip FROM room_players WHERE user_id = %s", (curr_p['user_id'],))
                if check_skip and check_skip[0].get('can_skip') == 1:
                    # Auto-pass turn
                    next_turn = (curr_idx + 1) % 2
                    db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_turn, room_id), commit=True)
                    db_query("UPDATE room_players SET can_skip = 0 WHERE user_id = %s", (curr_p['user_id'],), commit=True)
                    
                    auto_msgs = {}
                    auto_msgs[curr_p['user_id']] = "⏭ تم تمرير دورك تلقائياً"
                    auto_msgs[opp_id] = f"✅ {p_name} عبر دوره، الدور الحين لك!"
                    return await refresh_ui_2p(room_id, bot, auto_msgs)
                
                return

        # 🔥 هنا التعديل الرئيسي: نرسل الواجهة للاعبين الاثنين
        for i, p in enumerate(players):
            hand = sort_hand(safe_load(p['hand']))

            turn_status = "✅ دورك 👍🏻" if room['turn_index'] == i else "مو دورك ❌"
            num_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
            players_info = []
            for pl_idx, pl in enumerate(players):
                pl_name = pl.get('player_name') or 'لاعب'
                pl_cards = len(safe_load(pl['hand']))
                pl_score = pl.get('points') or 0
                num_marker = num_emojis[pl_idx] if pl_idx < len(num_emojis) else '👤'
                star = "✅" if pl_idx == room['turn_index'] else ""
                players_info.append(f"{star}{num_marker} {pl_name}: {pl_cards} ورقة | 💰 {pl_score} نقطة")

            status_text = f"📦 السحب: {len(safe_load(room['deck']))} | 🗑 الملعوب: {len(safe_load(room.get('discard_pile', '[]')))+1}\n"
            status_text += "\n".join(players_info)
            if alert_msg_dict and p['user_id'] in alert_msg_dict:
                status_text += f"\n──────────────\n📢 {alert_msg_dict[p['user_id']]}"
            if room['turn_index'] == i:
                status_text += f"\n──────────────\n⏱ لك وقت 20 ثانية"
            status_text += f"\n──────────────\n🃏 الورقة النازلة: [ {room['top_card']} ]           {turn_status}"

            kb = []
            row = []
            card_in_row = 0
            prev_group = None
            for card_idx, card in enumerate(hand):
                c_parts = card.split()
                c_group = "wild" if any(x in card for x in ["🌈", "🔥", "💧", "🌊"]) else c_parts[0]
                if prev_group is not None and c_group != prev_group and card_in_row > 0:
                    while card_in_row < 3:
                        row.append(InlineKeyboardButton(text="⬜", callback_data="ignore"))
                        card_in_row += 1
                    kb.append(row); row = []; card_in_row = 0
                row.append(InlineKeyboardButton(text=card, callback_data=f"pl_{room_id}_{card_idx}"))
                card_in_row += 1
                prev_group = c_group
                if card_in_row == 3: kb.append(row); row = []; card_in_row = 0
            if row: kb.append(row)

            controls = []
            if i == room['turn_index'] and len(hand) == 2:
                controls.append(InlineKeyboardButton(text="🚨 اونو!", callback_data=f"un_{room_id}"))
            opp = players[(i+1)%2]
            if len(safe_load(opp['hand'])) == 1 and not str(opp.get('said_uno', 'false')).lower() in ['true', '1']:
                controls.append(InlineKeyboardButton(text="🪤 صيدة!", callback_data=f"ct_{room_id}"))
            if controls: kb.append(controls)
            
            exit_row = [InlineKeyboardButton(text="🚪 انسحاب", callback_data=f"ex_{room_id}")]
            # Add skip button if player can skip (when they drew a non-playable card)
            if p.get('can_skip') == 1 and i == room['turn_index']:
                exit_row.insert(0, InlineKeyboardButton(text="⏭ مرر", callback_data=f"sk_{room_id}"))
            if p['user_id'] == room.get('creator_id'):
                exit_row.append(InlineKeyboardButton(text="⚙️", callback_data=f"rsettings_{room_id}"))
            kb.append(exit_row)

            # 🔥 هنا نتأكد إننا نرسل للجميع (حتى لو مو دوره)
            try:
                if p.get('last_msg_id'):
                    try:
                        msg = await bot.edit_message_text(
                            text=status_text,
                            chat_id=p['user_id'],
                            message_id=p['last_msg_id'],
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
                        )
                    except:
                        try: 
                            await bot.delete_message(p['user_id'], p['last_msg_id'])
                        except: 
                            pass
                        msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                else:
                    msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                
                db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", (msg.message_id, room_id, p['user_id']), commit=True)
                
                # العداد بس للاعب اللي دوره
                if i == room['turn_index']:
                    cd_msg = await bot.send_message(p['user_id'], "⏳ باقي 20 ثانية\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
                    countdown_msgs[room_id] = {'bot': bot, 'chat_id': p['user_id'], 'msg_id': cd_msg.message_id}
                    
            except Exception as ui_err:
                print(f"❌ ما قدرت أرسل الواجهة لـ {p['user_id']}: {ui_err}")
                # لو اللاعب بوت، نتجاهله ونكمل
                continue

        # نبدأ العداد التلقائي
        turn_timers[room_id] = asyncio.create_task(turn_timeout_2p(room_id, bot, room['turn_index']))
        
    except Exception as e: 
        print(f"UI Error: {e}")

@router.callback_query(F.data.startswith("pl_"))
async def handle_play(c: types.CallbackQuery, state: FSMContext):
    try:
        parts = c.data.split("_")
        idx, room_id = int(parts[-1]), "_".join(parts[1:-1])
        cancel_timer(room_id)
        await asyncio.sleep(0)
        room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
        players = get_ordered_players(room_id)
        p_idx = room['turn_index']
        if players[p_idx]['user_id'] != c.from_user.id: return await c.answer("مو دورك! ❌", show_alert=True)
        hand = sort_hand(safe_load(players[p_idx]['hand']))
        if idx >= len(hand): return await c.answer("حدث القائمة...", show_alert=True)
        card = hand[idx]
        p_name = players[p_idx].get('player_name') or "لاعب"
        opp_id = players[(p_idx+1)%2]['user_id']

        if not check_validity(card, room['top_card'], room['current_color']):
            deck = safe_load(room['deck'])
            penalty = [deck.pop(0) for _ in range(2) if deck]
            hand.extend(penalty)
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(hand), c.from_user.id), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            print(f"DEBUG: {p_name} tried {card} on {room['top_card']} (Color: {room['current_color']}) -> REJECTED")
            alerts = {
                c.from_user.id: f"⛔ لعبت ورقة خطأ ({card}) وتعاقبت بسحب ورقتين!",
                opp_id: f"⚠️ {p_name} لعب ورقة خطأ وتعاقب بسحب ورقتين!"
            }
            return await refresh_ui_2p(room_id, c.bot, alerts)

        hand.pop(idx)
        was_uno_said = str(players[p_idx]['said_uno']).lower() in ['true', '1']
        updated_said_uno = was_uno_said if len(hand) == 1 else False
        db_query("UPDATE room_players SET hand = %s, said_uno = %s WHERE user_id = %s", (json.dumps(hand), updated_said_uno, c.from_user.id), commit=True)

        discard_pile = safe_load(room['discard_pile'])
        discard_pile.append(room['top_card'])

        alerts = {}

        if len(hand) == 1:
            if was_uno_said:
                alerts[opp_id] = f"✅ {p_name} صاح اونو وبقتله ورقة وحدة (في أمان)."
            else:
                alerts[opp_id] = f"⚠️ {p_name} بقتله ورقة وحدة ونسي يصيح اونو! صيده بسرعة! 🪤"

        if len(hand) == 0:
            db_query("UPDATE rooms SET discard_pile = %s, top_card = %s, current_color = %s WHERE room_id = %s", (json.dumps(discard_pile), card, card.split()[0], room_id), commit=True)
            return await refresh_ui_2p(room_id, c.bot)

        if any(x in card for x in ["🌈", "🔥", "💧", "🌊"]):
            await state.update_data(room_id=room_id, card_played=card, p_idx=p_idx, prev_color=room['current_color'])
            kb_list = [[InlineKeyboardButton(text="🔴", callback_data="cl_🔴"), InlineKeyboardButton(text="🔵", callback_data="cl_🔵")], [InlineKeyboardButton(text="🟡", callback_data="cl_🟡"), InlineKeyboardButton(text="🟢", callback_data="cl_🟢")]]
            hand_row = []
            h_count = 0
            h_prev_group = None
            for h_card in hand:
                h_parts = h_card.split()
                h_group = "wild" if any(x in h_card for x in ["🌈", "🔥", "💧", "🌊"]) else h_parts[0]
                if h_prev_group is not None and h_group != h_prev_group and h_count > 0:
                    while h_count < 3:
                        hand_row.append(InlineKeyboardButton(text="⬜", callback_data="ignore"))
                        h_count += 1
                    kb_list.append(hand_row); hand_row = []; h_count = 0
                hand_row.append(InlineKeyboardButton(text=h_card, callback_data="ignore"))
                h_count += 1
                h_prev_group = h_group
                if h_count == 3: kb_list.append(hand_row); hand_row = []; h_count = 0
            if hand_row: kb_list.append(hand_row)
            await c.message.edit_text("🎨 اختر اللون الجديد:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
            await state.set_state(GameStates.choosing_color)
            db_query("UPDATE rooms SET discard_pile = %s WHERE room_id = %s", (json.dumps(discard_pile), room_id), commit=True)
            pending_color_data[room_id] = {'card_played': card, 'p_idx': p_idx, 'prev_color': room['current_color']}
            cd_msg = await c.bot.send_message(c.from_user.id, "⏳ باقي 20 ثانية لاختيار اللون\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
            color_countdown_msgs[room_id] = {'bot': c.bot, 'chat_id': c.from_user.id, 'msg_id': cd_msg.message_id}
            color_timers[room_id] = asyncio.create_task(color_timeout_2p(room_id, c.bot, c.from_user.id))
            return

        next_turn = (p_idx + 1) % 2
        if "🚫" in card:
            next_turn = p_idx
            alerts[opp_id] = f"🚫 {p_name} لعب منع والدور رجع اله!"
            alerts[c.from_user.id] = f"🚫 لعبت منع والدور رجع الك!"
        elif "🔄" in card:
            next_turn = p_idx
            alerts[opp_id] = f"🔄 {p_name} لعب تحويل والدور رجع اله!"
            alerts[c.from_user.id] = f"🔄 لعبت تحويل والدور رجع الك!"
        elif "⬆️2" in card:
            next_turn = p_idx
            deck = safe_load(room['deck'])
            opp_h = safe_load(players[(p_idx+1)%2]['hand'])
            for _ in range(2):
                if deck: opp_h.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(opp_h), players[(p_idx+1)%2]['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            alerts[opp_id] = f"⬆️2 {p_name} لعب سحب 2 وسحبك ورقتين والدور رجع اله!"
            alerts[c.from_user.id] = f"⬆️2 لعبت سحب 2 وسحبت الخصم ورقتين والدور رجع الك!"

        db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, discard_pile = %s WHERE room_id = %s", (card, card.split()[0], next_turn, json.dumps(discard_pile), room_id), commit=True)
        await refresh_ui_2p(room_id, c.bot, alerts)
    except Exception as e: print(f"Play Error: {e}")

@router.callback_query(GameStates.choosing_color, F.data.startswith("cl_"))
async def handle_color(c: types.CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        room_id, card, p_idx = data.get('room_id'), data.get('card_played'), data.get('p_idx')
        chosen_color = c.data.split("_")[1]
        task = color_timers.pop(room_id, None)
        if task and not task.done(): task.cancel()
        cd = color_countdown_msgs.pop(room_id, None)
        if cd:
            try: await cd['bot'].delete_message(cd['chat_id'], cd['msg_id'])
            except: pass
        pending_color_data.pop(room_id, None)
        if room_id in color_timed_out:
            color_timed_out.discard(room_id)
            await state.clear()
            return
        players = get_ordered_players(room_id)
        opp_id = players[(p_idx + 1) % 2]['user_id']
        p_name = players[p_idx].get('player_name') or "لاعب"
        if "🔥" in card:
            kb = [[InlineKeyboardButton(text="🕵️‍♂️ أتحداك", callback_data=f"rs_y_{room_id}_{data.get('prev_color')}_{chosen_color}"), InlineKeyboardButton(text="✅ قبول", callback_data=f"rs_n_{room_id}_{chosen_color}")]]
            msg_sent = await c.bot.send_message(opp_id, f"🚨 {p_name} لعب 🔥 +4 وغير اللون لـ {chosen_color}!", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            cd_msg = await c.bot.send_message(opp_id, "⏳ باقي 20 ثانية للرد\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
            challenge_countdown_msgs[room_id] = {'bot': c.bot, 'chat_id': opp_id, 'msg_id': cd_msg.message_id}
            challenge_timers[room_id] = asyncio.create_task(challenge_timeout_2p(room_id, c.bot, opp_id, chosen_color, msg_sent.message_id))
            await c.message.edit_text("⏳ بانتظار الخصم...")
            await state.clear()
            return
        penalty = 1 if "💧" in card else (2 if "🌊" in card else 0)
        room_res = db_query("SELECT deck FROM rooms WHERE room_id = %s", (room_id,))[0]
        deck = safe_load(room_res['deck'])
        alerts = {}
        if penalty > 0:
            opp_h = safe_load(players[(p_idx + 1) % 2]['hand'])
            for _ in range(penalty):
                if deck: opp_h.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(opp_h), opp_id), commit=True)
            next_turn = p_idx
            alerts[opp_id] = f"🎨 {p_name} اختار اللون {chosen_color} وسحبك {penalty} ورقة والدور رجع اله!"
        else:
            next_turn = (p_idx + 1) % 2
            alerts[opp_id] = f"🎨 {p_name} اختار اللون {chosen_color} والدور صار الك!"
        db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, deck = %s WHERE room_id = %s", (f"{card} {chosen_color}", chosen_color, next_turn, json.dumps(deck), room_id), commit=True)
        await state.clear()
        await refresh_ui_2p(room_id, c.bot, alerts)
    except Exception as e: print(f"Color Error: {e}")

@router.callback_query(F.data.startswith("rs_"))
async def handle_challenge(c: types.CallbackQuery):
    try:
        parts = c.data.split("_")
        cancel_challenge_timer(parts[2])
        decision, room_id = parts[1], parts[2]
        room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
        players = get_ordered_players(room_id)
        p_idx, opp_idx = room['turn_index'], (room['turn_index'] + 1) % 2
        deck = safe_load(room['deck'])
        alerts = {}
        if decision == "n":
            opp_h = safe_load(players[opp_idx]['hand'])
            for _ in range(4):
                if deck: opp_h.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(opp_h), players[opp_idx]['user_id']), commit=True)
            next_turn, final_col = p_idx, parts[3]
            alerts[players[p_idx]['user_id']] = "✅ الخصم قبل السحب والدور رجع الك!"
            alerts[players[opp_idx]['user_id']] = "📥 قبلت السحب وسحبت 4 ورقات وعبر دورك."
        else:
            prev_col, chosen_col = parts[3], parts[4]
            p_hand = safe_load(players[p_idx]['hand'])
            cheated = any(card.split()[0] == prev_col for card in p_hand if card.split()[0] in ['🔴', '🔵', '🟡', '🟢'])
            if cheated:
                for _ in range(6):
                    if deck: p_hand.append(deck.pop(0))
                db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(p_hand), players[p_idx]['user_id']), commit=True)
                next_turn = opp_idx
                alerts[players[p_idx]['user_id']] = "🕵️‍♂️ كشفك الخصم! سحبت 6 ورقات عقوبة."
                alerts[players[opp_idx]['user_id']] = "✅ نجح التحدي! الخصم كان يغش وسحب 6 ورقات."
            else:
                opp_h = safe_load(players[opp_idx]['hand'])
                for _ in range(6):
                    if deck: opp_h.append(deck.pop(0))
                db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(opp_h), players[opp_idx]['user_id']), commit=True)
                next_turn = p_idx
                alerts[players[p_idx]['user_id']] = "❌ فشل تحدي الخصم وسحب 6 ورقات! الدور الك."
                alerts[players[opp_idx]['user_id']] = "❌ فشل التحدي! سحبت 6 ورقات."
            final_col = chosen_col
        db_query("UPDATE rooms SET deck = %s, turn_index = %s, current_color = %s, top_card = %s WHERE room_id = %s", (json.dumps(deck), next_turn, final_col, f"🔥 جوكر+4 {final_col}", room_id), commit=True)
        try: await c.message.delete()
        except: pass
        await refresh_ui_2p(room_id, c.bot, alerts)
    except Exception as e: print(f"Challenge Error: {e}")

@router.callback_query(F.data.startswith("un_"))
async def handle_uno(c: types.CallbackQuery):
    try:
        room_id = c.data.split("_")[1]
        db_query("UPDATE room_players SET said_uno = TRUE WHERE room_id = %s AND user_id = %s", (room_id, c.from_user.id), commit=True)
        players = get_ordered_players(room_id)
        opp = next((p for p in players if p['user_id'] != c.from_user.id), None)
        me = next((p for p in players if p['user_id'] == c.from_user.id), None)
        p_name = me.get('player_name') if me else "لاعب"
        await c.answer()
        alerts = {c.from_user.id: "✅ صحت اونو بنجاح وأنت في أمان."}
        if opp:
            alerts[opp['user_id']] = f"🚨 {p_name} صاح اونو! بقتله ورقة وحدة وهو في أمان."
        try:
            if IMG_UNO_SAFE_ME and IMG_UNO_SAFE_ME != "123":
                await _send_photo_then_schedule_delete(c.bot, c.from_user.id, IMG_UNO_SAFE_ME)
            if opp and IMG_UNO_SAFE_OPP and IMG_UNO_SAFE_OPP != "123":
                await _send_photo_then_schedule_delete(c.bot, opp['user_id'], IMG_UNO_SAFE_OPP)
        except: pass
        await refresh_ui_2p(room_id, c.bot, alerts)
    except Exception as e: print(f"Uno Error: {e}")

@router.callback_query(F.data.startswith("ct_"))
async def handle_catch(c: types.CallbackQuery):
    try:
        room_id = c.data.split("_")[1]
        players = get_ordered_players(room_id)
        opp = next(p for p in players if p['user_id'] != c.from_user.id)
        opp_h = safe_load(opp['hand'])
        me = next((p for p in players if p['user_id'] == c.from_user.id), None)
        p_name = me.get('player_name') if me else "لاعب"
        opp_name = opp.get('player_name') or "لاعب"
        if len(opp_h) == 1 and not str(opp.get('said_uno')).lower() in ['true', '1']:
            room_data = db_query("SELECT deck FROM rooms WHERE room_id = %s", (room_id,))[0]
            deck = safe_load(room_data['deck'])
            for _ in range(2):
                if deck: opp_h.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(opp_h), opp['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            await c.answer()
            try:
                if IMG_CATCH_SUCCESS and IMG_CATCH_SUCCESS != "123":
                    await _send_photo_then_schedule_delete(c.bot, c.from_user.id, IMG_CATCH_SUCCESS)
                if IMG_CATCH_PENALTY and IMG_CATCH_PENALTY != "123":
                    await _send_photo_then_schedule_delete(c.bot, opp['user_id'], IMG_CATCH_PENALTY)
            except: pass
            alerts = {
                c.from_user.id: f"🪤 صدت {opp_name}! سحب ورقتين لأنه نسي الاونو.",
                opp['user_id']: f"⚠️ {p_name} صادك! سحبت ورقتين لأنك نسيت تصيح اونو!"
            }
            await refresh_ui_2p(room_id, c.bot, alerts)
        else:
            await c.answer("❌ ما تگدر تصيده حالياً!")
    except Exception as e: print(f"Catch Error: {e}")

@router.callback_query(F.data.startswith("sk_"))
async def skip_turn(c: types.CallbackQuery):
    """Handler for skip button - immediately pass turn when player has non-playable drawn card"""
    try:
        room_id = c.data.split("_")[1]
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data:
            return await c.answer("❌ الغرفة غير موجودة!", show_alert=True)
        
        room = room_data[0]
        players = get_ordered_players(room_id)
        
        # Verify it's the player's turn
        curr_idx = room['turn_index']
        curr_p = players[curr_idx]
        
        if curr_p['user_id'] != c.from_user.id:
            return await c.answer("❌ مو دورك!", show_alert=True)
        
        # Check if player can skip
        if curr_p.get('can_skip') != 1:
            return await c.answer("❌ ما تقدر تمرر الحين!", show_alert=True)
        
        # Pass turn to next player
        next_turn = (curr_idx + 1) % 2
        db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_turn, room_id), commit=True)
        db_query("UPDATE room_players SET can_skip = 0 WHERE user_id = %s", (curr_p['user_id'],), commit=True)
        
        p_name = curr_p.get('player_name') or "لاعب"
        opp_id = players[next_turn]['user_id']
        
        msgs = {}
        msgs[curr_p['user_id']] = "⏭ تم تمرير دورك"
        msgs[opp_id] = f"✅ {p_name} مرر دوره، الدور الحين لك!"
        
        await refresh_ui_2p(room_id, c.bot, msgs)
        await c.answer("✅ تم تمرير الدور")
        
    except Exception as e:
        print(f"Skip Error: {e}")
        await c.answer("❌ حدث خطأ", show_alert=True)

@router.callback_query(F.data.startswith("ex_"))
async def ask_exit(c: types.CallbackQuery):
    rid = c.data.split("_")[1]
    kb = [[InlineKeyboardButton(text="✅ نعم", callback_data=f"cf_ex_{rid}"), InlineKeyboardButton(text="❌ لا", callback_data=f"cn_ex_{rid}")]]
    await c.message.edit_text("🚪 هل أنت متأكد من الانسحاب؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("cf_ex_"))
async def confirm_exit(c: types.CallbackQuery):
    rid = c.data.split("_")[2]
    cancel_timer(rid)
    players = get_ordered_players(rid)
    room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (rid,))
    room = room_data[0] if room_data else {'max_players': 2, 'score_limit': 0}
    me = next((x for x in players if x['user_id'] == c.from_user.id), None)
    leave_name = me.get('player_name') if me else "لاعب"
    for p in players:
        end_kb = make_end_kb(players, room, '2p', for_user_id=p['user_id'])
        await c.bot.send_message(p['user_id'], f"🚪 {leave_name} انسحب، تم إلغاء اللعبة.", reply_markup=end_kb)
    db_query("DELETE FROM rooms WHERE room_id = %s", (rid,), commit=True)

@router.callback_query(F.data.startswith("cn_ex_"))
async def cancel_exit(c: types.CallbackQuery):
    rid = c.data.split("_")[2]
    await refresh_ui_2p(rid, c.bot)
