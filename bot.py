import asyncio
from aiogram import Dispatcher
from config import bot           # استيراد البوت من الكوفنك
from database import init_db     # استيراد الداتا بيس من ملفها الخاص
from handlers import common, calc, online, admin

async def main():
    # تشغيل قاعدة البيانات عند الانطلاق
    init_db() 
    
    dp = Dispatcher()

    # ربط الملفات المقسمة (الموجهات)
    dp.include_router(common.router)
    dp.include_router(calc.router)
    dp.include_router(online.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق بنجاح وبدون أي أخطاء استيراد!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
