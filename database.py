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
    
    # 1. جدول المستخدمين
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username TEXT,
                    player_name TEXT, 
                    online_points INTEGER DEFAULT 0,
                    is_registered BOOLEAN DEFAULT FALSE,
                    password TEXT)''')
    
    # 2. جدول ألعاب الأونلاين العشوائية
    cur.execute('''CREATE TABLE IF NOT EXISTS active_games (
                    game_id SERIAL PRIMARY KEY, 
                    p1_id BIGINT, p2_id BIGINT,
                    p1_hand TEXT, p2_hand TEXT, 
                    top_card TEXT, turn BIGINT, 
                    status TEXT DEFAULT 'waiting',
                    p1_uno BOOLEAN DEFAULT FALSE,
                    p2_uno BOOLEAN DEFAULT FALSE,
                    p1_last_msg BIGINT,
                    p2_last_msg BIGINT,
                    deck TEXT)''')

    # 3. جدول الغرف الخاصة (النظام المطور)
    cur.execute('''CREATE TABLE IF NOT EXISTS rooms (
                    room_id VARCHAR(10) PRIMARY KEY,
                    creator_id BIGINT,
                    max_players INT DEFAULT 2,
                    score_limit INT DEFAULT 100,
                    status VARCHAR(20) DEFAULT 'waiting',
                    game_mode VARCHAR(10) DEFAULT 'solo',
                    top_card VARCHAR(100),
                    deck TEXT,
                    turn_index INT DEFAULT 0,
                    current_color VARCHAR(10) DEFAULT '🔴',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # 4. جدول اللاعبين داخل الغرف
    cur.execute('''CREATE TABLE IF NOT EXISTS room_players (
                    room_id VARCHAR(10),
                    user_id BIGINT,
                    player_name VARCHAR(100),
                    hand TEXT DEFAULT '[]',
                    points INT DEFAULT 0,
                    team INT DEFAULT 0,
                    join_order SERIAL,
                    last_msg_id BIGINT,
                    PRIMARY KEY (room_id, user_id),
                    FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE)''')

    # 🚨 تحديث الأعمدة إذا كانت الجداول موجودة مسبقاً
    try:
        # لجدول الغرف
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS current_color VARCHAR(10) DEFAULT '🔴';")
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS game_mode VARCHAR(10) DEFAULT 'solo';")
        # لجدول لاعبين الغرف
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS team INT DEFAULT 0;")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS last_msg_id BIGINT;")
    except:
        pass

    # 5. جدول لاعبي الحاسبة
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
    print("✅ الداتا بيس جاهزة للنظام المستقر + الفرق + الألوان!")

init_db()
