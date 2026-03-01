# -*- coding: utf-8 -*-
"""
لوحة إدارة البوت. الأدمن فقط (ADMIN_ID من متغيرات Railway).
في ملف تشغيل البوت (main.py أو bot.py) أضف:
  from handlers import admin
  dp.include_router(admin.router)
"""
import os
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db_query

router = Router(name="admin")

# قراءة أدمن من متغيرات Railway (يمكن أكثر من واحد مفصول بفاصلة)
def _admin_ids():
    raw = os.getenv("ADMIN_ID", "").strip()
    if not raw:
        return set()
    return set(int(x.strip()) for x in raw.split(",") if x.strip().isdigit())

def is_admin(user_id: int) -> bool:
    return user_id in _admin_ids()

def _admin_only(callback_or_message):
    """استخدام كـ: إذا ليس أدمن، أجب وامنع."""
    uid = callback_or_message.from_user.id if hasattr(callback_or_message, "from_user") else callback_or_message.chat.id
    return is_admin(uid)


class AdminStates(StatesGroup):
    broadcast_text = State()
    edit_user_target = State()   # user_id أو username
    edit_user_field = State()    # name / username / password / points
    edit_user_value = State()


# --- /admin وزر القائمة الرئيسية ---
@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await _send_admin_menu(message, message.from_user.id)


@router.callback_query(F.data == "admin_open_panel")
async def admin_open_from_menu(c: types.CallbackQuery, state: FSMContext):
    """فتح لوحة الإدارة من زر «لوحة الإدارة» في القائمة الرئيسية"""
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    await state.clear()
    await _send_admin_menu(c.message, c.from_user.id)
    await c.answer()


def _admin_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 اذاعة بث للجميع", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 عدد اللاعبين وإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 قائمة اللاعبين / بحث وتعديل", callback_data="admin_players")],
        [InlineKeyboardButton(text="🛏 الغرف المفتوحة والمتروكة", callback_data="admin_rooms")],
        [InlineKeyboardButton(text="🔙 إغلاق لوحة الإدارة", callback_data="admin_close")],
    ])


