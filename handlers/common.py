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
    waiting_for_challenge = State()
    waiting_for_color_choice = State()

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
    join_order = len(current_players) + 1
    db_query("INSERT INTO room_players (room_id, user_id, player_name, join_order) VALUES (%s, %s, %s, %s)", 
             (code, message.from_user.id, user_data[0]['player_name'], join_order), commit=True)
    
    new_count, max_p = len(current_players) + 1, room[0]['max_players']
    await state.clear()
    
    # إرسال إشعار للمالك واللاعبين الجدد
    room_creator = db_query("SELECT creator_id FROM rooms WHERE room_id = %s", (code,))[0]['creator_id']
    try:
        await message.bot.send_message(room_creator, f"🎮 {user_data[0]['player_name']} انضم للغرفة ({new_count}/{max_p})")
    except: pass
    
    await message.answer(f"✅ دخلت الغرفة `{code}`. ({new_count}/{max_p})")
    
    # إذا اكتمل العدد
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
    
    # تسجيل التصويت
    user_id = c.from_user.id
    db_query("UPDATE room_players SET vote = %s WHERE room_id = %s AND user_id = %s", (mode, code, user_id), commit=True)
    
    # التحقق إذا اكتمل التصويت
    players = db_query("SELECT vote FROM room_players WHERE room_id = %s", (code,))
    votes = [p['vote'] for p in players if p['vote']]
    
    if len(votes) == len(players):
        # حساب الأغلبية
        team_votes = votes.count('team')
        solo_votes = votes.count('solo')
        
        final_mode = 'team' if team_votes > solo_votes else 'solo'
        
        db_query("UPDATE rooms SET game_mode = %s, status = 'playing' WHERE room_id = %s", (final_mode, code), commit=True)
        
        # إرسال نتيجة التصويت
        all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (code,))
        result_text = f"✅ اكتمل التصويت!\n👥 نظام فريق: {team_votes}\n👤 نظام فردي: {solo_votes}\n\nالنتيجة: {'👥 نظام فريق' if final_mode == 'team' else '👤 نظام فردي'}"
        
        for p in all_players:
            try: await c.bot.send_message(p['user_id'], result_text)
            except: pass
        
        await asyncio.sleep(2)
        await start_private_game(code, c.bot)
    else:
        await c.answer("✅ تم تسجيل صوتك! انتظر الآخرين...", show_alert=False)

async def create_uno_deck():
    """إنشاء مجموعة أونو كاملة"""
    colors = ['🔴', '🔵', '🟡', '🟢']
    numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    actions = ['🚫', '🔄', '➕2']
    
    deck = []
    
    # أوراق الأرقام (0 مرة واحدة، 1-9 مرتين)
    for color in colors:
        deck.append(f"{color} 0")
        for number in numbers[1:]:
            deck.append(f"{color} {number}")
            deck.append(f"{color} {number}")
    
    # أوراق الأكشن (مرتين لكل لون)
    for color in colors:
        for action in actions:
            deck.append(f"{color} {action}")
            deck.append(f"{color} {action}")
    
    # أوراق الجوكر
    for _ in range(4):
        deck.append("🌈 جوكر +4")
        deck.append("🌈 جوكر ملون")
    
    random.shuffle(deck)
    return deck

async def start_private_game(room_id, bot):
    """بدء اللعبة"""
    # إنشاء المجموعة
    deck = await create_uno_deck()
    
    # الحصول على معلومات اللاعبين
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    
    # توزيع 7 أوراق لكل لاعب
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s, points = 0 WHERE room_id = %s AND user_id = %s", 
                (json.dumps(hand), room_id, p['user_id']), commit=True)
    
    # وضع الورقة الأولى
    top_card = deck.pop()
    
    # التأكد أن الورقة الأولى ليست جوكر أو أكشن
    while '🌈' in top_card or '🚫' in top_card or '🔄' in top_card or '➕' in top_card:
        deck.append(top_card)
        random.shuffle(deck)
        top_card = deck.pop()
    
    # تحديد الفرق إذا كان وضع فريق
    if room['game_mode'] == 'team':
        await assign_teams(room_id)
    
    # حفظ حالة اللعبة
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = 0, direction = 1, current_color = %s WHERE room_id = %s", 
             (top_card, json.dumps(deck), top_card.split()[0], room_id), commit=True)
    
    # إرسال بداية اللعبة للجميع
    await announce_game_start(room_id, bot, room['game_mode'])
    
    # تحديث واجهة اللعبة
    await refresh_game_ui(room_id, bot)

