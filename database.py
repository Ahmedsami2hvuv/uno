import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_URL

def get_conn():
    return psycopg2.connect(DB_URL)

def db_query(query, params=(), commit=False):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    res = None
    try:
        cur.execute(query, params)
        # الفحص الذكي: إذا كان الاستعلام يرجع بيانات (SELECT)
        if cur.description:
            res = cur.fetchall()
        if commit:
            conn.commit()
    except Exception as e:
        print(f"❌ خطأ في الاستعلام: {e}")
        conn.rollback() # تراجع في حال الخطأ لضمان استقرار الداتا بيس
    finally:
        cur.close()
        conn.close()
    return res

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # إنشاء الجداول الأساسية
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, username TEXT,
                    player_name TEXT, password TEXT,
                    online_points INTEGER DEFAULT 0, is_registered BOOLEAN DEFAULT FALSE)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS active_games (
                    game_id SERIAL PRIMARY KEY, p1_id BIGINT, p2_id BIGINT,
                    p1_hand TEXT, p2_hand TEXT, top_card TEXT, deck TEXT,
                    turn BIGINT, status TEXT DEFAULT 'waiting',
                    p1_uno BOOLEAN DEFAULT FALSE, p2_uno BOOLEAN DEFAULT FALSE)''')
    conn.commit()
    cur.close()
    conn.close()
    print("✅ قاعدة البيانات جاهزة وبدون أخطاء!")
