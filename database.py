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
    # 1. جدول المستخدمين
    db_query('''CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, 
                username TEXT,
                player_name TEXT, 
                online_points INTEGER DEFAULT 0)''', commit=True)
    
    # 2. جدول الألعاب (تمت إضافة خانات p1_last_msg و p2_last_msg)
    db_query('''CREATE TABLE IF NOT EXISTS active_games (
                game_id SERIAL PRIMARY KEY, 
                p1_id BIGINT, 
                p2_id BIGINT,
                p1_hand TEXT, 
                p2_hand TEXT, 
                top_card TEXT, 
                deck TEXT, 
                turn BIGINT, 
                status TEXT DEFAULT 'waiting',
                p1_uno BOOLEAN DEFAULT FALSE,
                p2_uno BOOLEAN DEFAULT FALSE,
                p1_last_msg BIGINT DEFAULT 0,
                p2_last_msg BIGINT DEFAULT 0)''', commit=True)

    # 3. تحديثات أمان (تنفذ في حال كان الجدول موجود مسبقاً لضمان وجود الخانات)
    db_query("ALTER TABLE active_games ADD COLUMN IF NOT EXISTS p1_last_msg BIGINT DEFAULT 0;", commit=True)
    db_query("ALTER TABLE active_games ADD COLUMN IF NOT EXISTS p2_last_msg BIGINT DEFAULT 0;", commit=True)
    db_query("ALTER TABLE active_games ADD COLUMN IF NOT EXISTS p1_uno BOOLEAN DEFAULT FALSE;", commit=True)
    db_query("ALTER TABLE active_games ADD COLUMN IF NOT EXISTS p2_uno BOOLEAN DEFAULT FALSE;", commit=True)
    
    print("✅ قاعدة البيانات جاهزة ومحدثة بنظام ذاكرة الرسائل!")

# تشغيل التهيئة عند استيراد الملف
if __name__ == "__main__":
    init_db()