async def assign_teams(room_id):
    """توزيع اللاعبين على فرق"""
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    for i, player in enumerate(players):
        # الفريق الأول: 1, 3, 5, 7, 9
        # الفريق الثاني: 2, 4, 6, 8, 10
        team = 1 if (i + 1) % 2 == 1 else 2
        db_query("UPDATE room_players SET team = %s WHERE room_id = %s AND user_id = %s", 
                (team, room_id, player['user_id']), commit=True)

async def announce_game_start(room_id, bot, game_mode):
    """إعلان بداية اللعبة"""
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT player_name, team FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    start_text = f"🎮 **بدأت اللعبة!**\n"
    start_text += f"📊 السقف: {room['score_limit']} نقطة\n"
    start_text += f"🎯 النمط: {'👥 فريق' if game_mode == 'team' else '👤 فردي'}\n\n"
    
    if game_mode == 'team':
        start_text += "**الفرق:**\n"
        team1 = [p['player_name'] for p in players if p['team'] == 1]
        team2 = [p['player_name'] for p in players if p['team'] == 2]
        start_text += f"🔴 الفريق 1: {', '.join(team1)}\n"
        start_text += f"🔵 الفريق 2: {', '.join(team2)}\n\n"
    else:
        start_text += "**اللاعبون:**\n"
        for i, p in enumerate(players):
            start_text += f"{i+1}. {p['player_name']}\n"
    
    start_text += f"\n🎴 الورقة الأولى: {room['top_card']}"
    
    for player in players:
        try:
            await bot.send_message(player['user_id'], start_text)
        except:
            pass

