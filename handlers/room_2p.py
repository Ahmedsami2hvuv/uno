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
countdown_msgs = {}

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
    colors = ['🔴', '🟡', '🟢', '🔵']
    deck = []
    for color in colors:
        deck.append(f"{color} 0") # ورقة واحدة صفر (4 مجموعاً)
        for i in range(1, 10):
            deck.extend([f"{color} {i}", f"{color} {i}"]) # ورقتين 1-9 (72 مجموعاً)
        deck.extend([f"{color} 🚫", f"{color} 🚫"]) # منع (8 مجموعاً)
        deck.extend([f"{color} 🔄", f"{color} 🔄"]) # تحويل (8 مجموعاً)
        deck.extend([f"{color} +2", f"{color} +2"]) # سحب 2 (8 مجموعاً)
    
    # الجوكرات حسب طلبك:
    deck.extend(["🔥 جوكر+4"] * 4) # (4 مجموعاً)
    deck.append("🌈 جوكر+1")        # (1 مجموعاً)
    deck.append("🌈 جوكر+2")        # (1 مجموعاً)
    deck.extend(["🌈 جوكر ألوان"] * 4) # لإكمال العدد أو حسب رغبتك في بقية الـ 110
    
    random.shuffle(deck)
    return deck

def check_validity(card, top_card, current_color):
    """
    التحقق من صحة الورقة الملعوبة
    - الجوكرات الملونة (🌈) تعتبر صالحة دائماً وتحتاج اختيار لون
    - جوكرات السحب (💧, 🌊, 🔥) تعتبر صالحة دائماً وبعدها يمكن لعب أي لون
    - باقي الأوراق تتبع القواعد العادية (نفس اللون أو نفس الرقم)
    """
    
    # جوكر ألوان (🌈) - يختار لون ويمرر الدور للخصم
    if "🌈" in card:
        return True
        
    # جوكرات السحب (💧, 🌊, 🔥) - صالحة دائماً وبعدها يمكن لعب أي لون
    if any(x in card for x in ["🔥", "💧", "🌊"]):
        return True
    
    # باقي الأوراق (الأرقام والأكشنات)
    parts = card.split()
    if len(parts) < 2: 
        return False
    
    c_color, c_value = parts[0], parts[1]
    
    # نفس اللون
    if c_color == current_color: 
        return True
    
    # نفس الرقم أو نفس الأكشن
    top_parts = top_card.split()
    top_value = top_parts[1] if len(top_parts) > 1 else top_parts[0]
    
    if c_value == top_value: 
        return True
    
    # إذا ما تطابق أي شرط
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
    # إلغاء عداد الدور
    task = turn_timers.pop(room_id, None)
    if task and not task.done():
        task.cancel()
    
    # إلغاء رسالة عداد الدور
    cd = countdown_msgs.pop(room_id, None)
    if cd:
        asyncio.create_task(_delete_countdown(cd['bot'], cd['chat_id'], cd['msg_id']))
    
    # إلغاء تايمر اختيار اللون
    color_task = color_timers.pop(room_id, None)
    if color_task and not color_task.done():
        color_task.cancel()
    
    # إلغاء رسالة عداد اختيار اللون
    color_cd = color_countdown_msgs.pop(room_id, None)
    if color_cd:
        asyncio.create_task(_delete_countdown(color_cd['bot'], color_cd['chat_id'], color_cd['msg_id']))
    
    # إلغاء تايمر التحدي
    challenge_task = challenge_timers.pop(room_id, None)
    if challenge_task and not challenge_task.done():
        challenge_task.cancel()
    
    # إلغاء رسالة عداد التحدي
    challenge_cd = challenge_countdown_msgs.pop(room_id, None)
    if challenge_cd:
        asyncio.create_task(_delete_countdown(challenge_cd['bot'], challenge_cd['chat_id'], challenge_cd['msg_id']))

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
        if not cd_info:
            return
            
        # العداد الأصلي (20 ثانية)
        for step in range(10, 0, -1):
            # التحقق من الغرفة في كل دورة
            room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
            if not room_data:
                # حذف رسالة العداد إذا الغرفة غير موجودة
                if cd_info:
                    try: 
                        await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
                    except: 
                        pass
                return
                
            room = room_data[0]
            
            # إذا تغير الدور أو انتهت اللعبة
            if room['status'] != 'playing' or room['turn_index'] != expected_turn:
                # حذف رسالة العداد
                if cd_info:
                    try: 
                        await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
                    except: 
                        pass
                return
            
            # إذا ألغي التايمر
            if room_id not in turn_timers:
                if cd_info:
                    try: 
                        await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
                    except: 
                        pass
                return
            
            # حساب الوقت المتبقي
            remaining = step * 2
            
            # تحديد لون الشريط حسب الوقت المتبقي
            if remaining > 10:
                # أكثر من 10 ثواني - أخضر
                filled = "🟢" * step
                empty = "⚫" * (10 - step)
            elif remaining > 5:
                # بين 5 و 10 ثواني - أصفر
                filled = "🟡" * step
                empty = "⚫" * (10 - step)
            else:
                # أقل من 5 ثواني - أحمر
                filled = "🔴" * step
                empty = "⚫" * (10 - step)
            
            bar = filled + empty
            
            # جلب بيانات اللاعبين لبناء النص الكامل
            players = get_ordered_players(room_id)
            
            # بناء معلومات اللاعبين
            players_info = []
            for pl_idx, pl in enumerate(players):
                pl_name = pl.get('player_name') or 'لاعب'
                pl_cards = len(safe_load(pl['hand']))
                star = "✅" if pl_idx == expected_turn else "⏳"
                players_info.append(f"{star} {pl_name}: {pl_cards} ورقة")
            
            # بناء النص الكامل مع الوقت المحدث
            full_text = f"📦 السحب: {len(safe_load(room['deck']))} ورقات\n"
            full_text += f"🗑 النازلة: {len(safe_load(room.get('discard_pile', '[]')))+1} ورقات\n"
            full_text += "\n".join(players_info)
            full_text += f"\n──────────────\n⏳ باقي {remaining} ثانية\n{bar}"
            full_text += f"\n──────────────\n✅ دورك 👍🏻"
            full_text += f"\n🃏 الورقة النازلة: [ {room['top_card']} ]"
            
            # تحديث نفس الرسالة (الرسالة الرئيسية)
            if cd_info and cd_info.get('is_main_message'):
                try:
                    # نحتاج لجلب الأزرار الحالية - نخزنها في مكان ما
                    # للتبسيط، سنستخدم None وسيتم إعادة إنشاء الأزرار في refresh_ui
                    await bot.edit_message_text(
                        chat_id=cd_info['chat_id'],
                        message_id=cd_info['msg_id'],
                        text=full_text
                    )
                except Exception as e:
                    print(f"خطأ في تعديل رسالة الوقت: {e}")
            
            await asyncio.sleep(2)

        # بعد انتهاء الوقت، نحذف رسالة العداد
        if cd_info:
            try: 
                await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
            except: 
                pass
        
        # --- التحقق من الغرفة والدور قبل تنفيذ العقوبة ---
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: 
            return
        room = room_data[0]
        
        if room['status'] != 'playing' or room['turn_index'] != expected_turn: 
            return
        
        players = get_ordered_players(room_id)
        curr_p = players[expected_turn]
        p_id = curr_p['user_id']
        opp_id = players[(expected_turn + 1) % 2]['user_id']
        p_name = curr_p.get('player_name') or "لاعب"
        curr_hand = safe_load(curr_p['hand'])

        # --- تنفيذ المنطق: عقوبة ضياع الوقت ---
        deck = safe_load(room['deck'])
        if not deck:
            deck = generate_h2o_deck()
            random.shuffle(deck)
        
        penalty_card = deck.pop(0)
        curr_hand.append(penalty_card)
        
        # نقل الدور للمقابل
        next_turn = (expected_turn + 1) % 2
        
        # تحديث قاعدة البيانات
        db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", 
                (json.dumps(curr_hand), p_id), commit=True)
        db_query("UPDATE rooms SET turn_index = %s, deck = %s WHERE room_id = %s", 
                (next_turn, json.dumps(deck), room_id), commit=True)

        # تنظيف العدادات
        turn_timers.pop(room_id, None)
        cd_del = countdown_msgs.pop(room_id, None)
        if cd_del:
            try: 
                await bot.delete_message(cd_del['chat_id'], cd_del['msg_id'])
            except: 
                pass

        # إبلاغ اللاعبين
        msgs = {
            p_id: f"⏰ خلص وقتك! تعاقبت بسحب ورقة ({penalty_card}) وانتقل الدور للمنافس.",
            opp_id: f"⏰ {p_name} خلص وقته وتعاقب بسحب ورقة من الكومة، الدور صار إلك ✅"
        }
        await refresh_ui_2p(room_id, bot, msgs)

    except asyncio.CancelledError:
        # حذف رسالة العداد عند الإلغاء
        cd_info = countdown_msgs.get(room_id)
        if cd_info:
            try: 
                await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
            except: 
                pass
        # إعادة رفع الاستثناء للإلغاء الصحيح
        raise
        
    except Exception as e:
        print(f"Timer error 2p: {e}")
        # محاولة حذف رسالة العداد في حالة الخطأ
        cd_info = countdown_msgs.get(room_id)
        if cd_info:
            try: 
                await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
            except: 
                pass
        

