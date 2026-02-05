import asyncio
import logging
from aiogram import Dispatcher
from config import bot
from database import init_db
from handlers import common, calc, online, stats, admin

# إعداد السجلات (Logs) لمراقبة الأخطاء
logging.basicConfig(level=logging.INFO)

async def main():
    # 1. تهيئة قاعدة البيانات عند التشغيل
    print("⏳ جاري تهيئة قاعدة البيانات...")
    init_db()
    
    # 2. تعريف الموزع (Dispatcher)
    dp = Dispatcher()

    # 3. ربط ملفات المهام (Routers) بالبوت
    # الترتيب مهم جداً لضمان عمل الأوامر بشكل صحيح
    dp.include_router(common.router)   # ملف الترحيب والتسجيل
    dp.include_router(calc.router)     # ملف الحاسبة اليدوية
    dp.include_router(online.router)   # ملف اللعب أونلاين والغرف
    dp.include_router(stats.router)    # ملف المتصدرين والحساب الشخصي
    dp.include_router(admin.router)    # ملف لوحة تحكم الأدمن

    print("🚀 البوت انطلق الآن بنظام الملفات المقسمة الاحترافي!")
    
    # 4. بدء استقبال الرسائل
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 تم إيقاف البوت.")
