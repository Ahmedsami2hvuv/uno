import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_URL

# إنشاء الاتصال
def get_conn():
    return psycopg2.connect(DB_URL)

# الدالة التي سببت الخطأ (db_query) - تأكد من وجودها بهذا الاسم
def db_query(query, params=(), commit=False, fetch=True):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(query, params)
        res = cur.fetchall() if fetch else None
        if commit:
            conn.commit()
        return res
    except Exception as e:
        print(f"❌ خطأ في الاستعلام: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# تهيئة الجداول بنظام الحسابات الجديد
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    
    # 1. جدول المستخدمين (نظام التسجيل)
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username TEXT,
                    player_name TEXT,
                    password TEXT,
                    online_points INTEGER DEFAULT 0,
                    is_registered BOOLEAN DEFAULT FALSE)''')
    
    # 2. جدول الألعاب الحية
    cur.execute('''CREATE TABLE IF NOT EXISTS active_games (
                    game_id SERIAL PRIMARY KEY, 
                    p1_id BIGINT, p2_id BIGINT,
                    p1_hand TEXT, p2_hand TEXT, 
                    top_card TEXT, deck TEXT,
                    turn BIGINT, status TEXT DEFAULT 'waiting',
                    p1_uno BOOLEAN DEFAULT FALSE, p2_uno BOOLEAN DEFAULT FALSE)''')

    # تحديث تلقائي لإضافة أعمدة الأونو والحسابات في حال عدم وجودها
    columns = [
        ("users", "player_name", "TEXT"),
        ("users", "password", "TEXT"),
        ("users", "online_points", "INTEGER DEFAULT 0"),
        ("users", "is_registered", "BOOLEAN DEFAULT FALSE")
    ]
    for table, col, dtype in columns:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {dtype}")
        except: pass

    conn.commit()
    cur.close()
    conn.close()
    print("✅ قاعدة البيانات جاهزة ومحدثة بنظام الحسابات!")