async def color_timeout_2p(room_id, bot, player_id):
    try:
        cd_info = color_countdown_msgs.get(room_id)
        for step in range(9, -1, -1):
            # التحقق من الغرفة في كل دورة
            room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
            if not room_data:
                # حذف رسالة العداد
                if cd_info:
                    try: await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
                    except: pass
                return
                
            room = room_data[0]
            if room['status'] != 'playing':
                if cd_info:
                    try: await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
                    except: pass
                return
                
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
                        f"⏳ الوقت المتبقي: {remaining} ثانية لاختيار اللون\n{bar}"
                    )
                    cd_info['msg_id'] = new_msg.message_id
                except Exception as e:
                    print(f"Color countdown send error: {e}")
        
        # حذف رسالة العداد النهائية
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
        
        # في جميع حالات جوكر السحب، الدور يرجع للاعب نفسه
        next_turn = p_idx  # الدور يرجع للاعب نفسه
        
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
            alerts[opp_id] = f"⏰ {p_name} ما اختار اللون بالوقت! تم اختيار {chosen_color} تلقائياً وسحبك {penalty} ورقة والدور رجع له!"
            alerts[player_id] = f"⏰ انتهى الوقت! تم اختيار اللون {chosen_color} تلقائياً."
        else:
            alerts[opp_id] = f"🎨 {p_name} اختار اللون {chosen_color} والدور رجع له!"
            alerts[player_id] = f"🎨 اخترت اللون {chosen_color} والدور رجع لك!"
            
        db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, deck = %s WHERE room_id = %s", 
                (f"{card} {chosen_color}", chosen_color, next_turn, json.dumps(deck), room_id), commit=True)
        
        turn_timers.pop(room_id, None)
        countdown_msgs.pop(room_id, None)
        await refresh_ui_2p(room_id, bot, alerts)
        
    except asyncio.CancelledError:
        # حذف رسالة العداد عند الإلغاء
        cd_info = color_countdown_msgs.get(room_id)
        if cd_info:
            try: await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
            except: pass
        raise
    except Exception as e:
        print(f"Color timer error 2p: {e}")
        
    except asyncio.CancelledError:
        # حذف رسالة العداد عند الإلغاء
        cd_info = color_countdown_msgs.get(room_id)
        if cd_info:
            try: await bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
            except: pass
        raise
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
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return
        room = room_data[0]
        players = get_ordered_players(room_id)
        
        curr_idx = room['turn_index']
        curr_p = players[curr_idx]
        curr_hand = safe_load(curr_p['hand'])
        p_id = curr_p['user_id']
        opp_id = players[(curr_idx + 1) % 2]['user_id']

        # فحص إذا كان اللاعب عنده ورقة قابلة للعب
        is_playable = any(check_validity(c, room['top_card'], room['current_color']) for c in curr_hand)

        if not is_playable:
            # إطلاق مهمة السحب التلقائي
            if not alert_msg_dict or ("سحب" not in str(alert_msg_dict.get(p_id, ""))):
                asyncio.create_task(background_auto_draw(room_id, bot, curr_idx))
        else:
            turn_timers[room_id] = asyncio.create_task(turn_timeout_2p(room_id, bot, curr_idx))

        # --- بناء واجهة اللاعبين ---
        for i, p in enumerate(players):
            hand = sort_hand(safe_load(p['hand']))
            turn_status = "✅ دورك 👍🏻" if room['turn_index'] == i else "⏳ مو دورك"
            
            # معلومات اللاعبين
            players_info = []
            for pl_idx, pl in enumerate(players):
                pl_name = pl.get('player_name') or 'لاعب'
                pl_cards = len(safe_load(pl['hand']))
                star = "✅" if pl_idx == room['turn_index'] else "⏳"
                players_info.append(f"{star} {pl_name}: {pl_cards} ورقة")

            # بناء النص الرئيسي
            status_text = f"📦 السحب: {len(safe_load(room['deck']))} ورقات\n"
            status_text += f"🗑 النازلة: {len(safe_load(room.get('discard_pile', '[]')))+1} ورقات\n"
            status_text += "\n".join(players_info)
            
            # إضافة رسالة التنبيه إن وجدت
            if alert_msg_dict and p['user_id'] in alert_msg_dict:
                status_text += f"\n──────────────\n📢 {alert_msg_dict[p['user_id']]}"
            
            # إضافة رسالة الوقت إذا كان هذا هو صاحب الدور
            if i == room['turn_index']:
                # سنقوم بتحديث هذه الرسالة لاحقاً من دالة الوقت
                status_text += f"\n──────────────\n⏳ باقي 20 ثانية\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢"
            
            # الفاصل والورقة النازلة
            status_text += f"\n──────────────\n{turn_status}"
            status_text += f"\n🃏 الورقة النازلة: [ {room['top_card']} ]"

            # بناء الكيبورد (الأوراق)
            kb = []
            row = []
            for card_idx, card in enumerate(hand):
                row.append(InlineKeyboardButton(text=card, callback_data=f"pl_{room_id}_{card_idx}"))
                if len(row) == 3: 
                    kb.append(row)
                    row = []
            if row: 
                kb.append(row)

            # أزرار التحكم
            controls = []
            if i == room['turn_index']:
                can_play = any(check_validity(c, room['top_card'], room['current_color']) for c in hand)
                
                # زر التمرير يظهر فقط إذا اللاعب ليس لديه أوراق قابلة للعب
                if not can_play:
                    controls.append(InlineKeyboardButton(text="➡️ مرر الدور", callback_data=f"pass_{room_id}"))
                
                # زر اونو يظهر إذا عنده ورقتين
                if len(hand) == 2:
                    controls.append(InlineKeyboardButton(text="🚨 اونو!", callback_data=f"un_{room_id}"))
            
            # زر الصيد
            opp = players[(i+1)%2]
            if len(safe_load(opp['hand'])) == 1 and not str(opp.get('said_uno', 'false')).lower() in ['true', '1']:
                controls.append(InlineKeyboardButton(text="🪤 صيدة!", callback_data=f"ct_{room_id}"))
            
            if controls: 
                kb.append(controls)
            
            # أزرار إضافية
            extra_buttons = [InlineKeyboardButton(text="🚪 انسحاب", callback_data=f"ex_{room_id}")]
            if p['user_id'] == room.get('creator_id'):
                extra_buttons.append(InlineKeyboardButton(text="⚙️", callback_data=f"rsettings_{room_id}"))
            kb.append(extra_buttons)

            # تحديث الرسالة
            try:
                if p.get('last_msg_id'):
                    try:
                        # تحديث رسالة اللعب الرئيسية
                        await bot.edit_message_text(
                            text=status_text,
                            chat_id=p['user_id'],
                            message_id=p['last_msg_id'],
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
                        )
                        
                        # إذا كان هذا هو صاحب الدور، نخزن معلومات الرسالة الرئيسية
                        if i == room['turn_index']:
                            # حذف أي رسالة عداد سابقة
                            old_cd = countdown_msgs.get(room_id)
                            if old_cd:
                                try: await bot.delete_message(old_cd['chat_id'], old_cd['msg_id'])
                                except: pass
                            
                            # نخزن معلومات الرسالة الرئيسية
                            countdown_msgs[room_id] = {
                                'bot': bot, 
                                'chat_id': p['user_id'], 
                                'msg_id': p['last_msg_id'],
                                'is_main_message': True
                            }
                    except:
                        # إذا فشل التعديل، نرسل رسالة جديدة
                        msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                        db_query("UPDATE room_players SET last_msg_id = %s WHERE user_id = %s", (msg.message_id, p['user_id']), commit=True)
                        
                        # تخزين معلومات الرسالة الجديدة
                        if i == room['turn_index']:
                            old_cd = countdown_msgs.get(room_id)
                            if old_cd:
                                try: await bot.delete_message(old_cd['chat_id'], old_cd['msg_id'])
                                except: pass
                            
                            countdown_msgs[room_id] = {
                                'bot': bot, 
                                'chat_id': p['user_id'], 
                                'msg_id': msg.message_id,
                                'is_main_message': True
                            }
                else:
                    # لا توجد رسالة سابقة، نرسل رسالة جديدة
                    msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
                    db_query("UPDATE room_players SET last_msg_id = %s WHERE user_id = %s", (msg.message_id, p['user_id']), commit=True)
                    
                    # تخزين معلومات الرسالة الجديدة
                    if i == room['turn_index']:
                        old_cd = countdown_msgs.get(room_id)
                        if old_cd:
                            try: await bot.delete_message(old_cd['chat_id'], old_cd['msg_id'])
                            except: pass
                        
                        countdown_msgs[room_id] = {
                            'bot': bot, 
                            'chat_id': p['user_id'], 
                            'msg_id': msg.message_id,
                            'is_main_message': True
                        }
                    
            except Exception as ui_err:
                print(f"❌ ما قدرت أرسل الواجهة لـ {p['user_id']}: {ui_err}")
                continue
                
    except Exception as e: 
        print(f"UI Error: {e}")