async def refresh_game_ui(room_id, bot):
    """تحديث واجهة اللعبة"""
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    turn_idx = room['turn_index']
    top_card = room['top_card']
    current_color = room.get('current_color', top_card.split()[0])
    
    # إنشاء نص حالة اللعبة
    status_text = f"🃏 **الورقة الحالية:** [ {top_card} ]\n"
    status_text += f"🎨 **اللون المطلوب:** {current_color}\n\n"
    status_text += f"👥 **اللاعبين:**\n"
    
    for i, p in enumerate(players):
        star = "🌟" if i == turn_idx else "⏳"
        team_info = f"| فريق {p['team']}" if room['game_mode'] == 'team' and p.get('team') else ""
        status_text += f"{star} {p['player_name'][:10]:<10} | 🃏 {len(json.loads(p['hand']))} {team_info}\n"
    
    status_text += f"\n🎯 السقف: {room['score_limit']} | الاتجاه: {'⏩' if room['direction'] == 1 else '⏪'}"
    
    # تحديث واجهة كل لاعب
    for p in players:
        # مسح الرسالة السابقة إن وجدت
        if p.get('last_msg_id'):
            try:
                await bot.delete_message(p['user_id'], p['last_msg_id'])
            except:
                pass
        
        hand = json.loads(p['hand'])
        kb = []
        row = []
        
        # إذا كان الدور له، نعرض أزرار اللعب
        if i == turn_idx:
            # إضافة زر "سحب"
            kb.append([InlineKeyboardButton(text="🃏 سحب ورقة", callback_data=f"draw_{room_id}")])
            
            # عرض الورق
            for idx, card in enumerate(hand):
                # التحقق إذا كانت الورقة قابلة للعب
                if await is_card_playable(card, top_card, current_color):
                    row.append(InlineKeyboardButton(text=card, callback_data=f"play_{room_id}_{idx}"))
                    if len(row) == 2:
                        kb.append(row)
                        row = []
            
            if row:
                kb.append(row)
        else:
            kb.append([InlineKeyboardButton(text="⏳ انتظر دورك...", callback_data="wait")])
        
        # إرسال الرسالة الجديدة
        msg = await bot.send_message(p['user_id'], status_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        
        # حفظ معرف الرسالة
        db_query("UPDATE room_players SET last_msg_id = %s WHERE room_id = %s AND user_id = %s", 
                (msg.message_id, room_id, p['user_id']), commit=True)

async def is_card_playable(card, top_card, current_color):
    """التحقق إذا كانت الورقة قابلة للعب"""
    # الجوكر يمكن لعبه دائماً
    if '🌈' in card:
        return True
    
    # تقسيم الورقة الحالية والورقة المراد لعبها
    top_parts = top_card.split()
    card_parts = card.split()
    
    # إذا كان اللون متطابق
    if card_parts[0] == current_color:
        return True
    
    # إذا كان الرقم/الأكشن متطابق (وليس جوكر)
    if len(top_parts) > 1 and len(card_parts) > 1:
        if card_parts[1] == top_parts[1] and '🌈' not in card:
            return True
    
    return False

@router.callback_query(F.data.startswith("play_"))
async def play_card(c: types.CallbackQuery, state: FSMContext):
    """لعب ورقة"""
    _, room_id, idx = c.data.split("_")
    idx, user_id = int(idx), c.from_user.id
    
    # الحصول على معلومات الغرفة واللاعبين
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players_list = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    # التأكد أن الدور عليه
    if players_list[room['turn_index']]['user_id'] != user_id:
        return await c.answer("⏳ مو دورك! انتظر النجمة 🌟", show_alert=True)
    
    player_hand = json.loads(players_list[room['turn_index']]['hand'])
    played_card = player_hand[idx]
    
    # التحقق من صحة الورقة
    if not await is_card_playable(played_card, room['top_card'], room['current_color']):
        return await c.answer(f"❌ ما ترهم على {room['top_card']} (اللون: {room['current_color']})", show_alert=True)
    
    # إذا كانت ورقة جوكر، نحتاج لاختيار لون
    if '🌈' in played_card:
        await state.update_data(room_id=room_id, card_idx=idx, player_index=room['turn_index'])
        await state.set_state(GameStates.waiting_for_color_choice)
        
        colors_kb = [
            [InlineKeyboardButton(text="🔴 أحمر", callback_data=f"color_🔴_{room_id}"),
             InlineKeyboardButton(text="🔵 أزرق", callback_data=f"color_🔵_{room_id}")],
            [InlineKeyboardButton(text="🟡 أصفر", callback_data=f"color_🟡_{room_id}"),
             InlineKeyboardButton(text="🟢 أخضر", callback_data=f"color_🟢_{room_id}")]
        ]
        
        # إرسال رسالة خاصة للاعب لاختيار اللون
        await c.message.delete()
        await c.bot.send_message(
            user_id,
            "🎨 اختر لون للجوكر:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=colors_kb)
        )
        return
    
    # لعب الورقة العادية
    await process_normal_card(room_id, idx, played_card, room['turn_index'], c.bot, state)

async def process_normal_card(room_id, card_idx, played_card, player_index, bot, state):
    """معالجة لعب ورقة عادية"""
    # إزالة الورقة من يد اللاعب
    players_list = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    player_hand = json.loads(players_list[player_index]['hand'])
    player_hand.pop(card_idx)
    
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
             (json.dumps(player_hand), room_id, players_list[player_index]['user_id']), commit=True)
    
    # التحقق من الفوز
    if len(player_hand) == 0:
        await handle_win(room_id, player_index, bot)
        return
    
    # تحديث الورقة الحالية واللون
    card_color = played_card.split()[0]
    db_query("UPDATE rooms SET top_card = %s, current_color = %s WHERE room_id = %s", 
             (played_card, card_color, room_id), commit=True)
    
    # تطبيق تأثيرات الأكشن
    await apply_card_effects(room_id, played_card, player_index, bot, state)
    
    # تحديث الواجهة
    await refresh_game_ui(room_id, bot)

