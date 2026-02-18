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

class MultiGameStates(StatesGroup):
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

def make_end_kb(players, room, mode='multi', for_user_id=None):
    from handlers.common import replay_data
    replay_id = str(uuid.uuid4())[:8]
    replay_data[replay_id] = {
        'players': [(p['user_id'], p.get('player_name') or 'لاعب') for p in players],
        'max_players': room.get('max_players', 10),
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

def generate_deck():
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

async def turn_timeout_multi(room_id, bot, expected_turn):
    try:
        cd_info = countdown_msgs.get(room_id)
        for step in range(10, 0, -1):
            if cd_info:
                try:
                    remaining = step * 2
                    bar = "🟢" * step + "⚫" * (10 - step)
                    await bot.edit_message_text(text=f"⏳ باقي {remaining} ثانية\n{bar}", chat_id=cd_info['chat_id'], message_id=cd_info['msg_id'])
                except Exception as e:
                    print(f"Countdown edit error: {e}")
            await asyncio.sleep(2)
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        if room['status'] != 'playing': return
        players = get_ordered_players(room_id)
        num_players = len(players)
        direction = room.get('direction') or 1
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
                deck = generate_deck()
        new_card = deck.pop(0)
        curr_hand.append(new_card)
        next_turn = (curr_idx + direction) % num_players
        db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(curr_hand), curr_p['user_id']), commit=True)
        db_query("UPDATE rooms SET deck = %s, turn_index = %s WHERE room_id = %s", (json.dumps(deck), next_turn, room_id), commit=True)
        next_name = players[next_turn].get('player_name') or "لاعب"
        msgs = {curr_p['user_id']: f"⏰ انتهى وقتك! سحبت ورقة ({new_card}) وعبر الدور"}
        for op in players:
            if op['user_id'] != curr_p['user_id']:
                msgs[op['user_id']] = f"⏰ {p_name} ما لعب بالوقت! سحب ورقة والدور لـ {next_name} ✅"
        turn_timers.pop(room_id, None)
        cd_del = countdown_msgs.pop(room_id, None)
        if cd_del:
            try: await bot.delete_message(cd_del['chat_id'], cd_del['msg_id'])
            except: pass
        await refresh_ui_multi(room_id, bot, msgs)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Timer error multi: {e}")

async def challenge_timeout_multi(room_id, bot, victim_user_id, chosen_color, challenge_msg_id):
    try:
        cd_info = challenge_countdown_msgs.get(room_id)
        for step in range(9, -1, -1):
            await asyncio.sleep(2)
            remaining = step * 2
            if cd_info:
                try:
                    bar = "🟢" * step + "⚫" * (10 - step)
                    await bot.edit_message_text(text=f"⏳ باقي {remaining} ثانية للرد\n{bar}", chat_id=cd_info['chat_id'], message_id=cd_info['msg_id'])
                except Exception as e:
                    print(f"Challenge countdown edit error: {e}")
        ch_cd = challenge_countdown_msgs.pop(room_id, None)
        if ch_cd:
            try: await bot.delete_message(ch_cd['chat_id'], ch_cd['msg_id'])
            except: pass
        try: await bot.delete_message(victim_user_id, challenge_msg_id)
        except: pass
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        if room['status'] != 'playing': return
        players = get_ordered_players(room_id)
        num_players = len(players)
        direction = room.get('direction') or 1
        p_idx = room['turn_index']
        victim_idx = (p_idx + direction) % num_players
        deck = safe_load(room['deck'])
        if not deck:
            discard = safe_load(room['discard_pile'])
            if discard:
                deck = discard
                random.shuffle(deck)
                db_query("UPDATE rooms SET discard_pile = '[]' WHERE room_id = %s", (room_id,), commit=True)
            else:
                deck = generate_deck()
        v_hand = safe_load(players[victim_idx]['hand'])
        for _ in range(4):
            if deck: v_hand.append(deck.pop(0))
        db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(v_hand), players[victim_idx]['user_id']), commit=True)
        next_turn = (p_idx + direction * 2) % num_players
        db_query("UPDATE rooms SET deck = %s, turn_index = %s, current_color = %s, top_card = %s WHERE room_id = %s", (json.dumps(deck), next_turn, chosen_color, f"🔥 جوكر+4 {chosen_color}", room_id), commit=True)
        alerts = {}
        alerts[players[p_idx]['user_id']] = "⏰ الخصم ما رد بالوقت! قبل السحب تلقائياً!"
        alerts[players[victim_idx]['user_id']] = "⏰ انتهى الوقت! قبلت السحب تلقائياً وسحبت 4 ورقات."
        turn_timers.pop(room_id, None)
        countdown_msgs.pop(room_id, None)
        await refresh_ui_multi(room_id, bot, alerts)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Challenge timer error multi: {e}")

