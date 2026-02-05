# 1. دالة معالجة زر الأونو (📢 أونو!)
@router.callback_query(F.data.startswith("u_"))
async def process_uno(callback: types.CallbackQuery):
    g_id = callback.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    is_p1 = (int(callback.from_user.id) == int(game['p1_id']))
    opp_id = game['p2_id'] if is_p1 else game['p1_id']

    # تفعيل حالة الأونو
    db_query(f"UPDATE active_games SET {'p1_uno' if is_p1 else 'p2_uno'}=TRUE WHERE game_id=%s", (g_id,), commit=True)

    # مسح الرسائل القديمة لكل من اللاعبين (اختياري حسب منطق التحديث عندك)
    
    # أ. إرسال الصورة لي (أنا في أمان)
    await bot.send_photo(callback.from_user.id, photo=types.FSInputFile(IMG_UNO_SAFE_ME), 
                         caption="🛡️ لقد نقرت على أونو قبل لعب الورقة.. أنت في أمان ولا يمكن معاقبتك!")

    # ب. إرسال الصورة للخصم (الخصم نادى أونو)
    await bot.send_photo(opp_id, photo=types.FSInputFile(IMG_UNO_SAFE_OPP), 
                         caption="📣 خصمك قال أونو وأمن نفسه.. لا يمكنك معاقبته هذه المرة!")

    await callback.answer()
    # تحديث واجهة اللعب لمسح زر أونو بعد ضغطه
    await send_player_hand(callback.from_user.id, g_id, callback.message.message_id)


# 2. دالة معالجة زر الصيد (🚨 صيده!)
@router.callback_query(F.data.startswith("c_"))
async def process_catch(callback: types.CallbackQuery):
    g_id = callback.data.split("_")[1]
    game = db_query("SELECT * FROM active_games WHERE game_id=%s", (g_id,))[0]
    
    is_p1_catching = (int(callback.from_user.id) == int(game['p1_id']))
    victim_id = game['p2_id'] if is_p1_catching else game['p1_id']
    
    # جلب الأوراق وتطبيق العقوبة
    hand = (game['p2_hand'] if is_p1_catching else game['p1_hand']).split(",")
    deck = game['deck'].split(",")
    hand.extend([deck.pop(0), deck.pop(0)]) # عقوبة ورقتين
    
    db_query(f"UPDATE active_games SET {'p2_hand' if is_p1_catching else 'p1_hand'}=%s, deck=%s WHERE game_id=%s", 
             (",".join(hand), ",".join(deck), g_id), commit=True)

    # أ. إرسال الصورة لي (أنا الذي صدت الخصم)
    await bot.send_photo(callback.from_user.id, photo=types.FSInputFile(IMG_CATCH_SUCCESS), 
                         caption="🎯 أحسنت! لقد نقرت على أونو في الوقت المناسب وتمت معاقبة الخصم!")

    # ب. إرسال الصورة للضحية (الذي نسي الأونو)
    await bot.send_photo(victim_id, photo=types.FSInputFile(IMG_CATCH_PENALTY), 
                         caption="🚨 تم صيدك! لقد لعبت الورقة ولم تقل أونو.. أنت معاقب بسحب ورقتين!")

    await callback.answer()
    # تحديث يد اللاعبين لمشاهدة الأوراق الجديدة المسحوبة بالعقوبة
    await send_player_hand(game['p1_id'], g_id, callback.message.message_id if is_p1_catching else None)
    await send_player_hand(game['p2_id'], g_id, callback.message.message_id if not is_p1_catching else None)