@router.callback_query(F.data.startswith("color_"))
async def choose_color(c: types.CallbackQuery, state: FSMContext):
    """اختيار لون للجوكر"""
    color, _, room_id = c.data.split("_")
    data = await state.get_data()
    
    if not data.get('room_id') == room_id:
        await c.answer("❌ انتهت الجلسة", show_alert=True)
        return
    
    await state.clear()
    
    # الحصول على معلومات اللاعب والورقة
    players_list = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    player_index = data['player_index']
    card_idx = data['card_idx']
    
    player_hand = json.loads(players_list[player_index]['hand'])
    played_card = player_hand[card_idx]
    
    # إزالة الورقة من يد اللاعب
    player_hand.pop(card_idx)
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
             (json.dumps(player_hand), room_id, players_list[player_index]['user_id']), commit=True)
    
    # التحقق من الفوز
    if len(player_hand) == 0:
        await handle_win(room_id, player_index, c.bot)
        return
    
    # إذا كانت جوكر +4، نحتاج لتفعيل تحدٍ
    if 'جوكر +4' in played_card:
        # حفظ معلومات التحدي
        next_index = await get_next_player_index(room_id, player_index)
        next_player_id = players_list[next_index]['user_id']
        
        db_query("UPDATE rooms SET challenge_active = TRUE, challenge_card = %s, challenger_index = %s, target_index = %s, chosen_color = %s WHERE room_id = %s", 
                 (played_card, player_index, next_index, color, room_id), commit=True)
        
        # إرسال طلب التحدي للاعب التالي
        kb = [
            [InlineKeyboardButton(text="⚔️ أتحدى!", callback_data=f"challenge_accept_{room_id}"),
             InlineKeyboardButton(text="🏳️ استسلم", callback_data=f"challenge_decline_{room_id}")]
        ]
        
        challenger_name = players_list[player_index]['player_name']
        try:
            await c.bot.send_message(
                next_player_id,
                f"⚠️ **تحدي جوكر +4**\n\n{challenger_name} لعب جوكر +4 واختار اللون {color}\n\nهل تشك أنه يغش ويستطيع لعب ورقة أخرى؟\n\n✅ إذا كنت تشك → أتحدى (إذا كان يغش يسحب 6، وإلا تسحب 6 أنت)\n❌ إذا لا → استسلم وتسحب 4 فقط",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
            )
        except:
            pass
        
        # تحديث الواجهة مع إشعار
        room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
        new_top_card = f"🌈 جوكر +4 → {color}"
        db_query("UPDATE rooms SET top_card = %s, current_color = %s WHERE room_id = %s", 
                 (new_top_card, color, room_id), commit=True)
        
        # إرسال إشعار للجميع
        all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (room_id,))
        for p in all_players:
            if p['user_id'] != next_player_id:
                try:
                    await c.bot.send_message(p['user_id'], f"🎴 {challenger_name} لعب جوكر +4 واختار اللون {color}\n⚔️ في انتظار تحدي {players_list[next_index]['player_name']}...")
                except:
                    pass
        
        await refresh_game_ui(room_id, c.bot)
        return
    
    # إذا كانت جوكر عادي
    elif 'جوكر ملون' in played_card:
        # جوكر ملون يحتاج لتحدي أيضاً
        next_index = await get_next_player_index(room_id, player_index)
        next_player_id = players_list[next_index]['user_id']
        
        db_query("UPDATE rooms SET challenge_active = TRUE, challenge_card = %s, challenger_index = %s, target_index = %s, chosen_color = %s WHERE room_id = %s", 
                 (played_card, player_index, next_index, color, room_id), commit=True)
        
        # إرسال طلب التحدي
        kb = [
            [InlineKeyboardButton(text="⚔️ أتحدى!", callback_data=f"challenge_accept_{room_id}"),
             InlineKeyboardButton(text="🏳️ استسلم", callback_data=f"challenge_decline_{room_id}")]
        ]
        
        challenger_name = players_list[player_index]['player_name']
        try:
            await c.bot.send_message(
                next_player_id,
                f"⚠️ **تحدي جوكر ملون**\n\n{challenger_name} لعب جوكر ملون واختار اللون {color}\n\nهل تشك أنه يغش؟\n\n✅ إذا كنت تشك → أتحدى (إذا كان يغش يسحب 3، وإلا تسحب 3 أنت)\n❌ إذا لا → استسلم وتلعب باللون {color}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
            )
        except:
            pass
        
        # تحديث الواجهة
        new_top_card = f"🌈 جوكر ملون → {color}"
        db_query("UPDATE rooms SET top_card = %s, current_color = %s WHERE room_id = %s", 
                 (new_top_card, color, room_id), commit=True)
        
        await refresh_game_ui(room_id, c.bot)
        return
    
    # تحديث اللعبة وتطبيق التأثيرات
    new_top_card = f"{played_card} → {color}"
    db_query("UPDATE rooms SET top_card = %s, current_color = %s WHERE room_id = %s", 
             (new_top_card, color, room_id), commit=True)
    
    await apply_card_effects(room_id, played_card, player_index, c.bot, state)
    await refresh_game_ui(room_id, c.bot)