async def color_timeout_multi(room_id, bot, user_id):
    try:
        cd_info = color_countdown_msgs.get(room_id)
        for step in range(9, -1, -1):
            await asyncio.sleep(2)
            remaining = step * 2
            if cd_info:
                try:
                    bar = "🟢" * step + "⚫" * (10 - step)
                    await bot.edit_message_text(text=f"⏳ باقي {remaining} ثانية لاختيار اللون\n{bar}", chat_id=cd_info['chat_id'], message_id=cd_info['msg_id'])
                except Exception as e:
                    print(f"Color countdown edit error: {e}")
        cl_cd = color_countdown_msgs.pop(room_id, None)
        if cl_cd:
            try: await bot.delete_message(cl_cd['chat_id'], cl_cd['msg_id'])
            except: pass
        color_timers.pop(room_id, None)
        color_timed_out.add(room_id)
        pdata = pending_color_data.pop(room_id, None)
        if not pdata: return
        card = pdata['card_played']
        p_idx = pdata['p_idx']
        prev_color = pdata['prev_color']
        chosen_color = random.choice(['🔴', '🔵', '🟡', '🟢'])
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        if room['status'] != 'playing': return
        players = get_ordered_players(room_id)
        num_players = len(players)
        direction = room.get('direction') or 1
        p_name = players[p_idx].get('player_name') or "لاعب"
        alerts = {}
        deck = safe_load(room['deck'])

        if "🔥" in card:
            victim_idx = (p_idx + direction) % num_players
            victim = players[victim_idx]
            v_name = victim.get('player_name') or "لاعب"
            kb = [[InlineKeyboardButton(text="🕵️‍♂️ أتحداك", callback_data=f"rsmul_y_{room_id}_{prev_color}_{chosen_color}"), InlineKeyboardButton(text="✅ قبول", callback_data=f"rsmul_n_{room_id}_{chosen_color}")]]
            msg_sent = await bot.send_message(victim['user_id'], f"🚨 {p_name} لعب 🔥 +4 وغير اللون لـ {chosen_color}!", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            cd_msg = await bot.send_message(victim['user_id'], "⏳ باقي 20 ثانية للرد\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
            challenge_countdown_msgs[room_id] = {'bot': bot, 'chat_id': victim['user_id'], 'msg_id': cd_msg.message_id}
            challenge_timers[room_id] = asyncio.create_task(challenge_timeout_multi(room_id, bot, victim['user_id'], chosen_color, msg_sent.message_id))
            db_query("UPDATE rooms SET top_card = %s, current_color = %s, deck = %s WHERE room_id = %s", (f"{card} {chosen_color}", chosen_color, json.dumps(deck), room_id), commit=True)
            try: await bot.send_message(user_id, f"⏰ انتهى الوقت! تم اختيار اللون {chosen_color} تلقائياً.")
            except: pass
            return

        if not deck:
            discard = safe_load(room['discard_pile'])
            if discard:
                deck = discard
                random.shuffle(deck)
                db_query("UPDATE rooms SET discard_pile = '[]' WHERE room_id = %s", (room_id,), commit=True)
            else:
                deck = generate_deck()

        penalty = 1 if "💧" in card else (2 if "🌊" in card else 0)
        if penalty > 0:
            victim_idx = (p_idx + direction) % num_players
            victim = players[victim_idx]
            v_name = victim.get('player_name') or "لاعب"
            v_hand = safe_load(victim['hand'])
            for _ in range(penalty):
                if deck: v_hand.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(v_hand), victim['user_id']), commit=True)
            next_turn = (p_idx + direction * 2) % num_players
            alerts[victim['user_id']] = f"🎨 تم اختيار اللون {chosen_color} تلقائياً وسحبت {penalty} ورقة!"
            alerts[user_id] = f"⏰ انتهى الوقت! تم اختيار اللون {chosen_color} تلقائياً وسحبت {v_name} {penalty} ورقة!"
        else:
            next_turn = (p_idx + direction) % num_players
            alerts[user_id] = f"⏰ انتهى الوقت! تم اختيار اللون {chosen_color} تلقائياً!"
            for op in players:
                if op['user_id'] != user_id:
                    alerts[op['user_id']] = f"🎨 {p_name} تم اختيار اللون {chosen_color} تلقائياً!"

        db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, deck = %s WHERE room_id = %s", (f"{card} {chosen_color}", chosen_color, next_turn, json.dumps(deck), room_id), commit=True)
        turn_timers.pop(room_id, None)
        countdown_msgs.pop(room_id, None)
        await refresh_ui_multi(room_id, bot, alerts)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Color timer error multi: {e}")

