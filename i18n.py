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
    # البحث عن المفتاح، وإذا لم يوجد نرجع المفتاح نفسه كـ string
    text = TEXTS.get(key, {}).get(lang, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except: pass
    return text

TEXTS = {
    "choose_lang": {
        "ar": "🌍 اختر لغتك / Choose your language:",
        "en": "🌍 Choose your language / اختر لغتك:",
    },
    # --- نظام التسجيل والترقية الجديد ---
    "reg_upgrade_notice": {
        "ar": "⚠️ مهلاً عزيزي اللاعب..\n\nلقد أطلقنا تحديثاً جديداً لنظام الحسابات! يرجى اختيار 'اسم مستخدم' (Username) وكلمة سر لتتمكن من إضافة الأصدقاء ومتابعتهم.",
        "en": "⚠️ Wait, dear player..\n\nWe launched a new account system! Please choose a 'Username' and password to be able to follow and add friends.",
    },
    "ask_username_key": {
        "ar": "✍️ أرسل الآن 'اسم المستخدم' الذي تريده (بالإنجليزية والأرقام فقط، مثال: ahmed_uno):",
        "en": "✍️ Send the 'Username' you want (English & numbers only, e.g., ahmed_uno):",
    },
    "ask_password_key": {
        "ar": "🔒 ممتاز! الآن أرسل رمزاً سرياً (Password) لحماية حسابك:",
        "en": "🔒 Great! Now send a secret code (Password) to protect your account:",
    },
    "username_taken": {
        "ar": "❌ عذراً، هذا الاسم محجوز للاعب آخر. جرب اسماً مختلفاً:",
        "en": "❌ Sorry, this username is taken. Try another one:",
    },
    "reg_success": {
        "ar": "🎉 تهانينا {name}! تم إنشاء حسابك بنجاح.\nاسمك الفريد هو: @{username}",
        "en": "🎉 Congratulations {name}! Your account is ready.\nYour unique ID is: @{username}",
    },
    # --- البروفايل والنظام الاجتماعي ---
    "profile_title": {
        "ar": "👤 ملف اللاعب: {name}\n🆔 المعرف: @{username}\n🏆 النقاط: {points}\n📊 الحالة: {status}",
        "en": "👤 Player Profile: {name}\n🆔 Username: @{username}\n🏆 Points: {points}\n📊 Status: {status}",
    },
    "status_online": {"ar": "🟢 متصل الآن", "en": "🟢 Online"},
    "status_offline": {"ar": "⚪ غير متصل ({time})", "en": "⚪ Offline ({time})"},
    "btn_follow": {"ar": "➕ متابعة", "en": "➕ Follow"},
    "btn_unfollow": {"ar": "➖ إلغاء المتابعة", "en": "➖ Unfollow"},
    "btn_invite_play": {"ar": "🎮 دعوة للعب", "en": "🎮 Invite to Play"},
    "btn_spectate": {"ar": "👁 مشاهدة اللعب", "en": "👁 Spectate"},
    "btn_following_list": {"ar": "📉 من أتابعهم", "en": "📉 Following"},
    "btn_followers_list": {"ar": "📈 المتابعون", "en": "📈 Followers"},
    
    # --- نظام الإسكات (Mute) ---
    "mute_settings": {
        "ar": "🔕 هل تريد إسكات دعوات اللعب من هذا اللاعب؟",
        "en": "🔕 Do you want to mute play invites from this player?",
    },
    "btn_mute_1h": {"ar": "ساعة واحدة", "en": "1 Hour"},
    "btn_mute_24h": {"ar": "يوم كامل", "en": "24 Hours"},
    "btn_mute_forever": {"ar": "للأبد", "en": "Forever"},
    "btn_unmute": {"ar": "إلغاء الإسكات", "en": "Unmute"},

    # --- القائمة الرئيسية والترحيب ---
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
    "main_menu": {
        "ar": "🏠 القائمة الرئيسية\n\nأهلاً {name}! 👋\n\nأنت حالياً بالقائمة الرئيسية، اختر اللي تريده:\n\n🎲 لعب عشوائي - العب مع لاعبين حول العالم\n👥 الأصدقاء - تابع أصدقاءك وشوف المتصلين\n👤 حسابي - إعداداتك وخصوصيتك واليوزر مالتك",
        "en": "🏠 Main Menu\n\nHello {name}! 👋\n\nYou're on the main menu, choose:\n\n🎲 Random Play - Play with players worldwide\n👥 Friends - Follow and see online friends\n👤 My Account - Your settings, privacy and username",
    },
    "btn_random_play": {"ar": "🎲 لعب عشوائي", "en": "🎲 Random Play"},
    "btn_play_friends": {"ar": "👥 العب مع الأصدقاء", "en": "👥 Play with Friends"},
    "btn_calculator": {"ar": "🧮 حاسبة الاونو", "en": "🧮 UNO Calculator"},
    "btn_my_account": {"ar": "👤 حسابي", "en": "👤 My Account"},
    "btn_friends": {"ar": "👥 الأصدقاء والمتابعة", "en": "👥 Friends & Following"},
    "btn_rules": {"ar": "📖 قوانين اللعبة", "en": "📖 Game Rules"},
    "btn_language": {"ar": "🌍 تغيير اللغة", "en": "🌍 Change Language"},
    "btn_home": {"ar": "🏠 القائمة الرئيسية", "en": "🏠 Main Menu"},
    "btn_back": {"ar": "🔙 رجوع", "en": "🔙 Back"},

    # --- الخصوصية ---
    "settings_privacy": {
        "ar": "⚙️ إعدادات الخصوصية:\n\n- حساب خاص: {private}\n- السماح بالمشاهدة: {spectate}",
        "en": "⚙️ Privacy Settings:\n\n- Private Account: {private}\n- Allow Spectating: {spectate}",
    },
    "btn_toggle_private": {"ar": "🔒 تبديل حالة الحساب", "en": "🔒 Toggle Private Status"},
    "btn_toggle_spectate": {"ar": "🎥 تبديل ميزة المشاهدة", "en": "🎥 Toggle Spectate"},
    "val_on": {"ar": "مفعل ✅", "en": "ON ✅"},
    "val_off": {"ar": "معطل ❌", "en": "OFF ❌"},

    # --- بقية المفاتيح القديمة (لضمان عمل البوت) ---
    "ask_name": {"ar": "📝 أرسل الاسم الذي تريده:", "en": "📝 Send the name you want:"},
    "name_taken": {"ar": "❌ هذا الاسم مستخدم، اختر اسماً آخر:", "en": "❌ This name is taken:"},
    "ask_password": {"ar": "🔑 أرسل الرمز السري (4 أحرف أو أكثر):", "en": "🔑 Send your secret code:"},
    "register_success": {
        "ar": "✅ تم إنشاء حسابك بنجاح!\n\n📛 الاسم: {name}\n🔑 الرمز السري: {password}",
        "en": "✅ Account created!\n\n📛 Name: {name}\n🔑 Code: {password}",
    },
    "room_created": {
        "ar": "✅ تم إنشاء الغرفة بنجاح!\n{link}",
        "en": "✅ Room created!\n{link}",
    },
    "not_your_turn": {"ar": "مو دورك! ❌", "en": "Not your turn! ❌"},
    "btn_draw": {"ar": "📥 اسحب ورقة", "en": "📥 Draw Card"},
    "btn_uno": {"ar": "🔔 UNO!", "en": "🔔 UNO!"},
    "btn_catch": {"ar": "🚨 إمسك!", "en": "🚨 Catch!"},
    "rules_full": {
        "ar": "📖 قوانين لعبة UNO الكاملة...\n(كما في الكود السابق)",
        "en": "📖 Complete UNO Rules...\n(As in previous code)",
    }
}