@router.callback_query(F.data.startswith("challenge_"))
async def handle_challenge(c: types.CallbackQuery):
    """معالجة التحدي"""
    action, _, room_id = c.data.split("_")
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    
    if not room['challenge_active']:
        await c.answer("❌ انتهى التحدي", show_alert=True)
        return
    
    players_list = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    challenger = players_list[room['challenger_index']]
    target = players_list[room['target_index']]
    
    if c.from_user.id != target['user_id']:
        await c.answer("❌ هذا التحدي ليس لك!", show_alert=True)
        return
    
    if action == 'accept':
        # التحقق إذا كان المتحدي يغش
        challenger_hand = json.loads(challenger['hand'])
        top_card_before = db_query("SELECT top_card FROM rooms WHERE room_id = %s", (room_id,))[0]['top_card']
        
        # التحقق إذا كان لديه ورقة مناسبة
        has_playable = False
        for card in challenger_hand:
            card_color = card.split()[0]
            if card_color == room['current_color'] and '🌈' not in card:
                has_playable = True
                break
        
        if has_playable:
            # المتحدي كان يغش
            penalty = 6 if '+4' in room['challenge_card'] else 3
            await apply_draw_penalty(room_id, room['challenger_index'], penalty, c.bot)
            
            # إرجاع الجوكر ليد المتحدي
            challenger_hand.append(room['challenge_card'])
            db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
                     (json.dumps(challenger_hand), room_id, challenger['user_id']), commit=True)
            
            # إبقاء الدور عند المتحدي
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (room['challenger_index'], room_id), commit=True)
            
            result_msg = f"⚔️ {target['player_name']} تحدى ونجح!\n{challenger['player_name']} كان يغش وسحب {penalty} أوراق!"
        else:
            # المتحدي لم يغش
            penalty = 6 if '+4' in room['challenge_card'] else 3
            await apply_draw_penalty(room_id, room['target_index'], penalty, c.bot)
            
            # نقل الدور للاعب بعد الهدف
            next_index = await get_next_player_index(room_id, room['target_index'])
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_index, room_id), commit=True)
            
            result_msg = f"⚔️ {target['player_name']} تحدى وفشل!\nسحب {penalty} أوراق!"
    
    else:  # decline
        if '+4' in room['challenge_card']:
            penalty = 4
            await apply_draw_penalty(room_id, room['target_index'], penalty, c.bot)
            
            # نقل الدور للاعب بعد الهدف
            next_index = await get_next_player_index(room_id, room['target_index'])
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_index, room_id), commit=True)
            
            result_msg = f"🏳️ {target['player_name']} استسلم وسحب 4 أوراق"
        else:
            # جوكر ملون - الهدف يلعب باللون المختار
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (room['target_index'], room_id), commit=True)
            result_msg = f"🎨 {target['player_name']} يقبل اللون {room['chosen_color']}"
    
    # إرسال نتيجة التحدي للجميع
    all_players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (room_id,))
    for p in all_players:
        try:
            await c.bot.send_message(p['user_id'], result_msg)
        except:
            pass
    
    # إلغاء التحدي
    db_query("UPDATE rooms SET challenge_active = FALSE, challenge_card = NULL, challenger_index = NULL, target_index = NULL WHERE room_id = %s", 
             (room_id,), commit=True)
    
    await refresh_game_ui(room_id, c.bot)

async def apply_card_effects(room_id, played_card, player_index, bot, state):
    """تطبيق تأثيرات الورقة"""
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
    if not room:
        return
    room = room[0]
    
    direction = room['direction']
    max_players = room['max_players']
    
    # حساب المؤشر التالي
    next_index = (player_index + direction) % max_players
    if next_index < 0:
        next_index = max_players - 1
    
    skip_next = False
    draw_penalty = 0
    
    # تحديد التأثير
    if '🚫' in played_card:
        skip_next = True
        await send_action_notice(room_id, f"⏭️ تخطى دور اللاعب التالي", bot)
    
    elif '🔄' in played_card:
        # عكس الاتجاه
        new_direction = -direction
        db_query("UPDATE rooms SET direction = %s WHERE room_id = %s", (new_direction, room_id), commit=True)
        
        # في حالة لاعبين فقط، يعمل كـ Skip
        if max_players == 2:
            skip_next = True
        
        direction_text = "⏪" if new_direction == -1 else "⏩"
        await send_action_notice(room_id, f"🔄 تم عكس الاتجاه {direction_text}", bot)
    
    elif '➕2' in played_card:
        draw_penalty = 2
        await send_action_notice(room_id, f"➕2 اللاعب التالي يسحب ورقتين", bot)
    
    # تطبيق العقوبات
    if draw_penalty > 0:
        await apply_draw_penalty(room_id, next_index, draw_penalty, bot)
        next_index = await get_next_player_index(room_id, next_index)
    
    if skip_next:
        next_index = await get_next_player_index(room_id, next_index)
    
    # تحديث الدور
    db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_index, room_id), commit=True)
    
    # التحقق التلقائي إذا كان اللاعب القادم لا يملك أوراق مناسبة
    await auto_check_next_player(room_id, next_index, bot)

