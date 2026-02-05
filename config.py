import os
from aiogram import Bot

# جلب المتغيرات مع التأكد من الأسماء في ريلوي
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
DB_URL = os.getenv("DATABASE_URL")

# صور الحاسبة
IMG_CW = os.getenv("IMG_CW", "123")
IMG_CCW = os.getenv("IMG_CCW", "123")

# صور الأونو
IMG_UNO_SAFE_ME = os.getenv("IMG_UNO_SAFE_ME", "123")
IMG_UNO_SAFE_OPP = os.getenv("IMG_UNO_SAFE_OPP", "123")
IMG_CATCH_SUCCESS = os.getenv("IMG_CATCH_SUCCESS", "123")
IMG_CATCH_PENALTY = os.getenv("IMG_CATCH_PENALTY", "123")

# فحص التوكن قبل التشغيل لتجنب الانهيار الصامت
if not TOKEN:
    print("❌ خطأ: لم يتم العثور على BOT_TOKEN في متغيرات ريلوي!")
    # قيمة وهمية فقط لمنع الانهيار عند البناء (Build)
    bot = Bot(token="123456789:ABCDEF") 
else:
    bot = Bot(token=TOKEN)
