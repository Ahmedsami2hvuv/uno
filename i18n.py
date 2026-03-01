# -*- coding: utf-8 -*-
"""
ترجمة البوت: عربي (ar)، إنجليزي (en)، فارسي إيراني (fa)
"""
from database import db_query

# الترجمة الافتراضية عند غياب المفتاح
DEFAULT_LANG = "ar"

# كاش لتقليل استدعاءات قاعدة البيانات (لغة المستخدم)
_lang_cache = {}

def get_lang(user_id: int) -> str:
    if user_id in _lang_cache:
        return _lang_cache[user_id]
    try:
        r = db_query("SELECT language FROM users WHERE user_id = %s", (user_id,))
        if r and r[0].get("language") in ("ar", "en", "fa"):
            _lang_cache[user_id] = r[0]["language"]
            return _lang_cache[user_id]
    except Exception:
        pass
    _lang_cache[user_id] = DEFAULT_LANG
    return DEFAULT_LANG

def set_lang(user_id: int, lang: str):
    _lang_cache[user_id] = lang if lang in ("ar", "en", "fa") else DEFAULT_LANG
    try:
        db_query("UPDATE users SET language = %s WHERE user_id = %s", (lang, user_id), commit=True)
    except Exception:
        pass

def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_lang(user_id)
    texts = TEXTS.get(lang) or TEXTS.get(DEFAULT_LANG) or {}
    s = texts.get(key) or TEXTS.get("ar", {}).get(key) or key
    if kwargs:
        try:
            s = s.format(**kwargs)
        except KeyError:
            pass
    return s