async def background_auto_draw(room_id, bot, curr_idx):
    """دالة السحب التلقائي في الخلفية عندما لا يوجد أوراق مناسبة"""
    try:
        players = get_ordered_players(room_id)
        if curr_idx >= len(players):
            return
            
        p_id = players[curr_idx]['user_id']
        opp_id = players[(curr_idx + 1) % 2]['user_id']
        p_name = players[curr_idx].get('player_name') or "لاعب"
        
        # إرسال رسالة واحدة فقط للسحب التلقائي داخل واجهة اللعب للاعب صاحب الدور فقط
        alerts = {
            p_id: "⏳ ليس لديك أوراق مناسبة... سيتم سحب ورقة لك خلال 5 ثواني"
        }
        
        # تحديث الواجهة مع رسالة السحب (مرة واحدة فقط)
        await refresh_ui_2p(room_id, bot, alerts)
        
        # انتظار 5 ثواني بدون إرسال رسائل إضافية
        await asyncio.sleep(5)
        
        # التحقق من الغرفة والدور
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data:
            return
        room = room_data[0]
        
        if room['turn_index'] != curr_idx or room['status'] != 'playing':
            return
        
        # سحب ورقة من الكومة
        deck = safe_load(room['deck'])
        if not deck:
            deck = generate_h2o_deck()
            random.shuffle(deck)
        
        curr_hand = safe_load(players[curr_idx]['hand'])
        new_card = deck.pop(0)
        curr_hand.append(new_card)
        
        # تحديث قاعدة البيانات
        db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", 
                (json.dumps(curr_hand), p_id), commit=True)
        db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", 
                (json.dumps(deck), room_id), commit=True)
        
        # التحقق من صلاحية الورقة المسحوبة
        if check_validity(new_card, room['top_card'], room['current_color']):
            alerts = {
                p_id: f"✅ سحبت ورقة ({new_card}) وهذه الورقة تعمل! لديك 20 ثانية للعبها",
                opp_id: f"🎯 {p_name} سحب ورقة ({new_card}) وهي تعمل! سيلعبها خلال 20 ثانية"
            }
            await refresh_ui_2p(room_id, bot, alerts)
            turn_timers[room_id] = asyncio.create_task(turn_timeout_2p(room_id, bot, curr_idx))
        else:
            alerts = {
                p_id: f"📥 سحبت ورقة ({new_card}) وهي لا تعمل ❌",
                opp_id: f"📥 {p_name} سحب ورقة ({new_card}) وهي لا تعمل"
            }
            await refresh_ui_2p(room_id, bot, alerts)
            asyncio.create_task(auto_pass_with_countdown(room_id, bot, curr_idx, new_card))
            
    except Exception as e:
        print(f"Error in background_auto_draw: {e}")