async def apply_draw_penalty(room_id, player_idx, count, bot):
    """تطبيق عقوبة السحب"""
    room = db_query("SELECT deck FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    target = players[player_idx]
    
    deck = json.loads(room['deck'])
    hand = json.loads(target['hand'])
    
    # إذا لم تكن هناك أوراق كافية، نخلط الورق الملقاة
    if len(deck) < count:
        # هنا يمكن إضافة منطق إعادة خلط الورق الملقاة
        pass
    
    for _ in range(count):
        if deck:
            hand.append(deck.pop(0))
        else:
            break
    
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
             (json.dumps(hand), room_id, target['user_id']), commit=True)
    db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
    
    try:
        await bot.send_message(target['user_id'], f"⚠️ سحبت {count} أوراق عقوبة!")
    except:
        pass

async def auto_check_next_player(room_id, next_idx, bot):
    """فحص تلقائي إذا كان اللاعب القادم يحتاج سحب"""
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    next_player = players[next_idx]
    hand = json.loads(next_player['hand'])
    top_card = room['top_card']
    current_color = room['current_color']
    
    # التحقق إذا كان لديه ورقة قابلة للعب
    can_play = any(await is_card_playable(card, top_card, current_color) for card in hand)
    
    if not can_play:
        deck = json.loads(room['deck'])
        if deck:
            new_card = deck.pop(0)
            hand.append(new_card)
            
            db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
                    (json.dumps(hand), room_id, next_player['user_id']), commit=True)
            db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
            
            try:
                await bot.send_message(next_player['user_id'], f"📥 سحبت آلياً: {new_card}")
            except:
                pass
            
            # فحص إذا الورقة الجديدة قابلة للعب
            if await is_card_playable(new_card, top_card, current_color):
                # إذا كانت قابلة للعب، يبقى الدور عليه
                db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_idx, room_id), commit=True)
            else:
                # إذا لم تكن قابلة للعب، ننتقل للاعب التالي
                final_turn = await get_next_player_index(room_id, next_idx)
                db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (final_turn, room_id), commit=True)
                await auto_check_next_player(room_id, final_turn, bot)
                return
    
    await refresh_game_ui(room_id, bot)

async def get_next_player_index(room_id, current_index):
    """الحصول على مؤشر اللاعب التالي"""
    room = db_query("SELECT direction, max_players FROM rooms WHERE room_id = %s", (room_id,))[0]
    direction = room['direction']
    max_players = room['max_players']
    
    next_index = (current_index + direction) % max_players
    if next_index < 0:
        next_index = max_players - 1
    
    return next_index

async def send_action_notice(room_id, message, bot):
    """إرسال إشعار تأثير لجميع اللاعبين"""
    players = db_query("SELECT user_id FROM room_players WHERE room_id = %s", (room_id,))
    
    for p in players:
        try:
            await bot.send_message(p['user_id'], message)
        except:
            pass

async def handle_win(room_id, winner_index, bot):
    """معالجة فوز لاعب"""
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    
    winner = players[winner_index]
    
    # حساب النقاط
    total_points = 0
    result_text = f"🏆 **{winner['player_name']} فاز بالجولة!**\n\n"
    result_text += "📊 **نقاط اللاعبين:**\n"
    
    for p in players:
        if p['user_id'] == winner['user_id']:
            continue
        
        hand_points = calculate_hand_points(p['hand'])
        total_points += hand_points
        
        # إضافة النقاط للفائز
        db_query("UPDATE room_players SET points = points + %s WHERE room_id = %s AND user_id = %s", 
                (hand_points, room_id, winner['user_id']), commit=True)
        
        result_text += f"• {p['player_name']}: +{hand_points} نقطة\n"
    
    # الحصول على النقاط الإجمالية للفائز
    winner_total = db_query("SELECT points FROM room_players WHERE room_id = %s AND user_id = %s", 
                           (room_id, winner['user_id']))[0]['points']
    
    result_text += f"\n💰 **إجمالي نقاط {winner['player_name']}: {winner_total}**"
    result_text += f"\n🎯 **السقف: {room['score_limit']}**"
    
    # التحقق إذا وصل الفائز للسقف
    if winner_total >= room['score_limit']:
        await end_game(room_id, winner_index, bot)
        return
    
    # إذا لم يصل للسقف، نبدأ جولة جديدة
    result_text += "\n\n↪️ بداية جولة جديدة..."
    
    # إرسال النتائج للجميع
    for p in players:
        try:
            await bot.send_message(p['user_id'], result_text)
        except:
            pass
    
    await asyncio.sleep(3)
    
    # بدء جولة جديدة
    await start_new_round(room_id, bot)