# --- النصوص حسب اللغة ---
TEXTS = {
    "ar": {
        "welcome_new": "مرحباً! 👋\nسجّل الدخول أو أنشئ حساباً للعب.",
        "btn_register": "📝 تسجيل",
        "btn_login": "🔐 دخول",
        "ask_name": "✍️ أرسل اسمك (اسم اللاعب):",
        "ask_password": "🔑 أرسل كلمة السر (4 أحرف أو أكثر):",
        "name_too_short": "❌ الاسم قصير جداً. أرسل اسمك مرة ثانية:",
        "name_too_long": "❌ الاسم طويل جداً. اختصر وأرسل:",
        "name_taken": "❌ هذا الاسم مستخدم. اختر غيره:",
        "password_too_short": "❌ كلمة السر ضعيفة. أرسل 4 أحرف أو أكثر:",
        "reg_success": "✅ تم التسجيل! مرحباً {name}، يوزرك: @{username}",
        "profile_complete": "✅ تم! مرحباً {name}. كلمة السر محفوظة.",
        "register_success": "✅ تم التسجيل بنجاح! مرحباً {name}، كلمة السر: {password}",
        "login_ask_name": "🔐 أدخل اسم المستخدم (اليوزر نيم) للدخول:",
        "login_ask_password": "🔑 أدخل كلمة السر:",
        "login_fail": "❌ فشل الدخول. تحقق من اليوزر نيم وكلمة السر.",
        "login_success": "✅ تم الدخول! مرحباً {name}.",
        "room_not_found": "❌ الغرفة غير موجودة أو انتهت.",
        "already_in_room": "⚠️ أنت بالفعل في غرفة.",
        "room_full": "⚠️ الغرفة ممتلئة.",
        "game_starting_2p": "🎮 بدأت اللعبة! استعد...",
        "game_starting_multi": "🎮 بدأت اللعبة! عدد اللاعبين: {n}. استعد...",
        "🎮 بدأت اللعبة! استعد...": "🎮 بدأت اللعبة! استعد...",
        "btn_home": "🏠 الرئيسية",
        "player_joined": "✅ انضم {name} للغرفة ({count}/{max}). اللاعبون: {list}",
        "waiting_players": " ⏳ بانتظار {n} لاعب.",
        "🤌🏻اصبر شوي ": "🤌🏻 اصبر شوي",
        "➕ إنشاء غرفة": "➕ إنشاء غرفة",
        "🚪 انضمام لغرفة": "🚪 انضمام لغرفة",
        "الغرف المفتوحة": "الغرف المفتوحة",
        "الرجوع": "🔙 رجوع",
        "friends_menu": "🎮 اللعب مع الأصدقاء\n\nاختر:",
        "no_open_rooms": "⚠️ لا توجد غرف مفتوحة.",
        "open_rooms_list": "📋 غرفك المفتوحة:",
        "room_detail": "🛏 غرفة: {code}\n👥 اللاعبون ({count}/{max}): {players}\n\n🔗 رابط الدخول:\n{link}",
        "btn_close_room": "🚪 إغلاق الغرفة",
        "btn_back": "🔙 رجوع",
        "my_open_rooms": "الغرف المفتوحة",
        "room_gone": "⚠️ الغرفة لم تعد موجودة.",
        "room_closed_notification": "⚠️ تم إغلاق الغرفة من قبل صاحبها.",
        "room_closed": "✅ تم إغلاق الغرفة.",
        "no_open_rooms_text": "لا توجد غرف مفتوحة. أنشئ غرفة أو انضم بكود.",
        "send_room_code": "🔑 أرسل رمز الغرفة (5 أحرف):",
        "btn_random_play": "🎲 لعب عشوائي",
        "btn_play_friends": "👥 لعب مع الأصدقاء",
        "btn_my_account": "👤 حسابي",
        "main_menu": "🎮 أهلاً {name}\n\nاختر:",
        "lang_changed": "✅ تم تغيير اللغة.",
        "status_online": "🟢 متصل الآن",
        "status_offline": "⚫ آخر ظهور: {time}",
        "profile_title": "👤 **{name}**\n🆔 @{username}\n⭐ نقاط: {points}\n{status}",
        "btn_follow": "➕ متابعة",
        "btn_unfollow": "➖ إلغاء المتابعة",
        "btn_invite_play": "🎮 دعوة للعب",
        "btn_followers_list": "👥 المتابعون",
        "btn_following_list": "👥 المتابَعون",
        "btn_friends": "👥 الأصدقاء",
        "btn_calc": "🧮 حاسبة أونو",
        "btn_rules": "📜 القوانين",
        "btn_leaderboard": "📊 الإحصائيات",
        "btn_change_lang": "🌍 تغيير اللغة",
        "choose_language": "🌍 **اختر اللغة:**",
        "menu_updated": "تم تحديث القائمة 🎮",
        "invite_pending_room": "🎮 لديك دعوة للانضمام إلى غرفة! سجّل الدخول أو أنشئ حساباً ثم سيتم إدخالك للغرفة تلقائياً.",
        "rules_text": "📜 **قوانين أونو العراق 🇮🇶 - الدليل الكامل**\n\nالهدف من اللعبة هو إنك تخلص أوراقك قبل الكل. إذا وصلت لآخر ورقة، لازم تدوس زر \"أونو\" فوراً، وإلا راح تسحب أوراق عقوبة!\n\n🔹 **الأوراق الخاصة:**\n1️⃣ **سحب 2 (+2):** اللاعب اللي وراك يسحب ورقتين ويعبر دوره، إلا إذا عنده +2 يكدر يذبها عليك وتصير \"تراكمية\" (سحب 4).\n2️⃣ **عكس الدور (🔄):** يقلب اتجاه اللعب من اليمين لليسار أو العكس.\n3️⃣ **المنع (🚫):** يطفر اللاعب اللي وراك وما يخلي يلعب هالجولة.\n4️⃣ **الجوكر (🌈):** يغير اللون للون اللي أنت تريده.\n5️⃣ **جوكر سحب 4 (🌈+4):** أقوى ورقة! تغير اللون وتخلي الخصم يسحب 4 ورقات، بس تكدر \"تتحداه\" إذا جان عنده نفس اللون الأساسي.\n\n🔹 **قوانين التحدي والعقوبات:**\n- **تحدي الـ +4:** إذا ذبوا عليك +4 وتشك إن الخصم عنده نفس اللون اللي جان عالكاع، تكدر \"تتحداه\". إذا طلع غاش، هو يسحب الـ 4. إذا طلع صادق، أنت تسحب 6!\n- **نسيان الأونو:** إذا بقت عندك ورقة وحدة وما كلت \"أونو\" وكشفك الخصم، راح تسحب ورقتين عقوبة.\n\n🔹 **نهاية اللعبة:**\nتنتهي الجولة بس يخلص أول لاعب أوراقه. تنحسب نقاط الأوراق اللي بقت بيد البقية وتضاف لرصيدك.",
        "btn_back_short": "🔙 عودة",
        "tutorial_title": "🎓 مرحباً! جولة سريعة على البوت",
        "tutorial_body": "• **لعب عشوائي:** البوت يلاقي لك خصم وتبدأون.\n• **لعب مع الأصدقاء:** تنشئ غرفة أو تنضم بكود أو رابط.\n• **حسابي:** تعديل الاسم والإعدادات.\n• **القوانين:** قوانين أونو كاملة.\n\nاضغط «جرب الآن» لفتح القائمة والبدء!",
        "tutorial_btn": "✅ جرب الآن",
        "invite_reminder": "⏰ تذكير: ما زال عندك دعوة للعب! الرد خلال 15 ثانية المتبقية.",
        "leaderboard_title": "📊 **لوحة المتصدرين**",
        "leaderboard_global": "🌍 الكل",
        "leaderboard_friends": "👥 أصدقائي فقط",
        "leaderboard_empty": "لا يوجد لاعبون بعد.",
        "leaderboard_row": "{rank}. {name} — {points} نقطة",
        "round_summary_won": "فاز بالجولة",
        "match_history_title": "📜 آخر مبارياتك",
        "match_history_none": "لا توجد مباريات مسجلة بعد.",
        "match_history_row": "جولة {round} — فزت 🏆 (غرفة {room})",
        "public_rooms_title": "🚪 **غرف عامة**\nاختر غرفة للانضمام:",
        "public_rooms_none": "لا توجد غرف مفتوحة حالياً.",
        "public_room_row": "غرفة {code} — {current}/{max} لاعبين",
        "btn_join": "انضم",
        "replay_again_btn": "🔄 لعب مرة أخرى",
        "replay_again_msg": "🏁 انتهت الجولة! اضغط «لعب مرة أخرى» لدعوة نفس الفريق.",
        "btn_public_rooms": "🚪 غرف عامة",
    },
    "en": {
        "welcome_new": "Welcome! 👋\nLog in or register to play.",
        "btn_register": "📝 Register",
        "btn_login": "🔐 Log in",
        "ask_name": "✍️ Send your name (player name):",
        "ask_password": "🔑 Send your password (4+ characters):",
        "name_too_short": "❌ Name too short. Send again:",
        "name_too_long": "❌ Name too long. Shorten and send:",
        "name_taken": "❌ This name is taken. Choose another:",
        "password_too_short": "❌ Password too weak. Send 4+ characters:",
        "reg_success": "✅ Registered! Hi {name}, username: @{username}",
        "profile_complete": "✅ Done! Welcome {name}. Password saved.",
        "register_success": "✅ Registered! Hi {name}, password: {password}",
        "login_ask_name": "🔐 Enter username to log in:",
        "login_ask_password": "🔑 Enter password:",
        "login_fail": "❌ Login failed. Check username and password.",
        "login_success": "✅ Logged in! Hi {name}.",
        "room_not_found": "❌ Room not found or expired.",
        "already_in_room": "⚠️ You are already in a room.",
        "room_full": "⚠️ Room is full.",
        "game_starting_2p": "🎮 Game started! Get ready...",
        "game_starting_multi": "🎮 Game started! Players: {n}. Get ready...",
        "🎮 بدأت اللعبة! استعد...": "🎮 Game started! Get ready...",
        "btn_home": "🏠 Home",
        "player_joined": "✅ {name} joined the room ({count}/{max}). Players: {list}",
        "waiting_players": " ⏳ Waiting for {n} player(s).",
        "🤌🏻اصبر شوي ": "🤌🏻 Hold on...",
        "➕ إنشاء غرفة": "➕ Create room",
        "🚪 انضمام لغرفة": "🚪 Join room",
        "الغرف المفتوحة": "Open rooms",
        "الرجوع": "🔙 Back",
        "friends_menu": "🎮 Play with friends\n\nChoose:",
        "no_open_rooms": "⚠️ No open rooms.",
        "open_rooms_list": "📋 Your open rooms:",
        "room_detail": "🛏 Room: {code}\n👥 Players ({count}/{max}): {players}\n\n🔗 Join link:\n{link}",
        "btn_close_room": "🚪 Close room",
        "btn_back": "🔙 Back",
        "my_open_rooms": "Open rooms",
        "room_gone": "⚠️ Room no longer exists.",
        "room_closed_notification": "⚠️ The room was closed by the host.",
        "room_closed": "✅ Room closed.",
        "no_open_rooms_text": "No open rooms. Create one or join with a code.",
        "send_room_code": "🔑 Send the room code (5 characters):",
        "btn_random_play": "🎲 Random play",
        "btn_play_friends": "👥 Play with friends",
        "btn_my_account": "👤 My account",
        "main_menu": "🎮 Hello {name}\n\nChoose:",
        "lang_changed": "✅ Language changed.",
        "status_online": "🟢 Online",
        "status_offline": "⚫ Last seen: {time}",
        "profile_title": "👤 **{name}**\n🆔 @{username}\n⭐ Points: {points}\n{status}",
        "btn_follow": "➕ Follow",
        "btn_unfollow": "➖ Unfollow",
        "btn_invite_play": "🎮 Invite to play",
        "btn_followers_list": "👥 Followers",
        "btn_following_list": "👥 Following",
        "btn_friends": "👥 Friends",
        "btn_calc": "🧮 Uno Calculator",
        "btn_rules": "📜 Rules",
        "btn_leaderboard": "📊 Statistics",
        "btn_change_lang": "🌍 Change language",
        "choose_language": "🌍 **Choose language:**",
        "menu_updated": "Menu updated 🎮",
        "invite_pending_room": "🎮 You have an invite to join a room! Log in or register and you will join automatically.",
        "rules_text": "📜 **Uno Iraq 🇮🇶 - Full Rules**\n\nThe goal is to get rid of all your cards first. When you have one card left, you must press \"Uno\" immediately, or you draw penalty cards!\n\n🔹 **Special cards:**\n1️⃣ **Draw 2 (+2):** The next player draws 2 and skips their turn, unless they have +2 and stack it (draw 4).\n2️⃣ **Reverse (🔄):** Reverses play direction.\n3️⃣ **Skip (🚫):** The next player is skipped.\n4️⃣ **Wild (🌈):** Choose the new color.\n5️⃣ **Wild Draw 4 (🌈+4):** Strongest card! Choose color and the next player draws 4. They can challenge if they think you had a matching color.\n\n🔹 **Challenge & penalties:**\n- **+4 challenge:** If you get +4 and suspect the player had a matching color, you can challenge. If they cheated, they draw 4. If not, you draw 6!\n- **Forgot Uno:** If you had one card and didn't say \"Uno\" and get caught, you draw 2.\n\n🔹 **End of game:**\nThe round ends when one player runs out of cards. Remaining cards in others' hands are counted as points and added to the winner's score.",
        "btn_back_short": "🔙 Back",
        "tutorial_title": "🎓 Hi! Quick tour of the bot",
        "tutorial_body": "• **Random play:** The bot finds you an opponent and you start.\n• **Play with friends:** Create a room or join with a code/link.\n• **My account:** Edit name and settings.\n• **Rules:** Full Uno rules.\n\nPress «Try now» to open the menu and start!",
        "tutorial_btn": "✅ Try now",
        "invite_reminder": "⏰ Reminder: You still have a game invite! Reply within the next 15 seconds.",
        "leaderboard_title": "📊 **Leaderboard**",
        "leaderboard_global": "🌍 Everyone",
        "leaderboard_friends": "👥 Friends only",
        "leaderboard_empty": "No players yet.",
        "leaderboard_row": "{rank}. {name} — {points} pts",
        "round_summary_won": "won the round",
        "match_history_title": "📜 Your last matches",
        "match_history_none": "No matches recorded yet.",
        "match_history_row": "Round {round} — You won 🏆 (room {room})",
        "public_rooms_title": "🚪 **Public rooms**\nChoose a room to join:",
        "public_rooms_none": "No open rooms at the moment.",
        "public_room_row": "Room {code} — {current}/{max} players",
        "btn_join": "Join",
        "replay_again_btn": "🔄 Play again",
        "replay_again_msg": "🏁 Round over! Press «Play again» to invite the same team.",
        "btn_public_rooms": "🚪 Public rooms",
    },
    "fa": {
        "welcome_new": "خوش آمدید! 👋\nبرای بازی وارد شوید یا ثبت‌نام کنید.",
        "btn_register": "📝 ثبت‌نام",
        "btn_login": "🔐 ورود",
        "ask_name": "✍️ نام خود را بفرستید (نام بازیکن):",
        "ask_password": "🔑 رمز عبور را بفرستید (حداقل ۴ کاراکتر):",
        "name_too_short": "❌ نام خیلی کوتاه است. دوباره بفرستید:",
        "name_too_long": "❌ نام خیلی بلند است. کوتاه کنید و بفرستید:",
        "name_taken": "❌ این نام قبلاً استفاده شده. یکی دیگر انتخاب کنید:",
        "password_too_short": "❌ رمز عبور ضعیف است. حداقل ۴ کاراکتر بفرستید:",
        "reg_success": "✅ ثبت‌نام شد! سلام {name}، نام کاربری: @{username}",
        "profile_complete": "✅ انجام شد! خوش آمدید {name}. رمز ذخیره شد.",
        "register_success": "✅ ثبت‌نام انجام شد! سلام {name}، رمز: {password}",
        "login_ask_name": "🔐 نام کاربری را برای ورود وارد کنید:",
        "login_ask_password": "🔑 رمز عبور را وارد کنید:",
        "login_fail": "❌ ورود ناموفق. نام کاربری و رمز را بررسی کنید.",
        "login_success": "✅ وارد شدید! سلام {name}.",
        "room_not_found": "❌ اتاق پیدا نشد یا منقضی شده.",
        "already_in_room": "⚠️ شما الان در یک اتاق هستید.",
        "room_full": "⚠️ اتاق پر است.",
        "game_starting_2p": "🎮 بازی شروع شد! آماده باشید...",
        "game_starting_multi": "🎮 بازی شروع شد! بازیکنان: {n}. آماده باشید...",
        "🎮 بدأت اللعبة! استعد...": "🎮 بازی شروع شد! آماده باشید...",
        "btn_home": "🏠 خانه",
        "player_joined": "✅ {name} به اتاق پیوست ({count}/{max}). بازیکنان: {list}",
        "waiting_players": " ⏳ در انتظار {n} بازیکن.",
        "🤌🏻اصبر شوي ": "🤌🏻 صبر کنید...",
        "➕ إنشاء غرفة": "➕ ساخت اتاق",
        "🚪 انضمام لغرفة": "🚪 پیوستن به اتاق",
        "الغرف المفتوحة": "اتاق‌های باز",
        "الرجوع": "🔙 بازگشت",
        "friends_menu": "🎮 بازی با دوستان\n\nانتخاب کنید:",
        "no_open_rooms": "⚠️ اتاق بازی وجود ندارد.",
        "open_rooms_list": "📋 اتاق‌های باز شما:",
        "room_detail": "🛏 اتاق: {code}\n👥 بازیکنان ({count}/{max}): {players}\n\n🔗 لینک ورود:\n{link}",
        "btn_close_room": "🚪 بستن اتاق",
        "btn_back": "🔙 بازگشت",
        "my_open_rooms": "اتاق‌های باز",
        "room_gone": "⚠️ اتاق دیگر وجود ندارد.",
        "room_closed_notification": "⚠️ اتاق توسط سازنده بسته شد.",
        "room_closed": "✅ اتاق بسته شد.",
        "no_open_rooms_text": "اتاق بازی ندارید. یکی بسازید یا با کد وارد شوید.",
        "send_room_code": "🔑 کد اتاق (۵ کاراکتر) را بفرستید:",
        "btn_random_play": "🎲 بازی تصادفی",
        "btn_play_friends": "👥 بازی با دوستان",
        "btn_my_account": "👤 حساب من",
        "main_menu": "🎮 سلام {name}\n\nانتخاب کنید:",
        "lang_changed": "✅ زبان تغییر کرد.",
        "status_online": "🟢 آنلاین",
        "status_offline": "⚫ آخرین بازدید: {time}",
        "profile_title": "👤 **{name}**\n🆔 @{username}\n⭐ امتیاز: {points}\n{status}",
        "btn_follow": "➕ دنبال کردن",
        "btn_unfollow": "➖ لغو دنبال",
        "btn_invite_play": "🎮 دعوت به بازی",
        "btn_followers_list": "👥 دنبال‌کنندگان",
        "btn_following_list": "👥 دنبال‌شده‌ها",
        "btn_friends": "👥 دوستان",
        "btn_calc": "🧮 ماشین‌حساب اونو",
        "btn_rules": "📜 قوانین",
        "btn_leaderboard": "📊 آمار",
        "btn_change_lang": "🌍 تغییر زبان",
        "choose_language": "🌍 **زبان را انتخاب کنید:**",
        "menu_updated": "منو به‌روز شد 🎮",
        "invite_pending_room": "🎮 دعوت برای پیوستن به اتاق داری! وارد شو یا ثبت‌نام کن تا خودکار به اتاق بیایی.",
        "rules_text": "📜 **قوانین اونو عراق 🇮🇶 - راهنمای کامل**\n\nهدف بازی این است که قبل از همه کارت‌هایت را تمام کنی. وقتی یک کارت ماند، باید فوراً «اوونو» بزنی وگرنه کارت جریمه می‌کشی!\n\n🔹 **کارت‌های خاص:**\n1️⃣ **سحب ۲ (+۲):** بازیکن بعد ۲ کارت می‌کشد و نوبتش می‌افتد؛ مگر +۲ داشته باشد و بگذارد (۴ کارت).\n2️⃣ **برعکس (🔄):** جهت بازی عوض می‌شود.\n3️⃣ **منع (🚫):** بازیکن بعد نوبت نمی‌گیرد.\n4️⃣ **جوكر (🌈):** رنگ جدید را انتخاب کن.\n5️⃣ **جوكر +۴ (🌈+۴):** قوی‌ترین کارت! رنگ را عوض کن و بازیکن بعد ۴ کارت بکشد. در صورت داشتن رنگ همانند می‌تواند «چالش» بدهد.\n\n🔹 **چالش و جریمه:**\n- **چالش +۴:** اگر +۴ خوردی و فکر می‌کنی بازیکن رنگ همانند داشت، چالش بده. اگر تقلب کرده باشد ۴ کارت می‌کشد؛ وگرنه تو ۶ کارت می‌کشی!\n- **فراموشی اوونو:** اگر یک کارت داشتی و «اوونو» نگفتی و گیر افتادی، ۲ کارت جریمه می‌کشی.\n\n🔹 **پایان بازی:**\nوقتی یک بازیکن کارتش تمام شد دور تمام می‌شود. مجموع امتیاز کارت‌های باقی‌مانده به امتیاز برنده اضافه می‌شود.",
        "btn_back_short": "🔙 بازگشت",
        "tutorial_title": "🎓 سلام! راهنمای سریع ربات",
        "tutorial_body": "• **بازی تصادفی:** ربات حریف پیدا می‌کند و بازی شروع می‌شود.\n• **بازی با دوستان:** ساخت اتاق یا پیوستن با کد/لینک.\n• **حساب من:** تغییر نام و تنظیمات.\n• **قوانین:** قوانین کامل اونو.\n\n«الان امتحان کن» را بزن تا منو باز شود!",
        "tutorial_btn": "✅ الان امتحان کن",
        "invite_reminder": "⏰ یادآوری: هنوز دعوت بازی داری! تا ۱۵ ثانیهٔ بعد پاسخ بده.",
        "leaderboard_title": "📊 **جدول امتیازات**",
        "leaderboard_global": "🌍 همه",
        "leaderboard_friends": "👥 فقط دوستان",
        "leaderboard_empty": "هنوز بازیکنی نیست.",
        "leaderboard_row": "{rank}. {name} — {points} امتیاز",
        "round_summary_won": "برندهٔ دور شد",
        "match_history_title": "📜 آخرین بازی‌های شما",
        "match_history_none": "هنوز بازی‌ای ثبت نشده.",
        "match_history_row": "دور {round} — بردی 🏆 (اتاق {room})",
        "public_rooms_title": "🚪 **اتاق‌های عمومی**\nیک اتاق برای پیوستن انتخاب کنید:",
        "public_rooms_none": "الان اتاق بازی باز نیست.",
        "public_room_row": "اتاق {code} — {current}/{max} بازیکن",
        "btn_join": "پیوستن",
        "replay_again_btn": "🔄 بازی دوباره",
        "replay_again_msg": "🏁 دور تمام شد! «بازی دوباره» را بزن تا همان تیم دعوت شوند.",
        "btn_public_rooms": "🚪 اتاق‌های عمومی",
    },
}

