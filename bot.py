import asyncio
from aiogram import Dispatcher
from config import bot, init_db # استيراد البوت والداتا بيس
from handlers import common, calc, online, admin

async def main():
    # إنشاء الجداول إذا لم تكن موجودة
    from database import init_db
    init_db() 
    
    dp = Dispatcher()

    # ربط الملفات المقسمة
    dp.include_router(common.router)
    dp.include_router(calc.router)
    dp.include_router(online.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق بنجاح بدون أخطاء!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