async def auto_pass_with_countdown(room_id, bot, expected_turn, drawn_card):
    """تمرير الدور تلقائياً مع عد تنازلي داخل واجهة اللعب"""
    try:
        players = get_ordered_players(room_id)
        if expected_turn >= len(players):
            return
        p_id = players[expected_turn]['user_id']
        
        # عد تنازلي 12 ثانية مع تحديث الواجهة
        for step in range(6, 0, -1):
            # التحقق من الغرفة في كل دورة
            room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
            if not room_data:
                return
            room = room_data[0]
            
            if room['turn_index'] != expected_turn or room['status'] != 'playing':
                return
            
            remaining = step * 2
            
            # تحديد لون الشريط حسب الوقت المتبقي
            if remaining > 8:
                # أكثر من 8 ثواني - أخضر
                filled = "🟢" * step
                empty = "⚫" * (6 - step)
            elif remaining > 4:
                # بين 4 و 8 ثواني - أصفر
                filled = "🟡" * step
                empty = "⚫" * (6 - step)
            else:
                # أقل من 4 ثواني - أحمر
                filled = "🔴" * step
                empty = "⚫" * (6 - step)
            
            bar = filled + empty
            
            # تحديث الواجهة مع العد التنازلي والشريط
            alerts = {
                p_id: f"📥 سحبت ورقة ({drawn_card}) وهي لا تعمل ❌\n⏳ باقي {remaining} ثانية للتمرير التلقائي\n{bar}"
            }
            await refresh_ui_2p(room_id, bot, alerts)
            
            await asyncio.sleep(2)
        
        # بعد انتهاء العد، نمرر الدور
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data:
            return
        room = room_data[0]
        
        if room['turn_index'] != expected_turn or room['status'] != 'playing':
            return
        
        players = get_ordered_players(room_id)
        curr_idx = room['turn_index']
        next_idx = (curr_idx + 1) % 2
        p_name = players[curr_idx].get('player_name') or "لاعب"
        
        # تمرير الدور
        db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", 
                (next_idx, room_id), commit=True)
        
        # إلغاء التايمر الحالي
        cancel_timer(room_id)
        
        # إشعار الجميع داخل الواجهة
        alerts = {
            players[curr_idx]['user_id']: f"⏱ انتهى الوقت! تم تمرير دورك تلقائياً (سحبت {drawn_card} ولا تعمل)",
            players[next_idx]['user_id']: f"⏱ {p_name} انتهى وقته وصار دورك الآن!"
        }
        
        await refresh_ui_2p(room_id, bot, alerts)
        
    except Exception as e:
        print(f"Error in auto_pass_with_countdown: {e}")

