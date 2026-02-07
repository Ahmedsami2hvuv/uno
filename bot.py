import asyncio
import logging
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import bot
from database import init_db, db_query
from handlers import calc, common, online, stats, admin

logging.basicConfig(level=logging.INFO)

async def main():
    # تهيئة قاعدة البيانات
    init_db()
    
    dp = Dispatcher(storage=MemoryStorage())
    
    # ربط الراوترات
    dp.include_router(calc.router)
    dp.include_router(common.router)
    dp.include_router(online.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق بنجاح والبيانات آمنة!")
    
    # تخطي التحديثات القديمة (هذا السطر راح يخلي البوت ينسى الضغطات القديمة وينطق من جديد)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