async def start_new_round(room_id, bot):
    """بدء جولة جديدة"""
    # إعادة تعيين الأيدي مع الحفاظ على النقاط
    deck = await create_uno_deck()
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    
    # توزيع أوراق جديدة
    for p in players:
        hand = [deck.pop() for _ in range(7)]
        db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
                (json.dumps(hand), room_id, p['user_id']), commit=True)
    
    # وضع الورقة الأولى
    top_card = deck.pop()
    while '🌈' in top_card or '🚫' in top_card or '🔄' in top_card or '➕' in top_card:
        deck.append(top_card)
        random.shuffle(deck)
        top_card = deck.pop()
    
    # تحديد الدور (الفائز بالجولة السابقة يبدأ)
    winner_order = db_query("SELECT join_order FROM room_players WHERE room_id = %s ORDER BY points DESC LIMIT 1", (room_id,))
    if winner_order:
        winner_index = next((i for i, p in enumerate(players) if p['join_order'] == winner_order[0]['join_order']), 0)
    else:
        winner_index = 0
    
    # حفظ حالة اللعبة
    db_query("UPDATE rooms SET top_card = %s, deck = %s, turn_index = %s, direction = 1, current_color = %s, challenge_active = FALSE WHERE room_id = %s", 
             (top_card, json.dumps(deck), winner_index, top_card.split()[0], room_id), commit=True)
    
    # تحديث الواجهة
    await refresh_game_ui(room_id, bot)

async def end_game(room_id, winner_index, bot):
    """إنهاء اللعبة نهائياً"""
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    
    winner = players[winner_index]
    
    # حساب النتائج النهائية
    final_text = "🏁 **انتهت اللعبة! النتائج النهائية:**\n\n"
    
    # إذا كان وضع فريق، نعرض الفريق الفائز
    if room['game_mode'] == 'team':
        winner_team = winner['team']
        team_players = [p for p in players if p['team'] == winner_team]
        team_names = ', '.join([p['player_name'] for p in team_players])
        
        final_text += f"🏆 **الفريق الفائز (فريق {winner_team}):** {team_names}\n\n"
    
    final_text += "📊 **النقاط النهائية:**\n"
    
    for p in players:
        points = calculate_hand_points(p['hand'])
        total_points = p['points'] + points
        
        # تحديث النقاط في قاعدة البيانات الرئيسية
        if room['game_mode'] == 'team' and p['team'] == winner['team']:
            # الفريق الفائز يحصل على نقاط
            db_query("UPDATE users SET online_points = online_points + %s WHERE user_id = %s", 
                    (total_points, p['user_id']), commit=True)
        
        status = "🏆 فائز" if p['user_id'] == winner['user_id'] else f"❌ خاسر"
        final_text += f"{status} | **{p['player_name']}**: {total_points} نقطة\n"
    
    # إرسال النتائج للجميع
    for p in players:
        try:
            # مسح رسائل اللعبة
            if p.get('last_msg_id'):
                await bot.delete_message(p['user_id'], p['last_msg_id'])
            
            await bot.send_message(p['user_id'], final_text)
        except:
            pass
    
    # تحديث حالة الغرفة
    db_query("UPDATE rooms SET status = 'finished' WHERE room_id = %s", (room_id,), commit=True)
    
    # حذف بيانات اللاعبين من الغرفة
    db_query("DELETE FROM room_players WHERE room_id = %s", (room_id,), commit=True)

