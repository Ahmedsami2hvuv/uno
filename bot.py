import asyncio
import logging
from aiogram import Dispatcher
from config import bot
from database import init_db
from handlers import common, calc, online, stats, admin

logging.basicConfig(level=logging.INFO)

async def main():
    init_db()
    dp = Dispatcher()
    
    # ربط المجلدات
    dp.include_router(common.router)
    dp.include_router(calc.router)
    dp.include_router(online.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق بنجاح!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
