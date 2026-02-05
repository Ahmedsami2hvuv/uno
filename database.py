import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_URL

# 1. إنشاء الاتصال
def get_conn():
    return psycopg2.connect(DB_URL)

# 2. وظيفة الاستعلام العام (Helper)
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

# 3. تهيئة الجداول وتحديثها تلقائياً
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    
    # إنشاء جدول المستخدمين
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username TEXT)''')
    
    # إنشاء جدول إحصائيات اللاعبين
    cur.execute('''CREATE TABLE IF NOT EXISTS players_stats (
                    user_id BIGINT, 
                    player_name TEXT, 
                    wins INTEGER DEFAULT 0, 
                    games INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, player_name))''')

    # إنشاء جدول السجل
    cur.execute('''CREATE TABLE IF NOT EXISTS games_history (
                    id SERIAL PRIMARY KEY, 
                    user_id BIGINT, 
                    winner TEXT, 
                    duration TEXT, 
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # إنشاء جدول الألعاب الحية (مع الخانات الجديدة للأونو)
    cur.execute('''CREATE TABLE IF NOT EXISTS active_games (
                    game_id SERIAL PRIMARY KEY, 
                    p1_id BIGINT, 
                    p2_id BIGINT,
                    p1_hand TEXT, 
                    p2_hand TEXT, 
                    top_card TEXT, 
                    deck TEXT,
                    turn BIGINT, 
                    status TEXT DEFAULT 'waiting')''')

    # 🛠️ تحديث تلقائي: إضافة أعمدة الأونو إذا كانت مفقودة
    try:
        cur.execute("ALTER TABLE active_games ADD COLUMN IF NOT EXISTS p1_uno BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE active_games ADD COLUMN IF NOT EXISTS p2_uno BOOLEAN DEFAULT FALSE")
    except Exception as e:
        print(f"⚠️ تنبيه: الأعمدة قد تكون موجودة بالفعل: {e}")

    conn.commit()
    cur.close()
    conn.close()
    print("✅ قاعدة البيانات جاهزة ومحدثة بالكامل!")