async def auto_pass_after_auto_draw(room_id, bot, expected_turn, drawn_card):
    """تمرير الدور تلقائياً بعد 12 ثانية من سحب ورقة لا تعمل"""
    try:
        await asyncio.sleep(12)
        
        # التحقق من الغرفة
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data:
            return
        room = room_data[0]
        
        if room['turn_index'] != expected_turn or room['status'] != 'playing':
            return
        
        players = get_ordered_players(room_id)
        curr_idx = room['turn_index']
        next_idx = (curr_idx + 1) % 2
        p_name = players[curr_idx].get('player_name') or "لاعب"
        opp_id = players[next_idx]['user_id']
        
        # تمرير الدور
        db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", 
                (next_idx, room_id), commit=True)
        
        # إلغاء التايمر الحالي
        cancel_timer(room_id)
        
        # إشعار الجميع
        alerts = {
            players[curr_idx]['user_id']: f"⏱ انتهى الوقت! تم تمرير دورك تلقائياً (سحبت {drawn_card} ولا تعمل)",
            players[next_idx]['user_id']: f"⏱ {p_name} انتهى وقته وصار دورك الآن!"
        }
        
        await refresh_ui_2p(room_id, bot, alerts)
        
    except Exception as e:
        print(f"Error in auto_pass_after_auto_draw: {e}")

