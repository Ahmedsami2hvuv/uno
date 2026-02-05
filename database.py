def init_db():
    conn = get_conn()
    cur = conn.cursor()
    
    # تحديث جدول المستخدمين ليشمل الاسم والرمز والنقاط
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username TEXT,
                    player_name TEXT,
                    password TEXT,
                    online_points INTEGER DEFAULT 0,
                    is_registered BOOLEAN DEFAULT FALSE)''')
    
    # بقية الجداول (active_games, players_stats, etc.) تبقى كما هي
    # ... (تأكد من وجود الكود السابق للجداول الأخرى هنا)
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ قاعدة البيانات محدثة بنظام الحسابات!")
