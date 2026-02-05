import os
from aiogram import Bot

# 1. الإعدادات الأساسية
TOKEN = os.getenv("BOT_TOKEN") # تأكد إذا كان الاسم في ريلوي BOT_TOKEN أو TOKEN
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
CHANNEL_ID = os.getenv("CHANNEL_ID")
DB_URL = os.getenv("DATABASE_URL")

# 2. صور نظام اتجاه اللعب (الحاسبة)
IMG_CW = os.getenv("IMG_CW")
IMG_CCW = os.getenv("IMG_CCW")

# 3. صور نظام الأونو (إضافة جديدة)
# وضعنا "123" كقيمة افتراضية لكي يشتغل البوت وتستخرج الأكواد براحتك
IMG_UNO_SAFE_ME = os.getenv("IMG_UNO_SAFE_ME", "123")
IMG_UNO_SAFE_OPP = os.getenv("IMG_UNO_SAFE_OPP", "123")
IMG_CATCH_SUCCESS = os.getenv("IMG_CATCH_SUCCESS", "123")
IMG_CATCH_PENALTY = os.getenv("IMG_CATCH_PENALTY", "123")

# تعريف البوت
bot = Bot(token=TOKEN)
