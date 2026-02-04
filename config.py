import os
from aiogram import Bot

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
CHANNEL_ID = os.getenv("CHANNEL_ID")
DB_URL = os.getenv("DATABASE_URL")
IMG_CW = os.getenv("IMG_CW")
IMG_CCW = os.getenv("IMG_CCW")

# تعريف البوت
bot = Bot(token=TOKEN)
