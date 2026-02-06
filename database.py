import psycopg2
from psycopg2.extras import RealDictCursor
import os

# جلب رابط قاعدة البيانات من إعدادات السيرفر
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def db_query(sql, params=(), commit=False):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, params)
        if commit:
            conn.commit()
            return True
        return cur.fetchall()
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    
    # 1. جدول مستخدمي البوت
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username TEXT,
                    player_name TEXT, 
                    online_points INTEGER DEFAULT 0)''')
    
    # 2. جدول ألعاب الأونلاين (مع إضافة أعمدة مسح الرسائل)
    cur.execute('''CREATE TABLE IF NOT EXISTS active_games (
                    game_id SERIAL PRIMARY KEY, 
                    p1_id BIGINT, p2_id BIGINT,
                    p1_hand TEXT, p2_hand TEXT, 
                    top_card TEXT, turn BIGINT, 
                    status TEXT DEFAULT 'waiting',
                    p1_uno BOOLEAN DEFAULT FALSE,
                    p2_uno BOOLEAN DEFAULT FALSE)''')

    # --- تحديث الجدول لإضافة خانات مسح الرسائل إذا لم تكن موجودة ---
    try:
        cur.execute("ALTER TABLE active_games ADD COLUMN IF NOT EXISTS p1_last_msg BIGINT;")
        cur.execute("ALTER TABLE active_games ADD COLUMN IF NOT EXISTS p2_last_msg BIGINT;")
    except Exception as e:
        print(f"تنبيه: الأعمدة موجودة مسبقاً أو حدث خطأ بسيط: {e}")

    # 3. جدول لاعبي الحاسبة (الذاكرة الخاصة بكل مستخدم)
    cur.execute('''CREATE TABLE IF NOT EXISTS calc_players (
                    id SERIAL PRIMARY KEY,
                    player_name VARCHAR(100),
                    creator_id BIGINT,
                    wins INTEGER DEFAULT 0,
                    total_points INTEGER DEFAULT 0,
                    UNIQUE(player_name, creator_id))''')
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ جداول ريلوي جاهزة ومحدثة بنظام مسح الرسائل!")

# تشغيل التهيئة عند استيراد الملف
if __name__ == "__main__":
    init_db()