async def _send_admin_menu(target, uid: int, text: str = None):
    msg = text or "⚙️ **لوحة إدارة البوت**\n\nاختر:"
    kb = _admin_menu_kb()
    if isinstance(target, types.Message):
        await target.answer(msg, reply_markup=kb, parse_mode="Markdown")
    else:
        try:
            await target.edit_text(msg, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            await target.message.answer(msg, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "admin_close")
async def admin_close(c: types.CallbackQuery, state: FSMContext):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    await state.clear()
    try:
        await c.message.delete()
    except Exception:
        await c.message.edit_text("✅ تم إغلاق لوحة الإدارة.")
    await c.answer()


@router.callback_query(F.data == "admin_back")
async def admin_back(c: types.CallbackQuery, state: FSMContext):
    if not _admin_only(c):
        return
    await state.clear()
    await _send_admin_menu(c.message, c.from_user.id)
    await c.answer()


# --- اذاعة بث ---
@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(c: types.CallbackQuery, state: FSMContext):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    await state.set_state(AdminStates.broadcast_text)
    await c.message.edit_text(
        "📢 **اذاعة بث**\n\nأرسل النص الذي تريد إرساله لجميع اللاعبين المسجلين.\nلإلغاء أرسل: /cancel"
    , parse_mode="Markdown")
    await c.answer()


@router.message(AdminStates.broadcast_text, F.text)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        return await message.answer("تم الإلغاء.")
    text = message.text or ""
    try:
        rows = db_query("SELECT user_id FROM users WHERE user_id IS NOT NULL")
        total = len(rows) if rows else 0
        sent = 0
        for r in rows or []:
            try:
                await message.bot.send_message(r["user_id"], f"📢 **اذاعة من الإدارة:**\n\n{text}", parse_mode="Markdown")
                sent += 1
            except Exception:
                pass
        await state.clear()
        await message.answer(f"✅ تم إرسال الإذاعة إلى {sent}/{total} لاعب.")
    except Exception as e:
        await message.answer(f"❌ خطأ: {e}")
    await state.clear()


# --- إحصائيات ---
@router.callback_query(F.data == "admin_stats")
async def admin_stats(c: types.CallbackQuery):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    try:
        total = db_query("SELECT COUNT(*) AS c FROM users WHERE user_id IS NOT NULL")
        total = total[0]["c"] if total else 0
        registered = db_query("SELECT COUNT(*) AS c FROM users WHERE is_registered = TRUE")
        registered = registered[0]["c"] if registered else 0
        rooms_open = db_query("SELECT COUNT(*) AS c FROM rooms WHERE status IN ('waiting', 'playing')")
        rooms_open = rooms_open[0]["c"] if rooms_open else 0
    except Exception:
        total = registered = rooms_open = 0
    text = (
        f"📊 **إحصائيات البوت**\n\n"
        f"👥 إجمالي المستخدمين: **{total}**\n"
        f"✅ مسجلون (حساب كامل): **{registered}**\n"
        f"🛏 غرف مفتوحة/قيد اللعب: **{rooms_open}**"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_back")]])
    await c.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await c.answer()


# --- قائمة اللاعبين وتعديل ---
PLAYERS_PAGE_SIZE = 15

@router.callback_query(F.data == "admin_players")
async def admin_players_list(c: types.CallbackQuery, state: FSMContext):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    await state.clear()
    try:
        rows = db_query(
            "SELECT user_id, player_name, username_key, COALESCE(online_points, 0) AS online_points FROM users WHERE user_id IS NOT NULL ORDER BY user_id DESC LIMIT %s",
            (PLAYERS_PAGE_SIZE,)
        )
    except Exception:
        rows = []
    kb_rows = []
    if not rows:
        text = "👥 لا يوجد لاعبون مسجلون."
    else:
        text = "👥 **اللاعبون (أول 15)**\nاضغط على لاعب للتعديل أو ابحث برسالة: يوزر أو رقم ايدي\n\n"
        for r in rows:
            name = (r.get("player_name") or "—")[:20]
            uname = r.get("username_key") or "—"
            pts = r.get("online_points") or 0
            uid = r.get("user_id")
            text += f"• {name} | @{uname} | {pts} pts | `{uid}`\n"
        kb_rows = [[InlineKeyboardButton(text=f"✏️ {r.get('player_name', r['user_id'])}", callback_data=f"admin_view_{r['user_id']}")] for r in rows[:10]]
    kb_rows.append([InlineKeyboardButton(text="🔍 بحث برسالة (ايدي أو يوزر)", callback_data="admin_search_ask")])
    kb_rows.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_back")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="Markdown")
    await c.answer()


@router.callback_query(F.data == "admin_search_ask")
async def admin_search_ask(c: types.CallbackQuery, state: FSMContext):
    if not _admin_only(c):
        return
    await state.set_state(AdminStates.edit_user_target)
    await state.update_data(admin_action="search")
    await c.message.edit_text("🔍 أرسل **رقم الايدي** (user_id) أو **اليوزر نيم** (بدون @) للاعب الذي تريد عرضه/تعديله.\nلإلغاء: /cancel", parse_mode="Markdown")
    await c.answer()


@router.message(AdminStates.edit_user_target, F.text)
async def admin_search_or_edit_target(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        return await message.answer("تم الإلغاء.")
    raw = (message.text or "").strip().replace("@", "")
    try:
        if raw.isdigit():
            user = db_query("SELECT * FROM users WHERE user_id = %s", (int(raw),))
        else:
            user = db_query("SELECT * FROM users WHERE username_key = %s", (raw.lower(),))
        if not user:
            return await message.answer("❌ لا يوجد لاعب بهذا الايدي أو اليوزر.")
        user = user[0]
    except Exception:
        return await message.answer("❌ خطأ في البحث.")
    await state.clear()
    await _send_admin_user_detail(message.bot, message.chat.id, user, message.from_user.id)


def _user_detail_text(u: dict) -> str:
    return (
        f"👤 **معلومات اللاعب**\n\n"
        f"🆔 user_id: `{u.get('user_id')}`\n"
        f"📛 الاسم: {u.get('player_name') or '—'}\n"
        f"👤 اليوزر نيم: @{u.get('username_key') or '—'}\n"
        f"🔑 كلمة السر: {u.get('password_key') or u.get('password') or '—'}\n"
        f"⭐ النقاط: {u.get('online_points', 0)}\n"
        f"✅ مسجل: {u.get('is_registered')}\n"
        f"🌐 اللغة: {u.get('language') or 'ar'}"
    )


async def _send_admin_user_detail(bot, chat_id: int, user: dict, admin_uid: int):
    uid = user.get("user_id")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ تعديل الاسم", callback_data=f"admin_ef_name_{uid}")],
        [InlineKeyboardButton(text="✏️ تعديل اليوزر نيم", callback_data=f"admin_ef_username_{uid}")],
        [InlineKeyboardButton(text="✏️ تعديل كلمة السر", callback_data=f"admin_ef_password_{uid}")],
        [InlineKeyboardButton(text="✏️ تعديل النقاط", callback_data=f"admin_ef_points_{uid}")],
        [InlineKeyboardButton(text="🔙 رجوع للقائمة", callback_data="admin_players")],
    ])
    await bot.send_message(chat_id, _user_detail_text(user), reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("admin_view_"))
async def admin_view_user(c: types.CallbackQuery, state: FSMContext):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    await state.clear()
    try:
        uid = int(c.data.replace("admin_view_", ""))
        user = db_query("SELECT * FROM users WHERE user_id = %s", (uid,))
        if not user:
            return await c.answer("❌ اللاعب غير موجود.", show_alert=True)
        await c.message.edit_text(_user_detail_text(user[0]), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ تعديل الاسم", callback_data=f"admin_ef_name_{uid}")],
            [InlineKeyboardButton(text="✏️ تعديل اليوزر نيم", callback_data=f"admin_ef_username_{uid}")],
            [InlineKeyboardButton(text="✏️ تعديل كلمة السر", callback_data=f"admin_ef_password_{uid}")],
            [InlineKeyboardButton(text="✏️ تعديل النقاط", callback_data=f"admin_ef_points_{uid}")],
            [InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_players")],
        ]), parse_mode="Markdown")
    except Exception as e:
        await c.answer(f"خطأ: {e}", show_alert=True)
    await c.answer()


