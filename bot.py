import asyncio
from aiogram import Bot, Dispatcher
from config import TOKEN
from database import init_db
from handlers import common, calc, online # أضفنا common هنا

async def main():
    init_db() 
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # ربط الملفات المقسمة بالبوت (الترتيب مهم)
    dp.include_router(common.router) # الترحيب أولاً
    dp.include_router(calc.router)
    dp.include_router(online.router)

    print("🚀 البوت يعمل الآن بنظام الملفات المقسمة!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
