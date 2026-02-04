import asyncio
from aiogram import Bot, Dispatcher
from config import TOKEN
from database import init_db
from handlers import calc, online # استيراد الملفات المقسمة

async def main():
    init_db() # تشغيل الداتا بيس
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # ربط الملفات المقسمة بالبوت
    dp.include_router(calc.router)
    dp.include_router(online.router)

    print("🚀 البوت يعمل الآن بنظام الملفات المقسمة!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