async def start_game_multi(room_id, bot, start_turn_idx=0, alert_msgs=None):
    try:
        room_res = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_res: return
        players = get_ordered_players(room_id)
        deck = generate_deck()
        for p in players:
            hand = [deck.pop(0) for _ in range(7)]
            db_query("UPDATE room_players SET hand = %s, said_uno = FALSE, last_msg_id = NULL, is_ready = FALSE WHERE user_id = %s", (json.dumps(hand), p['user_id']), commit=True)
        while any(x in deck[0] for x in ["🌈", "🔥", "💧", "🌊"]): random.shuffle(deck)
        top_card = deck.pop(0)
        current_color = top_card.split()[0]
        db_query("UPDATE rooms SET deck = %s, top_card = %s, current_color = %s, turn_index = %s, discard_pile = '[]', direction = 1, status = 'playing' WHERE room_id = %s", (json.dumps(deck), top_card, current_color, start_turn_idx, room_id), commit=True)
        await refresh_ui_multi(room_id, bot)
    except Exception as e: print(f"Error in start_game_multi: {e}")

async def refresh_ui_multi(room_id, bot, alert_msg_dict=None):
    try:
        cancel_timer(room_id)
        await asyncio.sleep(0)
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        players = get_ordered_players(room_id)
        num_players = len(players)
        direction = room.get('direction') or 1
        score_limit = room.get('score_limit')
        if score_limit is None: score_limit = 500

        for p_idx, p_check in enumerate(players):
            p_hand = safe_load(p_check['hand'])
            if len(p_hand) == 0:
                round_points = 0
                losers_breakdown = []
                for other in players:
                    if other['user_id'] != p_check['user_id']:
                        other_hand = safe_load(other['hand'])
                        other_pts = calculate_points(other_hand)
                        round_points += other_pts
                        o_name = other.get('player_name') or "لاعب"
                        losers_breakdown.append(f"📉 {o_name}: -{other_pts} نقطة ({len(other_hand)} ورقة)")
                breakdown_text = "\n".join(losers_breakdown)
                current_score = p_check.get('points') or 0
                new_total_score = current_score + round_points
                db_query("UPDATE room_players SET points = %s WHERE room_id = %s AND user_id = %s", (new_total_score, room_id, p_check['user_id']), commit=True)
                p_name = p_check.get('player_name') or "لاعب"

                if score_limit > 0 and new_total_score >= score_limit:
                    scores_text = ""
                    num_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
                    all_players = get_ordered_players(room_id)
                    for rp_idx, rp in enumerate(all_players):
                        rp_name = rp.get('player_name') or "لاعب"
                        rp_score = rp.get('points') or 0
                        rp_marker = num_emojis[rp_idx] if rp_idx < len(num_emojis) else '👤'
                        scores_text += f"{rp_marker} {rp_name}: {rp_score} نقطة\n"
                    summary = f"🏆 انتهت اللعبة!\n\n🥇 الفائز: {p_name}\n💰 النقاط: {new_total_score}\n\n{scores_text}\n📊 نقاط الجولة الأخيرة:\n{breakdown_text}\n\n🎯 سقف اللعب: {score_limit} نقطة"
                    for target_p in players:
                        end_kb = make_end_kb(players, room, 'multi', for_user_id=target_p['user_id'])
                        await bot.send_message(target_p['user_id'], summary, reply_markup=end_kb)
                    db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
                    return
                elif score_limit == 0:
                    summary = f"🏆 {p_name} فاز بالجولة! (+{round_points} نقطة)\n\n📊 النقاط المأخوذة:\n{breakdown_text}\n\n🎯 الوضع: جولة واحدة"
                    for target_p in players:
                        end_kb = make_end_kb(players, room, 'multi', for_user_id=target_p['user_id'])
                        await bot.send_message(target_p['user_id'], summary, reply_markup=end_kb)
                    db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
                    return
                else:
                    from handlers.common import pending_next_round, _next_round_timeout
                    pending_next_round[room_id] = {'mode': 'multi', 'start_turn': 0}
                    round_text = f"🎉 {p_name} فاز بالجولة (+{round_points} نقطة)!\n💰 مجموعه: {new_total_score}/{score_limit}\n\n📊 النقاط المأخوذة:\n{breakdown_text}\n\n⏳ اضغط كمل خلال 20 ثانية"
                    next_kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 كمل جولة جديدة", callback_data=f"nextround_{room_id}")]
                    ])
                    for tp in players:
                        await bot.send_message(tp['user_id'], round_text, reply_markup=next_kb)
                    asyncio.create_task(_next_round_timeout(room_id, bot))
                    return

        curr_idx = room['turn_index']
        curr_p = players[curr_idx]
        curr_hand = safe_load(curr_p['hand'])

        if not any(check_validity(c, room['top_card'], room['current_color']) for c in curr_hand):
            deck = safe_load(room['deck'])
            if not deck:
                discard = safe_load(room['discard_pile'])
                if discard:
                    deck = discard
                    random.shuffle(deck)
                    db_query("UPDATE rooms SET discard_pile = '[]' WHERE room_id = %s", (room_id,), commit=True)
                else:
                    deck = generate_deck()
            new_card = deck.pop(0)
            curr_hand.append(new_card)
            is_playable = check_validity(new_card, room['top_card'], room['current_color'])
            next_turn = curr_idx if is_playable else (curr_idx + direction) % num_players
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(curr_hand), curr_p['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s, turn_index = %s WHERE room_id = %s", (json.dumps(deck), next_turn, room_id), commit=True)
            p_name = curr_p.get('player_name') or "لاعب"
            msgs = {}
            if is_playable:
                msgs[curr_p['user_id']] = f"📥 سحبت ({new_card}) وتگدر تلعبها 👍"
                for op in players:
                    if op['user_id'] != curr_p['user_id']:
                        msgs[op['user_id']] = f"📥 {p_name} سحب ورقة والورقة تشتغل وسيلعبها 🔄"
            else:
                msgs[curr_p['user_id']] = f"📥 سحبت ({new_card}) وما تشتغل ❌ والدور عبر"
                next_p = players[next_turn]
                next_name = next_p.get('player_name') or "لاعب"
                for op in players:
                    if op['user_id'] != curr_p['user_id']:
                        msgs[op['user_id']] = f"📥 {p_name} ما عنده ورقة مناسبة وسحب ورقة وما اشتغلت، الدور لـ {next_name} ✅"
            return await refresh_ui_multi(room_id, bot, msgs)

        dir_icon = "➡️" if direction == 1 else "⬅️"
        dir_arrow = "⤵️" if direction == 1 else "⤴️"
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
                players_info.append(f"{star}{num_marker}{dir_arrow} {pl_name}: {pl_cards} ورقة | 💰 {pl_score} نقطة")

            status_text = f"📦 السحب: {len(safe_load(room['deck']))} | 🗑 الملعوب: {len(safe_load(room.get('discard_pile', '[]')))+1} | {dir_icon} الاتجاه\n"
            status_text += "\n".join(players_info)
            if alert_msg_dict and p['user_id'] in alert_msg_dict:
                status_text += f"\n──────────────\n📢 {alert_msg_dict[p['user_id']]}"
            if room['turn_index'] == i:
                status_text += f"\n──────────────\n⏱ الك وقت 20 ثانية"
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
                row.append(InlineKeyboardButton(text=card, callback_data=f"mul_{room_id}_{card_idx}"))
                card_in_row += 1
                prev_group = c_group
                if card_in_row == 3: kb.append(row); row = []; card_in_row = 0
            if row: kb.append(row)

            controls = []
            if i == room['turn_index'] and len(hand) == 2:
                controls.append(InlineKeyboardButton(text="🚨 اونو!", callback_data=f"unomul_{room_id}"))
            for other in players:
                ohand = safe_load(other['hand'])
                if len(ohand) == 1 and not str(other.get('said_uno', 'false')).lower() in ['true', '1'] and other['user_id'] != p['user_id']:
                    o_name = other.get('player_name') or 'لاعب'
                    controls.append(InlineKeyboardButton(text=f"🪤 صيد {o_name}", callback_data=f"repmul_{room_id}_{other['user_id']}"))
                    break
            if controls: kb.append(controls)
            exit_row = [InlineKeyboardButton(text="🚪 انسحاب", callback_data=f"leavemul_{room_id}")]
            if p['user_id'] == room.get('creator_id'):
                exit_row.append(InlineKeyboardButton(text="⚙️", callback_data=f"rsettings_{room_id}"))
            kb.append(exit_row)

            if p.get('last_msg_id'):
                try:
                    msg = await bot.edit_message_text(
                        text=status_text,
                        chat_id=p['user_id'],
                        message_id=p['last_msg_id'],
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
                    )
                except:
                    try: await bot.delete_message(p['user_id'], p['last_msg_id'])
                    except: pass
                    msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            else:
                msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", (msg.message_id, room_id, p['user_id']), commit=True)
            if i == room['turn_index']:
                cd_msg = await bot.send_message(p['user_id'], "⏳ باقي 20 ثانية\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
                countdown_msgs[room_id] = {'bot': bot, 'chat_id': p['user_id'], 'msg_id': cd_msg.message_id}

        turn_timers[room_id] = asyncio.create_task(turn_timeout_multi(room_id, bot, room['turn_index']))
    except Exception as e: print(f"Multi UI Error: {e}")

@router.callback_query(F.data.startswith("mul_"))
async def handle_play_multi(c: types.CallbackQuery, state: FSMContext):
    try:
        parts = c.data.split("_")
        idx, room_id = int(parts[-1]), "_".join(parts[1:-1])
        cancel_timer(room_id)
        await asyncio.sleep(0)
        room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
        players = get_ordered_players(room_id)
        p_idx = room['turn_index']
        num_players = len(players)
        direction = room.get('direction') or 1
        if players[p_idx]['user_id'] != c.from_user.id: return await c.answer("مو دورك! ❌", show_alert=True)
        hand = sort_hand(safe_load(players[p_idx]['hand']))
        if idx >= len(hand): return await c.answer("حدث القائمة...", show_alert=True)
        card = hand[idx]
        p_name = players[p_idx].get('player_name') or "لاعب"

        if not check_validity(card, room['top_card'], room['current_color']):
            deck = safe_load(room['deck'])
            penalty = [deck.pop(0) for _ in range(2) if deck]
            hand.extend(penalty)
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(hand), c.from_user.id), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            alerts = {c.from_user.id: f"⛔ لعبت ورقة خطأ ({card}) وتعاقبت بسحب ورقتين!"}
            for op in players:
                if op['user_id'] != c.from_user.id:
                    alerts[op['user_id']] = f"⚠️ {p_name} لعب ورقة خطأ وتعاقب بسحب ورقتين!"
            return await refresh_ui_multi(room_id, c.bot, alerts)

        hand.pop(idx)
        was_uno_said = str(players[p_idx]['said_uno']).lower() in ['true', '1']
        updated_said_uno = was_uno_said if len(hand) == 1 else False
        db_query("UPDATE room_players SET hand = %s, said_uno = %s WHERE user_id = %s", (json.dumps(hand), updated_said_uno, c.from_user.id), commit=True)

        discard_pile = safe_load(room['discard_pile'])
        discard_pile.append(room['top_card'])

        alerts = {}
        if len(hand) == 1:
            if was_uno_said:
                for op in players:
                    if op['user_id'] != c.from_user.id:
                        alerts[op['user_id']] = f"✅ {p_name} صاح اونو وبقتله ورقة وحدة (في أمان)."
            else:
                for op in players:
                    if op['user_id'] != c.from_user.id:
                        alerts[op['user_id']] = f"⚠️ {p_name} بقتله ورقة وحدة ونسي يصيح اونو! صيده بسرعة! 🪤"

        if len(hand) == 0:
            db_query("UPDATE rooms SET discard_pile = %s, top_card = %s, current_color = %s WHERE room_id = %s", (json.dumps(discard_pile), card, card.split()[0], room_id), commit=True)
            return await refresh_ui_multi(room_id, c.bot)

        if any(x in card for x in ["🌈", "🔥", "💧", "🌊"]):
            await state.update_data(room_id=room_id, card_played=card, p_idx=p_idx, prev_color=room['current_color'])
            kb_list = [[InlineKeyboardButton(text="🔴", callback_data="clrmul_🔴"), InlineKeyboardButton(text="🔵", callback_data="clrmul_🔵")], [InlineKeyboardButton(text="🟡", callback_data="clrmul_🟡"), InlineKeyboardButton(text="🟢", callback_data="clrmul_🟢")]]
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
            await state.set_state(MultiGameStates.choosing_color)
            db_query("UPDATE rooms SET discard_pile = %s WHERE room_id = %s", (json.dumps(discard_pile), room_id), commit=True)
            pending_color_data[room_id] = {'card_played': card, 'p_idx': p_idx, 'prev_color': room['current_color']}
            cd_msg = await c.bot.send_message(c.from_user.id, "⏳ باقي 20 ثانية لاختيار اللون\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
            color_countdown_msgs[room_id] = {'bot': c.bot, 'chat_id': c.from_user.id, 'msg_id': cd_msg.message_id}
            color_timers[room_id] = asyncio.create_task(color_timeout_multi(room_id, c.bot, c.from_user.id))
            return

        next_turn = (p_idx + direction) % num_players
        if "🚫" in card:
            next_turn = (p_idx + direction * 2) % num_players
            skipped = players[(p_idx + direction) % num_players]
            sk_name = skipped.get('player_name') or "لاعب"
            alerts[skipped['user_id']] = f"🚫 {p_name} لعب منع وانمنعت!"
            for op in players:
                if op['user_id'] not in [c.from_user.id, skipped['user_id']]:
                    alerts[op['user_id']] = f"🚫 {p_name} لعب منع على {sk_name}!"
            alerts[c.from_user.id] = f"🚫 لعبت منع على {sk_name}!"
        elif "🔄" in card:
            new_dir = direction * -1
            db_query("UPDATE rooms SET direction = %s WHERE room_id = %s", (new_dir, room_id), commit=True)
            next_turn = (p_idx + new_dir) % num_players
            dir_text = "يمين ➡️" if new_dir == 1 else "يسار ⬅️"
            alerts[c.from_user.id] = f"🔄 غيرت الاتجاه لـ {dir_text}!"
            for op in players:
                if op['user_id'] != c.from_user.id:
                    alerts[op['user_id']] = f"🔄 {p_name} غير الاتجاه لـ {dir_text}!"
        elif "⬆️2" in card:
            victim_idx = (p_idx + direction) % num_players
            victim = players[victim_idx]
            v_name = victim.get('player_name') or "لاعب"
            deck = safe_load(room['deck'])
            v_hand = safe_load(victim['hand'])
            for _ in range(2):
                if deck: v_hand.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(v_hand), victim['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            next_turn = (p_idx + direction * 2) % num_players
            alerts[victim['user_id']] = f"⬆️2 {p_name} سحبك ورقتين وانمنعت!"
            alerts[c.from_user.id] = f"⬆️2 لعبت سحب 2 على {v_name}!"
            for op in players:
                if op['user_id'] not in [c.from_user.id, victim['user_id']]:
                    alerts[op['user_id']] = f"⬆️2 {p_name} سحب {v_name} ورقتين!"

        db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, discard_pile = %s WHERE room_id = %s", (card, card.split()[0], next_turn, json.dumps(discard_pile), room_id), commit=True)
        await refresh_ui_multi(room_id, c.bot, alerts)
    except Exception as e: print(f"Multi Play Error: {e}")

@router.callback_query(MultiGameStates.choosing_color, F.data.startswith("clrmul_"))
async def handle_color_multi(c: types.CallbackQuery, state: FSMContext):
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
        room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
        players = get_ordered_players(room_id)
        num_players = len(players)
        direction = room.get('direction') or 1
        p_name = players[p_idx].get('player_name') or "لاعب"
        alerts = {}

        if "🔥" in card:
            victim_idx = (p_idx + direction) % num_players
            victim = players[victim_idx]
            v_name = victim.get('player_name') or "لاعب"
            kb = [[InlineKeyboardButton(text="🕵️‍♂️ أتحداك", callback_data=f"rsmul_y_{room_id}_{data.get('prev_color')}_{chosen_color}"), InlineKeyboardButton(text="✅ قبول", callback_data=f"rsmul_n_{room_id}_{chosen_color}")]]
            msg_sent = await c.bot.send_message(victim['user_id'], f"🚨 {p_name} لعب 🔥 +4 وغير اللون لـ {chosen_color}!", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            cd_msg = await c.bot.send_message(victim['user_id'], "⏳ باقي 20 ثانية للرد\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
            challenge_countdown_msgs[room_id] = {'bot': c.bot, 'chat_id': victim['user_id'], 'msg_id': cd_msg.message_id}
            challenge_timers[room_id] = asyncio.create_task(challenge_timeout_multi(room_id, c.bot, victim['user_id'], chosen_color, msg_sent.message_id))
            await c.message.edit_text("⏳ بانتظار الخصم...")
            await state.clear()
            return

        penalty = 1 if "💧" in card else (2 if "🌊" in card else 0)
        deck = safe_load(room['deck'])
        if penalty > 0:
            victim_idx = (p_idx + direction) % num_players
            victim = players[victim_idx]
            v_name = victim.get('player_name') or "لاعب"
            v_hand = safe_load(victim['hand'])
            for _ in range(penalty):
                if deck: v_hand.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(v_hand), victim['user_id']), commit=True)
            next_turn = (p_idx + direction * 2) % num_players
            alerts[victim['user_id']] = f"🎨 {p_name} اختار اللون {chosen_color} وسحبك {penalty} ورقة!"
            alerts[c.from_user.id] = f"🎨 اخترت اللون {chosen_color} وسحبت {v_name} {penalty} ورقة!"
        else:
            next_turn = (p_idx + direction) % num_players
            alerts[c.from_user.id] = f"🎨 اخترت اللون {chosen_color}!"
            for op in players:
                if op['user_id'] != c.from_user.id:
                    alerts[op['user_id']] = f"🎨 {p_name} اختار اللون {chosen_color}!"
        db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, deck = %s WHERE room_id = %s", (f"{card} {chosen_color}", chosen_color, next_turn, json.dumps(deck), room_id), commit=True)
        await state.clear()
        await refresh_ui_multi(room_id, c.bot, alerts)
    except Exception as e: print(f"Multi Color Error: {e}")

@router.callback_query(F.data.startswith("rsmul_"))
async def handle_challenge_multi(c: types.CallbackQuery):
    try:
        parts = c.data.split("_")
        decision, room_id = parts[1], parts[2]
        cancel_challenge_timer(room_id)
        room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
        players = get_ordered_players(room_id)
        p_idx = room['turn_index']
        direction = room.get('direction') or 1
        num_players = len(players)
        victim_idx = (p_idx + direction) % num_players
        deck = safe_load(room['deck'])
        alerts = {}
        if decision == "n":
            v_hand = safe_load(players[victim_idx]['hand'])
            for _ in range(4):
                if deck: v_hand.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(v_hand), players[victim_idx]['user_id']), commit=True)
            next_turn = (p_idx + direction * 2) % num_players
            final_col = parts[3]
            alerts[players[p_idx]['user_id']] = "✅ الخصم قبل السحب!"
            alerts[players[victim_idx]['user_id']] = "📥 قبلت السحب وسحبت 4 ورقات وعبر دورك."
        else:
            prev_col, chosen_col = parts[3], parts[4]
            p_hand = safe_load(players[p_idx]['hand'])
            cheated = any(card.split()[0] == prev_col for card in p_hand if card.split()[0] in ['🔴', '🔵', '🟡', '🟢'])
            if cheated:
                for _ in range(6):
                    if deck: p_hand.append(deck.pop(0))
                db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(p_hand), players[p_idx]['user_id']), commit=True)
                next_turn = victim_idx
                alerts[players[p_idx]['user_id']] = "🕵️‍♂️ كشفك الخصم! سحبت 6 ورقات عقوبة."
                alerts[players[victim_idx]['user_id']] = "✅ نجح التحدي! الخصم كان يغش وسحب 6 ورقات."
            else:
                v_hand = safe_load(players[victim_idx]['hand'])
                for _ in range(6):
                    if deck: v_hand.append(deck.pop(0))
                db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(v_hand), players[victim_idx]['user_id']), commit=True)
                next_turn = (p_idx + direction * 2) % num_players
                alerts[players[p_idx]['user_id']] = "❌ فشل تحدي الخصم وسحب 6 ورقات!"
                alerts[players[victim_idx]['user_id']] = "❌ فشل التحدي! سحبت 6 ورقات."
            final_col = chosen_col
        db_query("UPDATE rooms SET deck = %s, turn_index = %s, current_color = %s, top_card = %s WHERE room_id = %s", (json.dumps(deck), next_turn, final_col, f"🔥 جوكر+4 {final_col}", room_id), commit=True)
        try: await c.message.delete()
        except: pass
        await refresh_ui_multi(room_id, c.bot, alerts)
    except Exception as e: print(f"Multi Challenge Error: {e}")

