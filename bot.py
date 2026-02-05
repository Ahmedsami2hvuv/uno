import asyncio
import logging
from aiogram import Dispatcher, types, F
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

    # --- ميزة مستخرج أكواد الصور (إضافة جديدة) ---
    @dp.message(F.photo)
    async def get_image_id(message: types.Message):
        # نأخذ آخر صورة (تكون بأعلى دقة)
        file_id = message.photo[-1].file_id
        await message.reply(f"✅ كود الصورة (File ID):\n\n`{file_id}`", parse_mode="MarkdownV2")
    # -------------------------------------------

    # 3. ربط ملفات المهام (Routers) بالبوت
    dp.include_router(common.router)
    dp.include_router(calc.router)
    dp.include_router(online.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق الآن! أرسل أي صورة للحصول على كودها.")
    
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
