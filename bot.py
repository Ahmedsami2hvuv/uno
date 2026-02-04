import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# إعدادات البوت
TOKEN = "YOUR_BOT_TOKEN"
CHANNEL_ID = "@YOUR_CHANNEL" # معرف قناتك
ADMIN_ID = 12345678 # أيدي المطور

bot = Bot(token=TOKEN)
dp = Dispatcher()

# قيم الأوراق كما طلبت
CARD_VALUES = {
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "0": 0,
    "+1": 10, "+2": 20, "+4": 50, "منع": 20, "تحويل": 20, "ملونة": 50
}

# حالات البوت (FSM)
class GameState(StatesGroup):
    waiting_for_names = State()
    waiting_for_limit = State()
    in_game = State()
    confirm_end = State()
    choosing_winner = State()
    entering_points = State()

# --- دالة التحقق من الاشتراك ---
async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# --- بداية البوت ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer(f"عذراً! يجب عليك الاشتراك في القناة أولاً لتتمكن من استخدام البوت:\n{CHANNEL_ID}")
        return
    
    await message.answer("مرحباً بك في بوت حاسبة أونو الاحترافي! 🃏\nأدخل أسماء اللاعبين مفصولة بفاصلة (مثال: أحمد, علي, سجاد):")
    return GameState.waiting_for_names

# --- معالجة الأسماء ---
@dp.message(GameState.waiting_for_names)
async def process_names(message: types.Message, state: FSMContext):
    names = [n.strip() for n in message.text.split(",")]
    await state.update_data(players=names, scores={name: 0 for name in names}, games_count=0)
    
    # اختيار الحد الأقصى للنقاط
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="150", callback_data="limit_150"),
         InlineKeyboardButton(text="300", callback_data="limit_300"),
         InlineKeyboardButton(text="500", callback_data="limit_500")]
    ])
    await message.answer("اختر سقف النقاط لإنهاء اللعبة:", reply_markup=kb)
    await state.set_state(GameState.waiting_for_limit)

# --- منطق اتجاه اللعب (الصورة والتحويل) ---
@dp.callback_query(F.data.startswith("limit_"))
async def set_limit(callback: types.CallbackQuery, state: FSMContext):
    limit = int(callback.data.split("_")[1])
    await state.update_data(limit=limit, direction="clockwise") # اتجاه الساعة
    
    await send_direction_msg(callback.message, "clockwise")
    await state.set_state(GameState.in_game)

async def send_direction_msg(message, direction):
    img_url = "URL_IMAGE_CLOCKWISE" if direction == "clockwise" else "URL_IMAGE_COUNTER"
    text = "🔄 اتجاه اللعب الحالي: مع عقارب الساعة" if direction == "clockwise" else "🔄 اتجاه اللعب الحالي: عكس عقارب الساعة"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 تحويل الاتجاه", callback_data="toggle_dir")],
        [InlineKeyboardButton(text="🏁 إنهاء الجولة", callback_data="pre_end_round")]
    ])
    
    # هنا ترسل الصورة (استبدل URL_IMAGE بروابط حقيقية)
    await message.answer_photo(photo=img_url, caption=text, reply_markup=kb)

# --- زر تحويل الاتجاه ---
@dp.callback_query(F.data == "toggle_dir")
async def toggle_direction(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new_dir = "counter" if data['direction'] == "clockwise" else "clockwise"
    await state.update_data(direction=new_dir)
    await callback.message.delete()
    await send_direction_msg(callback.message, new_dir)

# --- تأكيد إنهاء الجولة ---
@dp.callback_query(F.data == "pre_end_round")
async def pre_end(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ نعم، متأكد", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ لا، أكمل اللعب", callback_data="confirm_no")]
    ])
    await callback.message.answer("هل أنت متأكد من إنهاء هذه الجولة؟", reply_markup=kb)

@dp.callback_query(F.data == "confirm_no")
async def continue_game(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.delete()
    await send_direction_msg(callback.message, data['direction'])

# --- اختيار الفائز وإدخال النقاط ---
@dp.callback_query(F.data == "confirm_yes")
async def start_scoring(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"winner_{name}")] for name in data['players']
    ])
    await callback.message.edit_text("من هو اللاعب الفائز في هذه الجولة؟", reply_markup=kb)

# --- لوحة أزرار الأرقام والأوراق ---
def get_cards_keyboard():
    buttons = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["0", "+1", "+2"],
        ["+4", "منع", "تحويل"],
        ["ملونة", "تم ✅"]
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn, callback_data=f"card_{btn}") for btn in row] for row in buttons
    ])

# يتم إكمال بقية المنطق هنا (جمع النقاط، تحديث الصح، التحقق من الفوز النهائي)