@router.callback_query(F.data.startswith("admin_ef_name_"))
@router.callback_query(F.data.startswith("admin_ef_username_"))
@router.callback_query(F.data.startswith("admin_ef_password_"))
@router.callback_query(F.data.startswith("admin_ef_points_"))
async def admin_edit_field_ask(c: types.CallbackQuery, state: FSMContext):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    parts = c.data.split("_")
    if len(parts) < 4:
        return await c.answer()
    field = parts[2]  # name / username / password / points
    try:
        target_uid = int(parts[3])
    except ValueError:
        return await c.answer("خطأ في الايدي.", show_alert=True)
    await state.set_state(AdminStates.edit_user_value)
    await state.update_data(admin_edit_uid=target_uid, admin_edit_field=field)
    prompts = {
        "name": "أرسل **الاسم الجديد** للاعب:",
        "username": "أرسل **اليوزر نيم الجديد** (بدون @، إنجليزي وأرقام):",
        "password": "أرسل **كلمة السر الجديدة**:",
        "points": "أرسل **عدد النقاط** (رقم صحيح):",
    }
    await c.message.edit_text(prompts.get(field, "أرسل القيمة الجديدة:") + "\nلإلغاء: /cancel", parse_mode="Markdown")
    await c.answer()


@router.message(AdminStates.edit_user_value, F.text)
async def admin_edit_value_done(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        return await message.answer("تم الإلغاء.")
    data = await state.get_data()
    target_uid = data.get("admin_edit_uid")
    field = data.get("admin_edit_field")
    value = (message.text or "").strip()
    if not value:
        return await message.answer("القيمة فارغة. أعد المحاولة أو /cancel")
    try:
        if field == "name":
            db_query("UPDATE users SET player_name = %s WHERE user_id = %s", (value[:100], target_uid), commit=True)
        elif field == "username":
            db_query("UPDATE users SET username_key = %s WHERE user_id = %s", (value.lower()[:50], target_uid), commit=True)
        elif field == "password":
            db_query("UPDATE users SET password_key = %s WHERE user_id = %s", (value[:100], target_uid), commit=True)
        elif field == "points":
            pts = int(value)
            db_query("UPDATE users SET online_points = %s WHERE user_id = %s", (pts, target_uid), commit=True)
        else:
            await message.answer("حقل غير مدعوم.")
            await state.clear()
            return
    except ValueError:
        await message.answer("❌ النقاط يجب أن تكون رقماً صحيحاً.")
        return
    except Exception as e:
        await message.answer(f"❌ خطأ: {e}")
        await state.clear()
        return
    await state.clear()
    await message.answer(f"✅ تم تحديث **{field}** للاعب {target_uid}.")


# --- الغرف المفتوحة والمتروكة ---
@router.callback_query(F.data == "admin_rooms")
async def admin_rooms_list(c: types.CallbackQuery, skip_answer: bool = False):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    try:
        # غرف waiting أو playing. إذا أضفت عمود created_at لجدول rooms يمكن فلترة المتروكة > 24 ساعة
        rooms = db_query("""
            SELECT r.room_id, r.creator_id, r.status, r.max_players, r.score_limit,
                   (SELECT COUNT(*) FROM room_players rp WHERE rp.room_id = r.room_id) AS p_count
            FROM rooms r
            WHERE r.status IN ('waiting', 'playing')
            ORDER BY r.room_id
            LIMIT 50
        """)
    except Exception:
        rooms = []
    if not rooms:
        text = "🛏 لا توجد غرف مفتوحة حالياً."
        kb = [[InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_back")]]
    else:
        text = "🛏 **الغرف المفتوحة**\n(اضغط على غرفة لإغلاقها)\n\n"
        for r in rooms[:25]:
            code = r.get("room_id", "")
            cnt = r.get("p_count") or 0
            mx = r.get("max_players") or 0
            st = r.get("status") or ""
            text += f"• `{code}` | {cnt}/{mx} | {st}\n"
        kb = []
        for r in rooms[:15]:
            kb.append([InlineKeyboardButton(text=f"🚪 إغلاق {r['room_id']}", callback_data=f"admin_closeroom_{r['room_id']}")])
        kb.append([InlineKeyboardButton(text="🗑 إغلاق كل الغرف المفتوحة", callback_data="admin_closeallrooms")])
        kb.append([InlineKeyboardButton(text="⏳ إغلاق المتروكة فقط (>24 ساعة)", callback_data="admin_closeabandoned")])
        kb.append([InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_back")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    if not skip_answer:
        await c.answer()


@router.callback_query(F.data.startswith("admin_closeroom_"))
async def admin_close_one_room(c: types.CallbackQuery):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    room_id = c.data.replace("admin_closeroom_", "").strip()
    try:
        db_query("DELETE FROM room_players WHERE room_id = %s", (room_id,), commit=True)
        db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
        await c.answer(f"✅ تم إغلاق الغرفة {room_id}.", show_alert=True)
    except Exception as e:
        await c.answer(f"خطأ: {e}", show_alert=True)
    await admin_rooms_list(c, skip_answer=True)


@router.callback_query(F.data == "admin_closeallrooms")
async def admin_close_all_rooms(c: types.CallbackQuery):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    try:
        rooms = db_query("SELECT room_id FROM rooms WHERE status IN ('waiting', 'playing')")
        count = 0
        for r in (rooms or []):
            rid = r.get("room_id")
            db_query("DELETE FROM room_players WHERE room_id = %s", (rid,), commit=True)
            db_query("DELETE FROM rooms WHERE room_id = %s", (rid,), commit=True)
            count += 1
        await c.answer(f"✅ تم إغلاق {count} غرفة.", show_alert=True)
    except Exception as e:
        await c.answer(f"خطأ: {e}", show_alert=True)
    await admin_rooms_list(c, skip_answer=True)


@router.callback_query(F.data == "admin_closeabandoned")
async def admin_close_abandoned(c: types.CallbackQuery):
    if not _admin_only(c):
        return await c.answer("⛔ غير مسموح.", show_alert=True)
    try:
        rooms = db_query("""
            SELECT room_id FROM rooms
            WHERE status IN ('waiting', 'playing')
            AND created_at < NOW() - INTERVAL '24 hours'
        """)
    except Exception:
        try:
            rooms = db_query("""
                SELECT room_id FROM rooms
                WHERE status IN ('waiting', 'playing')
                AND created_at < DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """)
        except Exception:
            await c.answer("⚠️ أضف عمود created_at لجدول rooms لتفعيل إغلاق المتروكة (انظر schema_additions.sql).", show_alert=True)
            return
    if not rooms:
        await c.answer("لا توجد غرف متروكة أكثر من 24 ساعة.", show_alert=True)
        await admin_rooms_list(c, skip_answer=True)
        return
    count = 0
    for r in rooms:
        rid = r.get("room_id")
        db_query("DELETE FROM room_players WHERE room_id = %s", (rid,), commit=True)
        db_query("DELETE FROM rooms WHERE room_id = %s", (rid,), commit=True)
        count += 1
    await c.answer(f"✅ تم إغلاق {count} غرفة متروكة.", show_alert=True)
    await admin_rooms_list(c, skip_answer=True)
