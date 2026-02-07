import psycopg2
from psycopg2.extras import RealDictCursor
import os

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
    
    # 2. جدول الغرف
    cur.execute('''CREATE TABLE IF NOT EXISTS rooms (
                    room_id VARCHAR(10) PRIMARY KEY,
                    creator_id BIGINT,
                    max_players INT,
                    score_limit INT,
                    status VARCHAR(20) DEFAULT 'waiting',
                    game_mode VARCHAR(20) DEFAULT 'solo',
                    top_card VARCHAR(50),
                    deck TEXT,
                    turn_index INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # 3. جدول اللاعبين
    cur.execute('''CREATE TABLE IF NOT EXISTS room_players (
                    room_id VARCHAR(10),
                    user_id BIGINT,
                    player_name VARCHAR(100),
                    hand TEXT,
                    points INT DEFAULT 0,
                    join_order SERIAL,
                    last_msg_id BIGINT,
                    PRIMARY KEY (room_id, user_id))''')

    # أوامر تحديث الأعمدة
    try:
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS last_msg_id BIGINT;")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS hand TEXT;")
    except:
        pass

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database Cleaned and Ready!")

if __name__ == "__main__":
    init_db()
else:
    init_db()
