import asyncio
import logging
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import bot
from database import init_db
# استدعاء الهاندلرز (شلت الـ online وضفت الـ rooms)
from handlers import calc, common, stats, admin, room_2p, room_multi

logging.basicConfig(level=logging.INFO)

async def main():
    # 1. تهيئة قاعدة البيانات أولاً
    init_db()

    # 2. إعداد الموزع (Dispatcher) مع ذاكرة مؤقتة للـ States
    dp = Dispatcher(storage=MemoryStorage())

    # 3. ربط الراوترات بالترتيب الصحيح (مهم جداً)
    # خليت الـ common بالبداية حتى أوامر المنيو تشتغل فوراً
    dp.include_router(common.router)
    dp.include_router(room_2p.router)
    dp.include_router(room_multi.router)
    dp.include_router(calc.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)

    print("🚀 البوت انطلق بنجاح والبيانات آمنة!")

    # 4. تنظيف التحديثات المعلقة (عشان ما يدوخ البوت بضغطات قديمة)
    await bot.delete_webhook(drop_pending_updates=True)

    # 5. بدء الاستماع للرسائل
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("❌ تم إيقاف البوت!")
