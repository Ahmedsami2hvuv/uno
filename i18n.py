from database import db_query

_cache = {}

def get_lang(user_id):
    if user_id in _cache:
        return _cache[user_id]
    row = db_query("SELECT language FROM users WHERE user_id = %s", (user_id,))
    lang = row[0]['language'] if row and row[0].get('language') else 'ar'
    _cache[user_id] = lang
    return lang

def set_lang(user_id, lang):
    _cache[user_id] = lang

def t(user_id, key, **kwargs):
    lang = get_lang(user_id)
    text = TEXTS.get(key, {}).get(lang, key)
    if kwargs:
        text = text.format(**kwargs)
    return text

TEXTS = {
    "choose_lang": {
        "ar": "🌍 اختر لغتك / Choose your language:",
        "en": "🌍 Choose your language / اختر لغتك:",
    },
    "welcome_new": {
        "ar": "🎮 أهلاً بك في بوت UNO!\n\nاختر:",
        "en": "🎮 Welcome to UNO Bot!\n\nChoose:",
    },
    "btn_register": {
        "ar": "📝 إنشاء حساب",
        "en": "📝 Create Account",
    },
    "btn_login": {
        "ar": "🔑 تسجيل دخول",
        "en": "🔑 Login",
    },
    "ask_name": {
        "ar": "📝 أرسل الاسم الذي تريده:",
        "en": "📝 Send the name you want:",
    },
    "name_too_short": {
        "ar": "❌ الاسم قصير جداً، أرسل اسماً من حرفين على الأقل:",
        "en": "❌ Name too short, send a name with at least 2 characters:",
    },
    "name_too_long": {
        "ar": "❌ الاسم طويل جداً، أرسل اسماً أقصر (20 حرف كحد أقصى):",
        "en": "❌ Name too long, send a shorter name (max 20 characters):",
    },
    "name_taken": {
        "ar": "❌ هذا الاسم مستخدم، اختر اسماً آخر:",
        "en": "❌ This name is taken, choose another name:",
    },
    "ask_password": {
        "ar": "🔑 أرسل الرمز السري (4 أحرف أو أكثر):",
        "en": "🔑 Send your secret code (4+ characters):",
    },
    "password_too_short": {
        "ar": "❌ الرمز السري قصير جداً (4 أحرف على الأقل):",
        "en": "❌ Secret code too short (at least 4 characters):",
    },
    "register_success": {
        "ar": "✅ تم إنشاء حسابك بنجاح!\n\n📛 الاسم: {name}\n🔑 الرمز السري: {password}\n\n⚠️ احفظ الرمز السري! تحتاجه لتسجيل الدخول.",
        "en": "✅ Account created successfully!\n\n📛 Name: {name}\n🔑 Secret code: {password}\n\n⚠️ Save your secret code! You need it to login.",
    },
    "login_ask_name": {
        "ar": "📝 أرسل اسمك:",
        "en": "📝 Send your name:",
    },
    "login_ask_password": {
        "ar": "🔑 أرسل الرمز السري:",
        "en": "🔑 Send your secret code:",
    },
    "login_fail": {
        "ar": "❌ الاسم أو الرمز السري غلط! حاول مرة ثانية.\n\nأرسل اسمك:",
        "en": "❌ Wrong name or secret code! Try again.\n\nSend your name:",
    },
    "login_success": {
        "ar": "✅ تم تسجيل الدخول بنجاح! أهلاً {name}!",
        "en": "✅ Login successful! Welcome {name}!",
    },
    "complete_profile": {
        "ar": "👋 أهلاً {name}!\n\n⚠️ كمّل ملفك الشخصي أولاً عشان تقدر تلعب.\n\nهل اسمك {name} صحيح؟",
        "en": "👋 Hello {name}!\n\n⚠️ Complete your profile first to play.\n\nIs your name {name} correct?",
    },
    "btn_yes_name": {
        "ar": "✅ نعم، اسمي صحيح",
        "en": "✅ Yes, my name is correct",
    },
    "btn_edit_name": {
        "ar": "✏️ تعديل الاسم",
        "en": "✏️ Edit name",
    },
    "profile_complete": {
        "ar": "✅ تم تكميل ملفك الشخصي!\n\n📛 الاسم: {name}\n🔑 الرمز السري: {password}\n\n⚠️ احفظ الرمز السري!",
        "en": "✅ Profile completed!\n\n📛 Name: {name}\n🔑 Secret code: {password}\n\n⚠️ Save your secret code!",
    },
    "main_menu": {
        "ar": "🏠 القائمة الرئيسية\n\nأهلاً {name}! 👋\n\nأنت حالياً بالقائمة الرئيسية، اختر اللي تريده:\n\n🎲 لعب عشوائي - راح يدخلك مع لاعب عشوائي حول العالم أو ربما يكون جيرانك!\n👥 العب مع الأصدقاء - تقدر تلعب مع أصدقائك وتتحكم بالغرفة وتدزلهم الرابط يدخلون وياك\n🧮 حاسبة الاونو - تفيدك إذا كنتوا تلعبون اونو بالحقيقة وتريد حاسبة تحسبلكم بالمضبوط بدون أخطاء\n👤 حسابي - يمكنك من الدخول لحسابك وتعديل الرمز السري وتعديل اسمك",
        "en": "🏠 Main Menu\n\nHello {name}! 👋\n\nYou're on the main menu, choose what you want:\n\n🎲 Random Play - Matches you with a random player from around the world!\n👥 Play with Friends - Play with your friends, control the room, and share the link for them to join\n🧮 UNO Calculator - Useful when playing UNO in real life, calculates scores accurately for all players\n👤 My Account - Access your account, change your secret code or edit your name",
    },
    "btn_random_play": {
        "ar": "🎲 لعب عشوائي",
        "en": "🎲 Random Play",
    },
    "btn_play_friends": {
        "ar": "👥 العب مع الأصدقاء",
        "en": "👥 Play with Friends",
    },
    "btn_calculator": {
        "ar": "🧮 حاسبة الاونو",
        "en": "🧮 UNO Calculator",
    },
    "btn_create_room": {
        "ar": "➕ إنشاء غرفة",
        "en": "➕ Create Room",
    },
    "btn_join_room": {
        "ar": "📥 دخول غرفة",
        "en": "📥 Join Room",
    },
    "btn_leaderboard": {
        "ar": "🏆 المتصدرين",
        "en": "🏆 Leaderboard",
    },
    "btn_my_account": {
        "ar": "👤 حسابي",
        "en": "👤 My Account",
    },
    "btn_friends": {
        "ar": "👥 الأصدقاء",
        "en": "👥 Friends",
    },
    "btn_rules": {
        "ar": "📖 قوانين اللعبة",
        "en": "📖 Game Rules",
    },
    "btn_language": {
        "ar": "🌍 تغيير اللغة",
        "en": "🌍 Change Language",
    },
    "btn_home": {
        "ar": "🏠 القائمة الرئيسية",
        "en": "🏠 Main Menu",
    },
    "btn_back": {
        "ar": "🔙 رجوع",
        "en": "🔙 Back",
    },
    "choose_players": {
        "ar": "👥 اختر عدد اللاعبين:",
        "en": "👥 Choose number of players:",
    },
    "players_label": {
        "ar": "{n} لاعبين",
        "en": "{n} Players",
    },
    "choose_score_limit": {
        "ar": "🔢 الغرفة لـ {n} لاعبين.\nحدد سقف النقاط للفوز:",
        "en": "🔢 Room for {n} players.\nSet score limit to win:",
    },
    "single_round": {
        "ar": "🃏 جولة واحدة",
        "en": "🃏 Single Round",
    },
    "room_created": {
        "ar": "✅ تم إنشاء الغرفة بنجاح!\n\n🎮 هذا رابط الدخول للعبة، انقر الرابط للدخول:\n{link}",
        "en": "✅ Room created!\n\n🎮 Share this link to join the game:\n{link}",
    },
    "room_created_msg1": {
        "ar": "✅ تم إنشاء الغرفة بنجاح!\n\nسوف أعطيك رابط الدخول للغرفة، عليك إرساله لأصدقائك ليتمكنوا من الدخول واللعب معك. 👇",
        "en": "✅ Room created successfully!\n\nI'll give you a room link. Send it to your friends so they can join and play with you. 👇",
    },
    "room_created_msg2": {
        "ar": "🎮 هذا رابط الدخول للغرفة:\n{link}\n\n👆 انقر على الرابط أو أرسله لأصدقائك للدخول واللعب!",
        "en": "🎮 Here's the room link:\n{link}\n\n👆 Tap the link or share it with your friends to join and play!",
    },
    "room_created_invite": {
        "ar": "✅ تم إنشاء الغرفة!\n\n👥 اختر الأصدقاء اللي تبي تدعوهم (اضغط على اسم اللاعب لتحديده):",
        "en": "✅ Room created!\n\n👥 Select friends to invite (tap a name to select):",
    },
    "btn_send_invites": {
        "ar": "📨 إرسال الدعوات",
        "en": "📨 Send Invites",
    },
    "btn_get_link": {
        "ar": "🔗 الحصول على رابط فقط",
        "en": "🔗 Get Link Only",
    },
    "player_joined": {
        "ar": "📥 {name} انضم للغرفة!\n\n👥 اللاعبين ({count}/{max}):\n{list}",
        "en": "📥 {name} joined the room!\n\n👥 Players ({count}/{max}):\n{list}",
    },
    "waiting_players": {
        "ar": "\n⏳ بانتظار {n} لاعب آخر...",
        "en": "\n⏳ Waiting for {n} more player(s)...",
    },
    "room_full_starting": {
        "ar": "\n✅ اكتمل العدد! جاري بدء اللعب...",
        "en": "\n✅ Room full! Starting game...",
    },
    "game_starting_2p": {
        "ar": "🚀 جاري بدء اللعب الثنائي...",
        "en": "🚀 Starting 2-player game...",
    },
    "game_starting_multi": {
        "ar": "🚀 جاري بدء اللعب الجماعي ({n} لاعبين)...",
        "en": "🚀 Starting multiplayer game ({n} players)...",
    },
    "send_room_code": {
        "ar": "📥 أرسل كود الغرفة الآن:",
        "en": "📥 Send the room code now:",
    },
    "room_not_found": {
        "ar": "❌ الكود غلط أو الغرفة ممتلئة.",
        "en": "❌ Wrong code or room is full.",
    },
    "already_in_room": {
        "ar": "⚠️ أنت موجود بالغرفة بالفعل!",
        "en": "⚠️ You're already in this room!",
    },
    "room_full": {
        "ar": "❌ الغرفة ممتلئة!",
        "en": "❌ Room is full!",
    },
    "not_your_turn": {
        "ar": "مو دورك! ❌",
        "en": "Not your turn! ❌",
    },
    "btn_withdraw": {
        "ar": "🚪 انسحب",
        "en": "🚪 Leave",
    },
    "btn_settings": {
        "ar": "⚙️",
        "en": "⚙️",
    },
    "btn_draw": {
        "ar": "📥 اسحب ورقة",
        "en": "📥 Draw Card",
    },
    "btn_uno": {
        "ar": "🔔 UNO!",
        "en": "🔔 UNO!",
    },
    "btn_catch": {
        "ar": "🚨 إمسك!",
        "en": "🚨 Catch!",
    },
    "timer_remaining": {
        "ar": "⏳ باقي {s} ثانية",
        "en": "⏳ {s} seconds left",
    },
    "lang_changed": {
        "ar": "✅ تم تغيير اللغة إلى العربية!",
        "en": "✅ Language changed to English!",
    },
    "room_settings": {
        "ar": "⚙️ إعدادات الغرفة\n\n👥 عدد اللاعبين: {count}/{max}\n📊 سقف النقاط: {score}",
        "en": "⚙️ Room Settings\n\n👥 Players: {count}/{max}\n📊 Score Limit: {score}",
    },
    "btn_kick": {
        "ar": "🚫 طرد لاعبين",
        "en": "🚫 Kick Players",
    },
    "btn_change_limit": {
        "ar": "🔢 تغيير سقف اللعب ({score})",
        "en": "🔢 Change Score Limit ({score})",
    },
    "kick_select": {
        "ar": "🚫 حدد اللاعبين اللي تبي تطردهم:",
        "en": "🚫 Select players to kick:",
    },
    "btn_kick_selected": {
        "ar": "🚫 طرد المحددين ({n})",
        "en": "🚫 Kick Selected ({n})",
    },
    "kick_confirm": {
        "ar": "⚠️ هل أنت متأكد من طرد:\n{names}؟",
        "en": "⚠️ Are you sure you want to kick:\n{names}?",
    },
    "btn_yes_kick": {
        "ar": "✅ نعم، اطردهم",
        "en": "✅ Yes, kick them",
    },
    "btn_no": {
        "ar": "❌ لا",
        "en": "❌ No",
    },
    "kicked_notification": {
        "ar": "🚫 تم طردك من الغرفة بواسطة صاحب الغرفة.",
        "en": "🚫 You were kicked from the room by the room owner.",
    },
    "my_account_text": {
        "ar": "👤 حسابي\n\n📛 الاسم: {name}\n🔑 الرمز: {password}\n⭐ النقاط: {points}",
        "en": "👤 My Account\n\n📛 Name: {name}\n🔑 Code: {password}\n⭐ Points: {points}",
    },
    "btn_edit_account": {
        "ar": "✏️ تعديل الحساب",
        "en": "✏️ Edit Account",
    },
    "btn_logout": {
        "ar": "🚪 تسجيل الخروج",
        "en": "🚪 Logout",
    },
    "btn_change_name": {
        "ar": "📛 تغيير الاسم",
        "en": "📛 Change Name",
    },
    "btn_change_password": {
        "ar": "🔑 تغيير الرمز السري",
        "en": "🔑 Change Secret Code",
    },
    "btn_my_rooms": {
        "ar": "📋 الغرف المفتوحة",
        "en": "📋 Open Rooms",
    },
    "no_open_rooms": {
        "ar": "📋 ما عندك غرف مفتوحة حالياً!",
        "en": "📋 You have no open rooms!",
    },
    "no_open_rooms_text": {
        "ar": "📋 ما عندك غرف مفتوحة حالياً.",
        "en": "📋 You have no open rooms.",
    },
    "open_rooms_list": {
        "ar": "📋 غرفك المفتوحة:\n\nاضغط على الغرفة لعرض تفاصيلها، أو اضغط ❌ لإغلاقها.",
        "en": "📋 Your open rooms:\n\nTap a room for details, or press ❌ to close it.",
    },
    "room_detail": {
        "ar": "🎮 تفاصيل الغرفة: {code}\n\n👥 اللاعبين ({count}/{max}):\n{players}\n🔗 رابط الدخول:\n{link}",
        "en": "🎮 Room Details: {code}\n\n👥 Players ({count}/{max}):\n{players}\n🔗 Join Link:\n{link}",
    },
    "btn_close_room": {
        "ar": "❌ إغلاق الغرفة",
        "en": "❌ Close Room",
    },
    "room_closed": {
        "ar": "✅ تم إغلاق الغرفة!",
        "en": "✅ Room closed!",
    },
    "room_closed_notification": {
        "ar": "⚠️ تم إغلاق الغرفة من قبل صاحبها.",
        "en": "⚠️ The room was closed by its owner.",
    },
    "random_waiting": {
        "ar": "🎲 جاري البحث عن لاعب عشوائي...\n\n⏳ انتظر شوي، أول ما يجي لاعب ثاني راح تبدأ اللعبة تلقائياً!",
        "en": "🎲 Looking for a random player...\n\n⏳ Wait a moment, the game will start automatically when another player joins!",
    },
    "friends_menu": {
        "ar": "👥 العب مع الأصدقاء\n\nاختر:",
        "en": "👥 Play with Friends\n\nChoose:",
    },
    "room_gone": {
        "ar": "⚠️ الغرفة لم تعد موجودة.",
        "en": "⚠️ Room no longer exists.",
    },
    "only_creator": {
        "ar": "⚠️ فقط صاحب الغرفة يقدر يسوي هالشي!",
        "en": "⚠️ Only the room owner can do this!",
    },
    "no_other_players": {
        "ar": "⚠️ ما في لاعبين ثانيين في الغرفة!",
        "en": "⚠️ No other players in the room!",
    },

    "rules_full": {
        "ar": """📖 قوانين لعبة UNO الكاملة

🃏 عدد الأوراق الكلي: 108 ورقة
🎨 عدد الألوان: 4 (🔴 أحمر، 🔵 أزرق، 🟢 أخضر، 🟡 أصفر)
🔢 أوراق الأرقام: 0-9 لكل لون (76 ورقة)
⚡ أوراق الأكشن: 24 ورقة (8 لكل نوع)
🌈 أوراق الجوكر: 8 أوراق (4 جوكر عادي + 4 جوكر ⬆️4)

━━━━━━━━━━━━━━━
🔢 أوراق الأرقام (0-9):
━━━━━━━━━━━━━━━
• العب ورقة بنفس الرقم أو نفس اللون
• الورقة 0 موجودة مرة واحدة لكل لون
• الأوراق 1-9 موجودة مرتين لكل لون

━━━━━━━━━━━━━━━
⚡ أوراق الأكشن:
━━━━━━━━━━━━━━━
🔄 عكس (Reverse):
• الثنائي: تلعب دور إضافي
• الجماعي: يعكس اتجاه اللعب

⛔ تخطي (Skip):
• الثنائي: تلعب دور إضافي
• الجماعي: يتخطى اللاعب التالي

⬆️2 سحب اثنين (Draw 2):
• اللاعب التالي يسحب ورقتين ويفقد دوره
• ما يقدر يرد عليها

━━━━━━━━━━━━━━━
🌈 الجوكر العادي (Wild):
━━━━━━━━━━━━━━━
• تقدر تلعبها بأي وقت
• تختار اللون اللي تبيه
• إذا ما اخترت خلال 20 ثانية، يتم اختيار لون عشوائي

━━━━━━━━━━━━━━━
🌈 جوكر ⬆️4 (Wild Draw 4):
━━━━━━━━━━━━━━━
• تقدر تلعبها بأي وقت
• تختار اللون + اللاعب التالي يسحب 4 أوراق
• اللاعب التالي يقدر يتحدى! 🔥

🔥 نظام التحدي:
• إذا تحدى وأنت فعلاً ما عندك ورقة بنفس اللون = التحدي فشل، يسحب 6 أوراق
• إذا تحدى وأنت عندك ورقة بنفس اللون = التحدي نجح، أنت تسحب 4 أوراق
• عنده 20 ثانية يقرر: تحدي أو قبول

━━━━━━━━━━━━━━━
🔔 نظام UNO:
━━━━━━━━━━━━━━━
• لازم تضغط "UNO!" لما يبقى عندك ورقة وحدة
• إذا ما ضغطت وأحد ضغط "إمسك!" تسحب ورقتين عقوبة
• زر UNO يظهر تلقائي لما تبقى لك ورقتين

━━━━━━━━━━━━━━━
⏱ المؤقت:
━━━━━━━━━━━━━━━
• 20 ثانية لكل دور
• إذا ما لعبت بالوقت، تسحب ورقة تلقائياً وينتقل الدور

━━━━━━━━━━━━━━━
🏆 نظام النقاط:
━━━━━━━━━━━━━━━
• الأرقام (0-9): قيمة الرقم نفسه
• أكشن (عكس/تخطي/⬆️2): 20 نقطة
• جوكر عادي: 50 نقطة
• جوكر ⬆️4: 50 نقطة
• الفائز بالجولة ياخذ نقاط أوراق الخاسرين
• أول واحد يوصل سقف النقاط يفوز باللعبة!""",
        "en": """📖 Complete UNO Game Rules

🃏 Total Cards: 108
🎨 Colors: 4 (🔴 Red, 🔵 Blue, 🟢 Green, 🟡 Yellow)
🔢 Number Cards: 0-9 per color (76 cards)
⚡ Action Cards: 24 cards (8 of each type)
🌈 Wild Cards: 8 cards (4 Wild + 4 Wild ⬆️4)

━━━━━━━━━━━━━━━
🔢 Number Cards (0-9):
━━━━━━━━━━━━━━━
• Play a card with same number or same color
• Card 0 appears once per color
• Cards 1-9 appear twice per color

━━━━━━━━━━━━━━━
⚡ Action Cards:
━━━━━━━━━━━━━━━
🔄 Reverse:
• 2-Player: You get an extra turn
• Multiplayer: Reverses play direction

⛔ Skip:
• 2-Player: You get an extra turn
• Multiplayer: Next player loses their turn

⬆️2 Draw Two:
• Next player draws 2 cards and loses turn
• Cannot be countered

━━━━━━━━━━━━━━━
🌈 Wild Card:
━━━━━━━━━━━━━━━
• Can be played at any time
• You choose the color
• If not chosen in 20 seconds, random color is picked

━━━━━━━━━━━━━━━
🌈 Wild ⬆️4 (Wild Draw 4):
━━━━━━━━━━━━━━━
• Can be played at any time
• You choose color + next player draws 4 cards
• Next player can challenge! 🔥

🔥 Challenge System:
• If challenged and you truly had no matching color = challenge fails, challenger draws 6
• If challenged and you had a matching color = challenge succeeds, you draw 4
• 20 seconds to decide: challenge or accept

━━━━━━━━━━━━━━━
🔔 UNO System:
━━━━━━━━━━━━━━━
• Press "UNO!" when you have 1 card left
• If you don't and someone presses "Catch!" you draw 2 penalty cards
• UNO button appears automatically when you have 2 cards left

━━━━━━━━━━━━━━━
⏱ Timer:
━━━━━━━━━━━━━━━
• 20 seconds per turn
• If you don't play in time, you auto-draw a card and turn passes

━━━━━━━━━━━━━━━
🏆 Scoring System:
━━━━━━━━━━━━━━━
• Numbers (0-9): Face value
• Action (Reverse/Skip/⬆️2): 20 points
• Wild: 50 points
• Wild ⬆️4: 50 points
• Round winner gets points from losers' cards
• First to reach score limit wins the game!""",
    },
}