@router.callback_query(F.data.startswith("unomul_"))
async def handle_uno_multi(c: types.CallbackQuery):
    try:
        room_id = c.data.split("_")[1]
        db_query("UPDATE room_players SET said_uno = TRUE WHERE room_id = %s AND user_id = %s", (room_id, c.from_user.id), commit=True)
        players = get_ordered_players(room_id)
        me = next((p for p in players if p['user_id'] == c.from_user.id), None)
        p_name = me.get('player_name') if me else "لاعب"
        await c.answer()
        alerts = {c.from_user.id: "✅ صحت اونو بنجاح وأنت في أمان."}
        for op in players:
            if op['user_id'] != c.from_user.id:
                alerts[op['user_id']] = f"🚨 {p_name} صاح اونو! بقتله ورقة وحدة وهو في أمان."
        try:
            if IMG_UNO_SAFE_ME and IMG_UNO_SAFE_ME != "123":
                await _send_photo_then_schedule_delete(c.bot, c.from_user.id, IMG_UNO_SAFE_ME)
            if IMG_UNO_SAFE_OPP and IMG_UNO_SAFE_OPP != "123":
                for op in players:
                    if op['user_id'] != c.from_user.id:
                        await _send_photo_then_schedule_delete(c.bot, op['user_id'], IMG_UNO_SAFE_OPP)
        except: pass
        await refresh_ui_multi(room_id, c.bot, alerts)
    except Exception as e: print(f"Multi Uno Error: {e}")

