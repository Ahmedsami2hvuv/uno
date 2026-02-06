import asyncio
import logging
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import bot
from database import init_db
from handlers import calc, common, online, stats, admin

logging.basicConfig(level=logging.INFO)

async def main():
    # 🚨 سطر المسح القسري (ضفناه هنا)
    db_query("DROP TABLE IF EXISTS calc_players CASCADE;", commit=True)
    db_query("DROP TABLE IF EXISTS creator_id CASCADE;", commit=True)
    
    init_db() # البوت راح يرجع يبني جدول calc_players بالمواصفات الصح
    
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(calc.router)
    dp.include_router(common.router)
    dp.include_router(online.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("🚀 تم مسح الجداول القديمة وبناء الجديدة.. انطلق!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
