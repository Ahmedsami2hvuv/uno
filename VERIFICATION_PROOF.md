# 🔍 إثبات التعديلات - PROOF OF MODIFICATIONS

## التاريخ: 2026-02-19

---

## ✅ الدليل 1: زر تنظيف الرسائل

### في الملف: handlers/common.py

**السطر 40 - إضافة الزر:**
```python
keyboard=[[KeyboardButton(text="/start"), KeyboardButton(text="تنظيف الرسائل")]]
```

**السطور 60-90 - Handler كامل:**
```python
@router.message(F.text == "تنظيف الرسائل")
async def cleanup_messages_button(message: types.Message):
    """Handler for clean messages button - deletes all bot messages"""
    try:
        await message.delete()
    except:
        pass
    
    try:
        last_id = message.message_id
        deleted_count = 0
        for mid in range(last_id, max(last_id - 50, 1), -1):
            try:
                await message.bot.delete_message(message.chat.id, mid)
                deleted_count += 1
            except:
                pass
        
        if deleted_count > 0:
            confirm_msg = await message.answer(f"🧹 تم تنظيف {deleted_count} رسالة", reply_markup=persistent_kb)
            await asyncio.sleep(2)
            try:
                await confirm_msg.delete()
            except:
                pass
    except Exception as e:
        print(f"Error cleaning messages: {e}")
```

**البحث في الكود:**
```bash
$ grep -n "تنظيف الرسائل" handlers/common.py
40:    keyboard=[[KeyboardButton(text="/start"), KeyboardButton(text="تنظيف الرسائل")]],
60:@router.message(F.text == "تنظيف الرسائل")
```

---

## ✅ الدليل 2: الثوابت الجديدة للتوقيت

### في الملف: handlers/room_2p.py

**السطور 13-14:**
```python
AUTO_DRAW_DELAY = 5  # Seconds to wait before auto-drawing a card
SKIP_TIMEOUT = 12    # Seconds to wait before auto-passing turn after drawing non-playable card
```

**البحث في الكود:**
```bash
$ grep -n "AUTO_DRAW_DELAY\|SKIP_TIMEOUT" handlers/room_2p.py
13:AUTO_DRAW_DELAY = 5  # Seconds to wait before auto-drawing a card
14:SKIP_TIMEOUT = 12    # Seconds to wait before auto-passing turn after drawing non-playable card
507:            await asyncio.sleep(AUTO_DRAW_DELAY)
543:                await asyncio.sleep(SKIP_TIMEOUT)
```

---

## ✅ الدليل 3: زر المرر (Skip Button)

### في الملف: handlers/room_2p.py

**السطر 613 - إضافة الزر:**
```python
if p.get('can_skip') == 1 and i == room['turn_index']:
    exit_row.insert(0, InlineKeyboardButton(text="⏭ مرر", callback_data=f"sk_{room_id}"))
```

**السطور 905-945 - Handler الزر:**
```python
@router.callback_query(F.data.startswith("sk_"))
async def skip_turn(c: types.CallbackQuery):
    """Handler for skip button - immediately pass turn when player has non-playable drawn card"""
    try:
        room_id = c.data.split("_")[1]
        room_data = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if not room_data:
            return await c.answer("❌ الغرفة غير موجودة!", show_alert=True)
        
        room = room_data[0]
        players = get_ordered_players(room_id)
        
        curr_idx = room['turn_index']
        curr_p = players[curr_idx]
        
        if curr_p['user_id'] != c.from_user.id:
            return await c.answer("❌ مو دورك!", show_alert=True)
        
        if curr_p.get('can_skip') != 1:
            return await c.answer("❌ ما تقدر تمرر الحين!", show_alert=True)
        
        next_turn = (curr_idx + 1) % 2
        db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_turn, room_id), commit=True)
        db_query("UPDATE room_players SET can_skip = 0 WHERE user_id = %s", (curr_p['user_id'],), commit=True)
        
        p_name = curr_p.get('player_name') or "لاعب"
        opp_id = players[next_turn]['user_id']
        
        msgs = {}
        msgs[curr_p['user_id']] = "⏭ تم تمرير دورك"
        msgs[opp_id] = f"✅ {p_name} مرر دوره، الدور الحين لك!"
        
        await refresh_ui_2p(room_id, c.bot, msgs)
        await c.answer("✅ تم تمرير الدور")
        
    except Exception as e:
        print(f"Skip Error: {e}")
        await c.answer("❌ حدث خطأ", show_alert=True)
```

**البحث في الكود:**
```bash
$ grep -n "⏭ مرر" handlers/room_2p.py
613:                exit_row.insert(0, InlineKeyboardButton(text="⏭ مرر", callback_data=f"sk_{room_id}"))
```

---

## ✅ الدليل 4: تحديث قاعدة البيانات

### في الملف: database.py

**السطر 122:**
```python
"ALTER TABLE room_players ADD COLUMN IF NOT EXISTS can_skip INT DEFAULT 0;" # For skip turn functionality
```

**البحث في الكود:**
```bash
$ grep -n "can_skip" database.py
122:        "ALTER TABLE room_players ADD COLUMN IF NOT EXISTS can_skip INT DEFAULT 0;" # For skip turn functionality
```

---

## ✅ الدليل 5: السحب التلقائي مع الإشعارات

