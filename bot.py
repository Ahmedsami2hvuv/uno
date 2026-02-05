import asyncio
import logging
from aiogram import Dispatcher
from config import bot
from database import init_db
from handlers import common, calc, online, stats, admin

# إعداد السجلات لمراقبة الأخطاء
logging.basicConfig(level=logging.INFO)

async def main():
    # 1. تهيئة قاعدة البيانات
    print("⏳ جاري تهيئة قاعدة البيانات...")
    init_db()
    
    # 2. تعريف الموزع
    dp = Dispatcher()

    # 3. ربط ملفات المهام (الرواتر)
    dp.include_router(common.router)   # ملف الترحيب والتسجيل ومستخرج الصور
    dp.include_router(calc.router)     # ملف الحاسبة
    dp.include_router(online.router)   # ملف اللعب أونلاين
    dp.include_router(stats.router)    # ملف المتصدرين
    dp.include_router(admin.router)    # ملف الأدمن

    print("🚀 البوت انطلق الآن! أرسل صورة للحصول على الكود.")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 تم إيقاف البوت.")
