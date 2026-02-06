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
    # 🚨 عملية تنظيف الجداول القديمة (مرة واحدة فقط)
    try:
        db_query("DROP TABLE IF EXISTS calc_players CASCADE;", commit=True)
        db_query("DROP TABLE IF EXISTS creator_id CASCADE;", commit=True)
        print("✅ تم تنظيف الجداول القديمة بنجاح")
    except Exception as e:
        print(f"⚠️ تنبيه: لم يتم مسح الجداول (ربما هي ممسوحة أصلاً): {e}")

    # بناء الجداول من جديد بالمواصفات الصحيحة
    init_db() 
    
    dp = Dispatcher(storage=MemoryStorage())
    
    # ربط الملفات
    dp.include_router(calc.router)
    dp.include_router(common.router)
    dp.include_router(online.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق بنجاح والجداول تحددت!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
