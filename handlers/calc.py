from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import bot, IMG_CW, IMG_CCW
from database import db_query

router = Router()

# --- تعريف حالات الحاسبة ---
class CalcStates(StatesGroup):
    wait_players = State()
    wait_points = State()

# --- 1. بدء الحاسبة ---
@router.callback_query(F.data == "mode_calc")
async def start_calc(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "📝 **حاسبة أونو اليدوية**\n\nأرسل أسماء اللاعبين مفصولة بفاصلة أو مسافة.\nمثال: `علي، محمد، سجاد`",
        parse_mode="Markdown"
    )
    await state.set_state(CalcStates.wait_players)

# --- 2. استقبال الأسماء وإنشاء الجدول ---
@router.message(CalcStates.wait_players)
async def get_players(message: types.Message, state: FSMContext):
    names = message.text.replace("،", " ").replace(",", " ").split()
    if len(names) < 2:
        return await message.answer("⚠️ لازم على الأقل لاعبين اثنين! أرسل الأسماء مرة ثانية:")

    game_data = {
        "players": {name: 0 for name in names},
        "history": [],
        "direction": "CW", # CW = مع عقارب الساعة، CCW = عكس
    }
    await state.update_data(game_data=game_data)
    await send_calc_interface(message, state)

# --- 3. واجهة التحكم بالحاسبة ---
async def send_calc_interface(message, state: FSMContext, extra_msg=""):
    data = await state.get_data()
    game = data['game_data']
    
    # بناء نص الجدول
    table = "📊 **نتائج الجلسة الحالية:**\n"
    table += "━━━━━━━━━━━━━━\n"
    for name, score in game['players'].items():
        table += f"👤 {name}: `{score}`\n"
    table += "━━━━━━━━━━━━━━\n"
    table += f"🔄 الاتجاه الحالي: {'مع عقارب الساعة ➡️' if game['direction'] == 'CW' else 'عكس عقارب الساعة ⬅️'}\n"
    if extra_msg: table += f"\n📢 {extra_msg}"

    kb = [
        [InlineKeyboardButton(text="➕ إضافة نقاط جولة", callback_data="add_round")],
        [InlineKeyboardButton(text="🔄 تغيير الاتجاه", callback_data="toggle_dir")],
        [InlineKeyboardButton(text="🔙 تراجع", callback_data="undo_calc"), 
         InlineKeyboardButton(text="🏁 إنهاء الجلسة", callback_data="finish_calc")]
    ]
    
    # إرسال الصورة حسب الاتجاه
    img = IMG_CW if game['direction'] == "CW" else IMG_CCW
    
    # حذف الرسالة القديمة إذا أمكن لإبقاء الدردشة نظيفة
    try: await message.delete()
    except: pass

    await bot.send_photo(
        message.chat.id, 
        photo=img, 
        caption=table, 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )

# --- 4. تغيير الاتجاه ---
@router.callback_query(F.data == "toggle_dir")
async def toggle_direction(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data['game_data']
    game['direction'] = "CCW" if game['direction'] == "CW" else "CW"
    await state.update_data(game_data=game)
    await send_calc_interface(callback.message, state, "تم تغيير الاتجاه!")

# --- 5. إضافة نقاط الجولة ---
@router.callback_query(F.data == "add_round")
async def prompt_points(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    players = list(data['game_data']['players'].keys())
    await callback.message.answer(
        f"📥 أرسل نقاط اللاعبين بالترتيب مفصولة بمسافة:\n`{' '.join(players)}`",
        parse_mode="Markdown"
    )
    await state.set_state(CalcStates.wait_points)

@router.message(CalcStates.wait_points)
async def process_points(message: types.Message, state: FSMContext):
    points = message.text.split()
    data = await state.get_data()
    game = data['game_data']
    players_list = list(game['players'].keys())

    if len(points) != len(players_list):
        return await message.answer(f"⚠️ خطأ! لازم ترسل {len(players_list)} أرقام. جرب مرة ثانية:")

    try:
        round_data = {}
        for i, p_name in enumerate(players_list):
            pts = int(points[i])
            game['players'][p_name] += pts
            round_data[p_name] = pts
        
        game['history'].append(round_data)
        await state.update_data(game_data=game)
        await send_calc_interface(message, state, "✅ تمت إضافة الجولة!")
    except ValueError:
        await message.answer("⚠️ أرسل أرقام فقط!")

# --- 6. التراجع عن آخر جولة ---
@router.callback_query(F.data == "undo_calc")
async def undo_round(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data['game_data']
    
    if not game['history']:
        return await callback.answer("ماكو جولات للتراجع عنها!", show_alert=True)
    
    last_round = game['history'].pop()
    for name, pts in last_round.items():
        game['players'][name] -= pts
    
    await state.update_data(game_data=game)
    await send_calc_interface(callback.message, state, "⏪ تم التراجع عن آخر جولة.")

# --- 7. إنهاء الجلسة ---
@router.callback_query(F.data == "finish_calc")
async def finish_game(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    game = data['game_data']
    
    # تحديد الفائز (صاحب أقل نقاط)
    winner = min(game['players'], key=game['players'].get)
    
    summary = "🏁 **انتهت اللعبة!**\n\n"
    for name, score in game['players'].items():
        status = "🏆 فائز" if name == winner else "💀 خاسر"
        summary += f"👤 {name}: `{score}` ({status})\n"
    
    await callback.message.delete()
    await callback.message.answer(summary, parse_mode="Markdown")
    
    # أزرار العودة
    kb = [[InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")]]
    await callback.message.answer("ماذا تريد أن تفعل الآن؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()