@router.callback_query(F.data.startswith("repmul_"))
async def handle_catch_multi(c: types.CallbackQuery):
    try:
        parts = c.data.split("_")
        room_id, target_id = parts[1], int(parts[2])
        players = get_ordered_players(room_id)
        target = next(p for p in players if p['user_id'] == target_id)
        t_hand = safe_load(target['hand'])
        me = next((p for p in players if p['user_id'] == c.from_user.id), None)
        p_name = me.get('player_name') if me else "لاعب"
        t_name = target.get('player_name') or "لاعب"
        if len(t_hand) == 1 and not str(target.get('said_uno')).lower() in ['true', '1']:
            room_data = db_query("SELECT deck FROM rooms WHERE room_id = %s", (room_id,))[0]
            deck = safe_load(room_data['deck'])
            for _ in range(2):
                if deck: t_hand.append(deck.pop(0))
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(t_hand), target_id), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            await c.answer()
            try:
                if IMG_CATCH_SUCCESS and IMG_CATCH_SUCCESS != "123":
                    await _send_photo_then_schedule_delete(c.bot, c.from_user.id, IMG_CATCH_SUCCESS)
                if IMG_CATCH_PENALTY and IMG_CATCH_PENALTY != "123":
                    await _send_photo_then_schedule_delete(c.bot, target_id, IMG_CATCH_PENALTY)
            except: pass
            alerts = {
                c.from_user.id: f"🪤 صدت {t_name}! سحب ورقتين لأنه نسي الاونو.",
                target_id: f"⚠️ {p_name} صادك! سحبت ورقتين لأنك نسيت تصيح اونو!"
            }
            for op in players:
                if op['user_id'] not in [c.from_user.id, target_id]:
                    alerts[op['user_id']] = f"🪤 {p_name} صاد {t_name} لأنه نسي الاونو!"
            await refresh_ui_multi(room_id, c.bot, alerts)
        else:
            await c.answer("❌ ما تگدر تصيده حالياً!")
    except Exception as e: print(f"Multi Catch Error: {e}")

