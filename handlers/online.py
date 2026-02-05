import random
from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from database import db_query
from config import bot

router = Router()

class RoomStates(StatesGroup):
    wait_room_code = State()

# زر اللعب العشوائي
@router.callback_query(F.data == "mode_random")
async def start_random(callback: types.CallbackQuery):
    await callback.answer("🔎 جاري البحث عن خصم...")
    # (هنا يوضع كود البحث التلقائي الذي برمجناه سابقاً)
    await callback.message.edit_text("🔎 جاري البحث عن لاعب أونلاين الآن...")

# زر إنشاء غرفة (للعب مع صديق)
@router.callback_query(F.data == "create_room")
async def create_private_room(callback: types.CallbackQuery):
    room_code = random.randint(1000, 9999)
    user_id = callback.from_user.id
    
    # إنشاء اللعبة بوضع 'waiting_room'
    db_query("INSERT INTO active_games (p1_id, status) VALUES (%s, %s)", 
             (user_id, f"room_{room_code}"), commit=True, fetch=False)
    
    await callback.message.edit_text(
        f"🏠 **تم إنشاء غرفتك الخاصة!**\n\n"
        f"كود الغرفة: `{room_code}`\n\n"
        f"أرسل الكود لصديقك، وعليه الضغط على 'دخول غرفة' وكتابة الكود.",
        parse_mode="Markdown"
    )

# زر دخول غرفة
@router.callback_query(F.data == "join_room")
async def ask_room_code(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔢 أرسل كود الغرفة المكون من 4 أرقام:")
    await state.set_state(RoomStates.wait_room_code)

@router.message(RoomStates.wait_room_code)
async def process_room_join(message: types.Message, state: FSMContext):
    code = message.text.strip()
    # البحث عن الغرفة بالكود
    room = db_query("SELECT * FROM active_games WHERE status = %s", (f"room_{code}",))
    
    if not room:
        return await message.answer("❌ الكود خطأ أو الغرفة غير موجودة. جرب مرة أخرى:")
    
    game = room[0]
    if game['p1_id'] == message.from_user.id:
        return await message.answer("⚠️ أنت صاحب الغرفة! انتظر دخول صديقك.")

    # إذا وجد الغرفة، تبدأ اللعبة فوراً
    await message.answer("✅ تم الدخول للغرفة! جاري توزيع الأوراق...")
    await bot.send_message(game['p1_id'], "✅ دخل صديقك للغرفة! بدأت اللعبة.")
    
    # (هنا نضع كود توزيع الورق وبدء اللعبة الفعلي)
    await state.clear()