@router.callback_query(F.data.startswith("draw_"))
async def draw_card(c: types.CallbackQuery):
    """سحب ورقة"""
    _, room_id = c.data.split("_")
    user_id = c.from_user.id
    
    room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))[0]
    players = db_query("SELECT * FROM room_players WHERE room_id = %s ORDER BY join_order", (room_id,))
    
    # التأكد أن الدور عليه
    if players[room['turn_index']]['user_id'] != user_id:
        await c.answer("⏳ مو دورك!", show_alert=True)
        return
    
    # سحب ورقة
    deck = json.loads(room['deck'])
    if not deck:
        await c.answer("❌ لا توجد أوراق في المجموعة", show_alert=True)
        return
    
    player_index = room['turn_index']
    player_hand = json.loads(players[player_index]['hand'])
    new_card = deck.pop(0)
    player_hand.append(new_card)
    
    # تحديث البيانات
    db_query("UPDATE room_players SET hand = %s WHERE room_id = %s AND user_id = %s", 
             (json.dumps(player_hand), room_id, user_id), commit=True)
    db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
    
    # التحقق إذا كانت الورقة قابلة للعب
    if await is_card_playable(new_card, room['top_card'], room['current_color']):
        # إذا كانت قابلة للعب، يبقى الدور عليه
        await c.answer(f"📥 سحبت: {new_card} - يمكنك لعبها الآن!", show_alert=False)
    else:
        # إذا لم تكن قابلة للعب، ننتقل للاعب التالي
        next_index = await get_next_player_index(room_id, player_index)
        db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_index, room_id), commit=True)
        await c.answer(f"📥 سحبت: {new_card} - الدور ينتقل للاعب التالي", show_alert=False)
    
    await refresh_game_ui(room_id, c.bot)

def calculate_hand_points(hand_json):
    """حساب نقاط اليد"""
    hand = json.loads(hand_json)
    total = 0
    
    for card in hand:
        if any(x in card for x in ['🚫', '🔄', '➕2']):
            total += 20
        elif any(x in card for x in ['🌈', '➕4']):
            total += 50
        else:
            try:
                # استخراج الرقم من الورقة
                parts = card.split()
                if len(parts) > 1:
                    num = int(parts[1])
                    total += num
            except:
                total += 0  # في حالة وجود خطأ
    
    return total

@router.callback_query(F.data == "room_create")
async def room_create_start(c: types.CallbackQuery):
    kb, row = [], []
    for i in range(2, 11):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"setp_{i}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    await c.message.edit_text("👥 حدد عدد اللاعبين (2-10):", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("setp_"))
async def set_room_players(c: types.CallbackQuery):
    num = c.data.split("_")[1]
    scores = [100, 150, 200, 250, 300, 350, 400, 450, 500]
    kb, row = [], []
    
    for s in scores:
        row.append(InlineKeyboardButton(text=str(s), callback_data=f"sets_{num}_{s}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    
    if row:
        kb.append(row)
    
    await c.message.edit_text(f"🎯 لاعبين: {num}. حدد السقف:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sets_"))
async def finalize_room_creation(c: types.CallbackQuery):
    _, p_count, s_limit = c.data.split("_")
    code = generate_room_code()
    
    u_name = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))[0]['player_name']
    
    # إنشاء الغرفة
    db_query("""
        INSERT INTO rooms (room_id, creator_id, max_players, score_limit, status, game_mode, direction) 
        VALUES (%s, %s, %s, %s, 'waiting', 'solo', 1)
    """, (code, c.from_user.id, int(p_count), int(s_limit)), commit=True)
    
    # إضافة المالك كأول لاعب
    db_query("""
        INSERT INTO room_players (room_id, user_id, player_name, join_order) 
        VALUES (%s, %s, %s, 1)
    """, (code, c.from_user.id, u_name), commit=True)
    
    await c.message.edit_text(
        f"✅ **تم إنشاء الغرفة!**\n\n"
        f"🔑 **كود الغرفة:** `{code}`\n"
        f"👥 **عدد اللاعبين:** {p_count}\n"
        f"🎯 **السقف:** {s_limit}\n\n"
        f"📤 شارك الكود مع أصدقائك!"
    )
    
    # إرسال الكود كرسالة منفصلة لسهولة النسخ
    await c.message.answer(f"`{code}`")

@router.callback_query(F.data == "home")
async def go_home(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = db_query("SELECT player_name FROM users WHERE user_id = %s", (c.from_user.id,))
    await show_main_menu(c.message, user[0]['player_name'])
