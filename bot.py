import asyncio
import logging
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import bot
from database import init_db
from handlers import calc, common, online, stats, admin

logging.basicConfig(level=logging.INFO)

async def main():
    init_db()
    # الذاكرة ضرورية جداً للحاسبة
    dp = Dispatcher(storage=MemoryStorage())
    
    # الترتيب: الحاسبة أولاً لضمان عدم ضياع الرسائل النصية
    dp.include_router(calc.router)
    dp.include_router(common.router)
    dp.include_router(online.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق بنجاح!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