@router.callback_query(F.data.startswith("pl_"))
async def handle_play(c: types.CallbackQuery, state: FSMContext):
    try:
        # استخراج البيانات من callback
        parts = c.data.split("_")
        idx = int(parts[-1])
        room_id = "_".join(parts[1:-1])
        
        # حذف رسالة العداد الحالية
        cd_info = countdown_msgs.get(room_id)
        if cd_info:
            try: await c.bot.delete_message(cd_info['chat_id'], cd_info['msg_id'])
            except: pass
        countdown_msgs.pop(room_id, None)
        
        # إلغاء التايمر الحالي
        cancel_timer(room_id)
        await asyncio.sleep(0)
        
        # جلب بيانات الغرفة
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data:
            return await c.answer("⚠️ الغرفة غير موجودة", show_alert=True)
        room = room_data[0]
        
        # جلب اللاعبين
        players = get_ordered_players(room_id)
        
        # التحقق من الدور
        p_idx = room['turn_index']
        if players[p_idx]['user_id'] != c.from_user.id:
            return await c.answer("❌ مو دورك!", show_alert=True)
        
        # جلب يد اللاعب
        hand = sort_hand(safe_load(players[p_idx]['hand']))
        if idx >= len(hand):
            return await c.answer("⚠️ حدث خطأ في اختيار الورقة", show_alert=True)
        
        # الورقة المختارة
        card = hand[idx]
        p_name = players[p_idx].get('player_name') or "لاعب"
        opp_idx = (p_idx + 1) % 2
        opp_id = players[opp_idx]['user_id']
        
        # التحقق من صلاحية الورقة
        if not check_validity(card, room['top_card'], room['current_color']):
            # عقوبة الورقة الخطأ
            deck = safe_load(room['deck'])
            penalty_cards = []
            for _ in range(1):
                if deck:
                    penalty_cards.append(deck.pop(0))
            
            if penalty_cards:
                hand.extend(penalty_cards)
                db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", 
                        (json.dumps(hand), c.from_user.id), commit=True)
                db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", 
                        (json.dumps(deck), room_id), commit=True)
            
            print(f"DEBUG: {p_name} tried {card} on {room['top_card']} (Color: {room['current_color']}) -> REJECTED")
            alerts = {
                c.from_user.id: f"⛔ لعبت ورقة خطأ ({card}) وتعاقبت بسحب ورقة واحدة!" + 
                               (f" (سحبت: {', '.join(penalty_cards)})" if penalty_cards else ""),
                opp_id: f"⚠️ {p_name} لعب ورقة خطأ وتعاقب بسحب ورقة واحدة!"
            }
            return await refresh_ui_2p(room_id, c.bot, alerts)
        
        # إزالة الورقة من اليد
        hand.pop(idx)
        
        # تحديث حالة UNO
        was_uno_said = str(players[p_idx].get('said_uno', False)).lower() in ['true', '1', 'true']
        updated_said_uno = was_uno_said if len(hand) == 1 else False
        
        db_query("UPDATE room_players SET hand = %s, said_uno = %s WHERE user_id = %s", 
                (json.dumps(hand), updated_said_uno, c.from_user.id), commit=True)
        
        # تحديث كومة المرمي
        discard_pile = safe_load(room.get('discard_pile', '[]'))
        discard_pile.append(room['top_card'])
        
        alerts = {}
        
        # التحقق من الفوز
        if len(hand) == 0:
            # حساب النقاط
            opp_hand = safe_load(players[opp_idx]['hand'])
            points = calculate_points(opp_hand)
            
            # تحديث النقاط
            current_points = players[p_idx].get('online_points', 0)
            new_points = current_points + points
            db_query("UPDATE users SET online_points = %s WHERE user_id = %s", 
                    (new_points, c.from_user.id), commit=True)
            
            # تحديث الغرفة
            db_query("UPDATE rooms SET discard_pile = %s, top_card = %s, current_color = %s WHERE room_id = %s", 
                    (json.dumps(discard_pile), card, card.split()[0], room_id), commit=True)
            
            # حذف أوراق اللعب السابقة
            db_query("DELETE FROM room_players WHERE room_id = %s", (room_id,), commit=True)
            
            # التحقق من الفوز باللعبة
            score_limit = room.get('score_limit', 500)
            total_points = new_points
            
            # رسالة الفوز مع النقاط
            win_text = f"🏆 **{p_name} فاز باللعبة!** 🏆\n\n"
            win_text += f"📊 نقاط هذه الجولة: {points}\n"
            win_text += f"💰 إجمالي نقاطك: {total_points}\n\n"
            
            if score_limit > 0:
                win_text += f"🎯 هدف اللعبة كان: {score_limit} نقطة"
            
            end_kb = make_end_kb(players, room, '2p')
            for p in players:
                await c.bot.send_message(
                    p['user_id'],
                    win_text,
                    reply_markup=end_kb
                )
            
            # تنظيف الغرفة
            db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
            return
        
        # التحقق من حالة UNO
        if len(hand) == 1:
            if was_uno_said:
                alerts[opp_id] = f"✅ {p_name} صاح اونو وبقتله ورقة وحدة (في أمان)."
                # إرسال صور UNO
                try:
                    if IMG_UNO_SAFE_ME and IMG_UNO_SAFE_ME != "123":
                        await _send_photo_then_schedule_delete(c.bot, c.from_user.id, IMG_UNO_SAFE_ME)
                    if IMG_UNO_SAFE_OPP and IMG_UNO_SAFE_OPP != "123":
                        await _send_photo_then_schedule_delete(c.bot, opp_id, IMG_UNO_SAFE_OPP)
                except:
                    pass
            else:
                alerts[opp_id] = f"⚠️ {p_name} بقتله ورقة وحدة ونسي يصيح اونو! صيده بسرعة! 🪤"
        
        # معالجة الأوراق الخاصة
        next_turn = (p_idx + 1) % 2  # الدور ينتقل للخصم (القيمة الافتراضية)
        
        if any(x in card for x in ["🌈", "🔥", "💧", "🌊"]):
            # إلغاء أي تايمر سابق لاختيار اللون
            cancel_color_timer(room_id)
            
            # التحقق من نوع الجوكر
            if "🌈" in card:
                # جوكر ألوان فقط - يحتاج لاختيار لون ويمرر الدور للخصم
                await state.update_data(
                    room_id=room_id, 
                    card_played=card, 
                    p_idx=p_idx, 
                    prev_color=room['current_color']
                )
                
                # بناء كيبورد اختيار اللون مع أسماء الألوان
                color_kb = [
                    [
                        InlineKeyboardButton(text="🔴 أحمر", callback_data="cl_🔴"),
                        InlineKeyboardButton(text="🔵 أزرق", callback_data="cl_🔵")
                    ],
                    [
                        InlineKeyboardButton(text="🟡 أصفر", callback_data="cl_🟡"),
                        InlineKeyboardButton(text="🟢 أخضر", callback_data="cl_🟢")
                    ]
                ]
                
                # إضافة أوراق اللاعب تحت أزرار اختيار اللون
                hand_kb = []
                row = []
                for card_idx, h_card in enumerate(hand):
                    row.append(InlineKeyboardButton(text=h_card, callback_data="ignore"))
                    if len(row) == 3:
                        hand_kb.append(row)
                        row = []
                if row:
                    hand_kb.append(row)
                
                # دمج الكيبوردين
                full_kb = color_kb + hand_kb
                
                # رسالة مع أوراق اللاعب
                hand_text = "\n".join([f"• {h_card}" for h_card in hand])
                await c.message.edit_text(
                    f"🎨 اختر اللون الجديد:\n\n📋 أوراقك الحالية:\n{hand_text}", 
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=full_kb)
                )
                await state.set_state(GameStates.choosing_color)
                
                # تحديث كومة المرمي
                db_query("UPDATE rooms SET discard_pile = %s WHERE room_id = %s", 
                        (json.dumps(discard_pile), room_id), commit=True)
                
                # بدء تايمر اختيار اللون
                pending_color_data[room_id] = {
                    'card_played': card, 
                    'p_idx': p_idx, 
                    'prev_color': room['current_color']
                }
                
                # إرسال رسالة العد التنازلي لاختيار اللون
                cd_msg = await c.bot.send_message(
                    c.from_user.id, 
                    "⏳ باقي 20 ثانية لاختيار اللون\n🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢"
                )
                
                # حذف أي رسالة عداد سابقة
                old_cd = color_countdown_msgs.get(room_id)
                if old_cd:
                    try: await c.bot.delete_message(old_cd['chat_id'], old_cd['msg_id'])
                    except: pass
                
                color_countdown_msgs[room_id] = {
                    'bot': c.bot, 
                    'chat_id': c.from_user.id, 
                    'msg_id': cd_msg.message_id
                }
                color_timers[room_id] = asyncio.create_task(
                    color_timeout_2p(room_id, c.bot, c.from_user.id)
                )
                return
            else:
                # جوكرات السحب (🔥, 💧, 🌊)
                if "🔥" in card:  # جوكر +4 فقط هو الذي يحتاج تحدي
                    # تخزين معلومات الجوكر في الذاكرة
                    pending_color_data[room_id] = {
                        'card_played': card,
                        'p_idx': p_idx,
                        'opp_id': opp_id,
                        'p_name': p_name,
                        'type': 'challenge'
                    }
                    
                    # إرسال رسالة للخصم مع خياري التحدي والقبول
                    challenge_kb = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="🕵️‍♂️ أتحداك", callback_data=f"challenge_y_{room_id}"),
                            InlineKeyboardButton(text="✅ أقبل السحب", callback_data=f"challenge_n_{room_id}")
                        ]
                    ])
                    
                    await c.bot.send_message(
                        opp_id,
                        f"🔥 {p_name} لعب جوكر +4! هل تريد تحدي أنه كان لديه ورقة مناسبة؟",
                        reply_markup=challenge_kb
                    )
                    
                    # تحديث الغرفة مؤقتاً (بدون تطبيق العقوبة بعد)
                    db_query("UPDATE rooms SET top_card = %s, discard_pile = %s WHERE room_id = %s", 
                            (card, json.dumps(discard_pile), room_id), commit=True)
                    
                    # إعلام اللاعب بأنه بانتظار رد الخصم
                    await c.message.edit_text(
                        f"🔥 لعبت جوكر +4! بانتظار رد الخصم..."
                    )
                    return
                    
                else:  # جوكرات +1 و +2
                    next_turn = p_idx  # الدور يرجع للاعب نفسه
                    
                    # تحديث كومة المرمي
                    discard_pile.append(room['top_card'])
                    
                    # سحب الورقات حسب نوع الجوكر
                    deck = safe_load(room['deck'])
                    opp_hand = safe_load(players[opp_idx]['hand'])
                    drawn_cards = []
                    
                    if "💧" in card:  # جوكر +1
                        for _ in range(1):
                            if deck:
                                drawn_cards.append(deck.pop(0))
                                opp_hand.append(drawn_cards[-1])
                        # نستخدم لون عشوائي للجوكر
                        random_color = random.choice(['🔴', '🔵', '🟡', '🟢'])
                        top_card_value = f"{card} {random_color}"
                        current_color = random_color
                        msg_opp = f"💧 {p_name} لعب جوكر +1 وسحبك ورقة! 🎨 يمكنه الآن لعب أي لون"
                        msg_me = f"💧 لعبت جوكر +1 وسحبت الخصم ورقة! 🎨 يمكنك الآن لعب أي لون"
                        
                    elif "🌊" in card:  # جوكر +2
                        for _ in range(2):
                            if deck:
                                drawn_cards.append(deck.pop(0))
                                opp_hand.append(drawn_cards[-1])
                        # نستخدم لون عشوائي للجوكر
                        random_color = random.choice(['🔴', '🔵', '🟡', '🟢'])
                        top_card_value = f"{card} {random_color}"
                        current_color = random_color
                        msg_opp = f"🌊 {p_name} لعب جوكر +2 وسحبك ورقتين! 🎨 يمكنه الآن لعب أي لون"
                        msg_me = f"🌊 لعبت جوكر +2 وسحبت الخصم ورقتين! 🎨 يمكنك الآن لعب أي لون"
                    
                    # تحديث يد الخصم والكومة
                    if drawn_cards:
                        db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", 
                                (json.dumps(opp_hand), opp_id), commit=True)
                        db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", 
                                (json.dumps(deck), room_id), commit=True)
                    
                    # تحديث الغرفة - نضع لون عشوائي للجوكر
                    db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, discard_pile = %s WHERE room_id = %s", 
                            (top_card_value, current_color, next_turn, json.dumps(discard_pile), room_id), commit=True)
                    
                    # إضافة الرسائل
                    alerts[opp_id] = msg_opp
                    alerts[c.from_user.id] = msg_me
                    
                    # تحديث الواجهة
                    await refresh_ui_2p(room_id, c.bot, alerts)
                    return
        
        # أوراق الأكشن
        if "🚫" in card or "🔄" in card:
            next_turn = p_idx  # الدور يرجع للاعب نفسه
            alerts[opp_id] = f"🚫 {p_name} لعب ورقة أكشن والدور بقى عنده!"
            alerts[c.from_user.id] = f"🚫 لعبت {card} والدور رجع الك!"
        
        elif "+2" in card:
            next_turn = p_idx  # الدور يبقى عند اللاعب
            deck = safe_load(room['deck'])
            opp_hand = safe_load(players[opp_idx]['hand'])
            
            # سحب ورقتين للخصم
            drawn_cards = []
            for _ in range(2):
                if deck:
                    drawn_cards.append(deck.pop(0))
            
            if drawn_cards:
                opp_hand.extend(drawn_cards)
                db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", 
                        (json.dumps(opp_hand), opp_id), commit=True)
                db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", 
                        (json.dumps(deck), room_id), commit=True)
            
            alerts[opp_id] = f"⬆️2 {p_name} سحبك 2 والدور بقى عنده!"
            alerts[c.from_user.id] = f"⬆️2 سحبت الخصم ورقتين والدور رجع الك!"
        
        # تحديث الغرفة
        db_query("UPDATE rooms SET top_card = %s, current_color = %s, turn_index = %s, discard_pile = %s WHERE room_id = %s", 
                (card, card.split()[0], next_turn, json.dumps(discard_pile), room_id), commit=True)
        
        # تحديث الواجهة
        await refresh_ui_2p(room_id, c.bot, alerts)
        
    except Exception as e:
        print(f"Error in handle_play: {e}")
        await c.answer("⚠️ حدث خطأ", show_alert=True)