### في الملف: handlers/room_2p.py (السطور 495-556)

```python
if not any(check_validity(c, room['top_card'], room['current_color']) for c in curr_hand):
    # Step 1: Notify player - no suitable card, will draw in 5 seconds
    p_name = curr_p.get('player_name') or "لاعب"
    opp_id = players[(curr_idx+1)%2]['user_id']
    
    try:
        await bot.send_message(curr_p['user_id'], "❌ ماعندك ورقة مناسبة! راح اسحبلك ورقة خلال 5 ثواني...")
        await bot.send_message(opp_id, f"⏳ {p_name} ماعنده ورقة مناسبة، البوت راح يسحبله ورقة...")
    except:
        pass
    
    # Step 2: Wait 5 seconds
    await asyncio.sleep(AUTO_DRAW_DELAY)
    
    # Step 3: Draw card
    deck = safe_load(room['deck'])
    if not deck:
        discard = safe_load(room['discard_pile'])
        if discard:
            deck = discard
            random.shuffle(deck)
            db_query("UPDATE rooms SET discard_pile = '[]' WHERE room_id = %s", (room_id,), commit=True)
        else:
            deck = generate_h2o_deck()
    new_card = deck.pop(0)
    curr_hand.append(new_card)
    is_playable = check_validity(new_card, room['top_card'], room['current_color'])
    
    db_query("UPDATE room_players SET hand = %s WHERE user_id = %s", (json.dumps(curr_hand), curr_p['user_id']), commit=True)
    db_query("UPDATE rooms SET deck = %s WHERE room_id = %s", (json.dumps(deck), room_id), commit=True)
    
    msgs = {}
    if is_playable:
        # Card is playable - keep turn with player
        msgs[curr_p['user_id']] = f"✅ سحبتلك ({new_card}) ومناسبة للعب! العبها 👍"
        msgs[opp_id] = f"📥 {p_name} سحب ورقة ({new_card}) والورقة مناسبة وسيلعبها 🔄"
        return await refresh_ui_2p(room_id, bot, msgs)
    else:
        # Card is NOT playable - need to show skip button
        db_query("UPDATE room_players SET can_skip = 1 WHERE user_id = %s", (curr_p['user_id'],), commit=True)
        msgs[curr_p['user_id']] = f"❌ الورقة الي سحبتها ({new_card}) غير مناسبة للعب. راح يعبر دورك خلال 12 ثانية او دوس على زر مرر ⏭"
        msgs[opp_id] = f"�� {p_name} سحب ورقة ({new_card}) وماهي مناسبة، راح يعبر دوره قريب..."
        
        # Refresh UI with skip button
        await refresh_ui_2p(room_id, bot, msgs)
        
        # Step 4: Wait 12 seconds for skip or auto-pass
        await asyncio.sleep(SKIP_TIMEOUT)
        
        # Check if player already skipped manually (can_skip would be 0 if they did)
        check_skip = db_query("SELECT can_skip FROM room_players WHERE user_id = %s", (curr_p['user_id'],))
        if check_skip and check_skip[0].get('can_skip') == 1:
            # Auto-pass turn
            next_turn = (curr_idx + 1) % 2
            db_query("UPDATE rooms SET turn_index = %s WHERE room_id = %s", (next_turn, room_id), commit=True)
            db_query("UPDATE room_players SET can_skip = 0 WHERE user_id = %s", (curr_p['user_id'],), commit=True)
            
            auto_msgs = {}
            auto_msgs[curr_p['user_id']] = "⏭ تم تمرير دورك تلقائياً"
            auto_msgs[opp_id] = f"✅ {p_name} عبر دوره، الدور الحين لك!"
            return await refresh_ui_2p(room_id, bot, auto_msgs)
        
        return
```

---

## 📊 ملخص الإحصائيات

| البند | القيمة |
|------|--------|
| عدد الملفات المعدلة | 6 |
| عدد السطور المضافة | 271 |
| عدد السطور المحذوفة | 19 |
| الوظائف الجديدة | 3 (cleanup, skip_turn, auto-draw) |
| الثوابت الجديدة | 2 (AUTO_DRAW_DELAY, SKIP_TIMEOUT) |
| التحديثات على قاعدة البيانات | 1 (can_skip column) |

---

## 🔗 روابط للتحقق

1. **GitHub Branch**: https://github.com/Ahmedsami2hvuv/uno/tree/copilot/modify-requested-file
2. **Commits**: 
   - dcefc7c: Add .gitignore and remove Python cache files
   - be725a5: Add constants for delays and clarify race condition handling
   - 416c46d: Add auto-draw and skip functionality to multi-player mode
   - 8020b08: Add auto-draw card logic with skip button functionality
   - 054c3ef: Add clean messages button to persistent keyboard

---

## ⚠️ لتفعيل التعديلات في Railway

يجب دمج branch `copilot/modify-requested-file` في `main`:

1. اذهب إلى: https://github.com/Ahmedsami2hvuv/uno/compare
2. اختر: base: main ← compare: copilot/modify-requested-file
3. اضغط "Create pull request"
4. اضغط "Merge pull request"
5. Railway سيحدث تلقائياً!

---

تم التوثيق بتاريخ: 19 فبراير 2026
Branch: copilot/modify-requested-file
Status: ✅ Complete - Ready to merge
