import asyncio
import logging
from aiogram import Dispatcher
from config import bot, TOKEN
from database import init_db
from handlers import common, calc, online, stats, admin

logging.basicConfig(level=logging.INFO)

async def main():
    print("📢 محاولة تشغيل البوت...")
    if "123456789" in bot.token:
        print("🛑 توقف التشغيل: التوكن غير صحيح أو مفقود!")
        return

    init_db()
    dp = Dispatcher()

    dp.include_router(common.router)
    dp.include_router(calc.router)
    dp.include_router(online.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("✅ البوت متصل الآن بنجاح!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