@router.callback_query(F.data.startswith("challenge_"))
async def handle_challenge_decision(c: types.CallbackQuery):
    try:
        data = c.data.split("_")
        decision = data[1]  # y أو n
        room_id = data[2]
        
        # جلب بيانات الجوكر
        pending = pending_color_data.get(room_id)
        if not pending:
            return await c.answer("⚠️ انتهت صلاحية هذا الطلب.", show_alert=True)
        
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data:
            return await c.answer("⚠️ الغرفة غير موجودة.", show_alert=True)
        
        room = room_data[0]
        players = get_ordered_players(room_id)
        p_idx = pending['p_idx']
        opp_id = pending['opp_id']
        p_name = pending['p_name']
        
        if c.from_user.id != opp_id:
            return await c.answer("❌ هذا القرار ليس لك!", show_alert=True)
        
        deck = safe_load(room['deck'])
        
        if decision == "n":  # قبل السحب
            # الخصم قبل السحب - يسحب 4 ورقات
            opp_hand = safe_load(players[(p_idx + 1) % 2]['hand'])
            drawn_cards = []
            for _ in range(4):
                if deck:
                    drawn_cards.append(deck.pop(0))
                    opp_hand.append(drawn_cards[-1])
            
            db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", 
                    (json.dumps(opp_hand), opp_id), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", 
                    (json.dumps(deck), room_id), commit=True)
            
            # تحديث current_color للسماح بلعب أي لون
            db_query("UPDATE rooms SET current_color = '🌈' WHERE room_id = %s", 
                    (room_id,), commit=True)
            
            await c.message.edit_text("✅ قبلت السحب! سحبت 4 ورقات.")
            await c.bot.send_message(players[p_idx]['user_id'], 
                                   f"✅ الخصم قبل السحب! دورك الآن ويمكنك لعب أي لون.")
            
            # تحديث turn_index للاعب الأول
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", 
                    (p_idx, room_id), commit=True)
            
        else:  # تحدي
            # فحص أوراق اللاعب الأول
            p_hand = safe_load(players[p_idx]['hand'])
            
            # هل كان لديه ورقة مناسبة (بدون احتساب الجوكرات)؟
            had_valid = False
            for card in p_hand:
                if any(x in card for x in ["🔥", "💧", "🌊", "🌈"]):
                    continue  # نتجاهل الجوكرات
                if check_validity(card, room['top_card'], room['current_color']):
                    had_valid = True
                    break
            
            if had_valid:
                # اللاعب غشاش - يعاقب بسحب 6 ورقات
                p_hand = safe_load(players[p_idx]['hand'])
                for _ in range(6):
                    if deck:
                        p_hand.append(deck.pop(0))
                
                db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", 
                        (json.dumps(p_hand), players[p_idx]['user_id']), commit=True)
                db_query("UPDATE rooms SET deck = %s, turn_index = %s WHERE room_id = %s", 
                        (json.dumps(deck), (p_idx + 1) % 2, room_id), commit=True)
                
                await c.message.edit_text("✅ نجح التحدي! الخصم غشاش وسحب 6 ورقات!")
                await c.bot.send_message(players[p_idx]['user_id'], 
                                       f"🕵️‍♂️ تم كشفك! سحبت 6 ورقات كعقوبة.")
            else:
                # التحدي فشل - الخصم يسحب 6 ورقات
                opp_hand = safe_load(players[(p_idx + 1) % 2]['hand'])
                for _ in range(6):
                    if deck:
                        opp_hand.append(deck.pop(0))
                
                db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", 
                        (json.dumps(opp_hand), opp_id), commit=True)
                db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", 
                        (json.dumps(deck), room_id), commit=True)
                
                # تحديث current_color للسماح بلعب أي لون
                db_query("UPDATE rooms SET current_color = '🌈' WHERE room_id = %s", 
                        (room_id,), commit=True)
                
                await c.message.edit_text("❌ فشل التحدي! اللاعب كان محقاً. سحبت 6 ورقات.")
                await c.bot.send_message(players[p_idx]['user_id'], 
                                       f"🎯 فشل تحدي الخصم! دورك الآن ويمكنك لعب أي لون.")
                
                # تحديث turn_index للاعب الأول
                db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", 
                        (p_idx, room_id), commit=True)
        
        # إلغاء البيانات المؤقتة
        cancel_color_timer(room_id)
        
        # تحديث الواجهة للجميع
        await refresh_ui_2p(room_id, c.bot)
        
    except Exception as e:
        print(f"Challenge decision error: {e}")
        await c.answer("⚠️ حدث خطأ في معالجة التحدي.", show_alert=True)


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