@router.callback_query(F.data.startswith("leavemul_"))
async def ask_leave_multi(c: types.CallbackQuery):
    rid = c.data.split("_")[1]
    kb = [[InlineKeyboardButton(text="✅ نعم", callback_data=f"cflv_{rid}"), InlineKeyboardButton(text="❌ لا", callback_data=f"cnlv_{rid}")]]
    await c.message.edit_text("🚪 هل أنت متأكد من الانسحاب؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("cflv_"))
async def confirm_leave_multi(c: types.CallbackQuery):
    rid = c.data.split("_")[1]
    cancel_timer(rid)
    players = get_ordered_players(rid)
    me = next((x for x in players if x['user_id'] == c.from_user.id), None)
    leave_name = me.get('player_name') if me else "لاعب"

    my_hand = safe_load(me['hand']) if me else []
    room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (rid,))
    if not room_data:
        return
    room = room_data[0]
    deck = safe_load(room['deck'])
    deck.extend(my_hand)
    random.shuffle(deck)

    my_idx = next((i for i, p in enumerate(players) if p['user_id'] == c.from_user.id), 0)
    curr_turn = room['turn_index']
    if my_idx < curr_turn:
        new_turn = curr_turn - 1
    elif my_idx == curr_turn:
        new_turn = curr_turn
    else:
        new_turn = curr_turn

    db_query("DELETE FROM room_players WHERE room_id = %s AND user_id = %s", (rid, c.from_user.id), commit=True)

    remaining_players = get_ordered_players(rid)
    num_remaining = len(remaining_players)

    if num_remaining >= 2:
        new_turn = new_turn % num_remaining
        db_query("UPDATE rooms SET deck = %s, turn_index = %s WHERE room_id = %s", (json.dumps(deck), new_turn, rid), commit=True)

        leave_end_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]
        ])
        await c.bot.send_message(c.from_user.id, f"🚪 انسحبت من اللعبة.", reply_markup=leave_end_kb)

        alerts = {}
        for p in remaining_players:
            alerts[p['user_id']] = f"🚪 {leave_name} انسحب! باقي {num_remaining} لاعبين. اللعب مستمر."
        await refresh_ui_multi(rid, c.bot, alerts)
    else:
        all_players_before = players + [{'user_id': c.from_user.id, 'player_name': leave_name}]
        end_kb_me = make_end_kb(all_players_before, room, 'multi', for_user_id=c.from_user.id)
        await c.bot.send_message(c.from_user.id, f"🚪 انسحبت من اللعبة.", reply_markup=end_kb_me)
        if remaining_players:
            winner = remaining_players[0]
            w_name = winner.get('player_name') or "لاعب"
            end_kb_w = make_end_kb(all_players_before, room, 'multi', for_user_id=winner['user_id'])
            await c.bot.send_message(winner['user_id'], f"🏆 {w_name} فاز! كل اللاعبين انسحبوا.", reply_markup=end_kb_w)
        db_query("DELETE FROM rooms WHERE room_id = %s", (rid,), commit=True)

@router.callback_query(F.data.startswith("cnlv_"))
async def cancel_leave_multi(c: types.CallbackQuery):
    rid = c.data.split("_")[1]
    await refresh_ui_multi(rid, c.bot)

# دالة إرسال التنبيهات المدمجة - (انضمام ومشاهدة)
async def notify_followers_game_started(player_id, player_name, bot):
    # جلب المتابعين الذين فعلوا الجرس لهذا اللاعب
    followers = db_query("""
        SELECT follower_id FROM follows 
        WHERE following_id = %s AND notify_games = 1
    """, (player_id,))
    
    if not followers:
        return

    # نص التنبيه الموحد
    text = f"🚀 **تنبيه متابعة!**\n\nصديقك **{player_name}** بدأ لعبة أونو الآن! ماذا تريد أن تفعل؟"
    
    # أزرار مزدوجة (انضمام ومشاهدة)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 انضمام للعب", callback_data=f"view_profile_{player_id}"),
            InlineKeyboardButton(text="👁 مشاهدة فقط", callback_data=f"spectate_{player_id}")
        ]
    ])

    for f in followers:
        try:
            await bot.send_message(f['follower_id'], text, reply_markup=kb)
        except Exception:
            continue
