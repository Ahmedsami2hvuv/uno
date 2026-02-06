import asyncio
import logging
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import bot
# أضفنا db_query هنا حتى البوت يتعرف عليها
from database import init_db, db_query 
from handlers import calc, common, online, stats, admin

logging.basicConfig(level=logging.INFO)

async def main():
    # تأكد إن أسطر الـ DROP TABLE ممسوحة من هنا 🗑️
    
    init_db() # هذا السطر يبني الجداول فقط إذا كانت ممسوحة، وما يأثر على البيانات الموجودة
    
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(calc.router)
    dp.include_router(common.router)
    dp.include_router(online.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق بنجاح والبيانات آمنة!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