@router.callback_query(F.data.startswith("ex_"))
async def ask_exit(c: types.CallbackQuery):
    rid = c.data.split("_")[1]
    kb = [[InlineKeyboardButton(text="✅ نعم", callback_data=f"cf_ex_{rid}"), InlineKeyboardButton(text="❌ لا", callback_data=f"cn_ex_{rid}")]]
    await c.message.edit_text("🚪 هل أنت متأكد من الانسحاب؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("cf_ex_"))
async def confirm_exit(c: types.CallbackQuery):
    rid = c.data.split("_")[2]
    
    # مسح رسالة التأكيد
    try:
        await c.message.delete()
    except:
        pass
    
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
    
    # مسح رسالة التأكيد
    try:
        await c.message.delete()
    except:
        pass
    
    await refresh_ui_2p(rid, c.bot)

@router.callback_query(F.data.startswith("pass_"))
async def process_pass_turn(c: types.CallbackQuery):
    try:
        room_id = c.data.split("_")[1]
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data: return await c.answer("⚠️ الغرفة غير موجودة")
        room = room_data[0]
        
        players = get_ordered_players(room_id)
        curr_idx = room['turn_index']
        
        # التأكد أن اللاعب الذي ضغط هو صاحب الدور
        if c.from_user.id != players[curr_idx]['user_id']:
            return await c.answer("❌ مو دورك تمرر!", show_alert=True)
        
        # تمرير الدور للاعب التالي
        next_turn = (curr_idx + 1) % 2
        db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_turn, room_id), commit=True)
        
        p_name = players[curr_idx].get('player_name') or "لاعب"
        await c.answer("➡️ تم تمرير الدور")
        
        # تحديث الواجهة للجميع
        await refresh_ui_2p(room_id, c.bot, {
            players[curr_idx]['user_id']: "➡️ مررت دورك",
            players[next_turn]['user_id']: f"➡️ {p_name} مرر دوره، صار دورك الآن ✅"
        })
        
    except Exception as e:
        print(f"Pass Error: {e}")
