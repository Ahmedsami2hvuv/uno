import psycopg2
from psycopg2.extras import RealDictCursor
import os
import json

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
                    online_points INTEGER DEFAULT 0,
                    is_registered BOOLEAN DEFAULT FALSE,
                    password TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
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

    # 3. جدول الغرف الخاصة (النظام الجديد) - محدث
    cur.execute('''CREATE TABLE IF NOT EXISTS rooms (
                    room_id VARCHAR(10) PRIMARY KEY,
                    creator_id BIGINT,
                    max_players INT DEFAULT 2,
                    score_limit INT DEFAULT 100,
                    status VARCHAR(20) DEFAULT 'waiting', -- waiting, voting, playing, finished
                    game_mode VARCHAR(10) DEFAULT 'solo', -- solo, team
                    top_card VARCHAR(100),
                    deck TEXT,
                    turn_index INT DEFAULT 0,
                    direction INT DEFAULT 1, -- 1 للأمام, -1 للخلف
                    current_color VARCHAR(10),
                    challenge_active BOOLEAN DEFAULT FALSE,
                    challenge_card TEXT,
                    challenger_index INT,
                    target_index INT,
                    chosen_color VARCHAR(10),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # 4. جدول اللاعبين داخل الغرف - محدث
    cur.execute('''CREATE TABLE IF NOT EXISTS room_players (
                    id SERIAL PRIMARY KEY,
                    room_id VARCHAR(10),
                    user_id BIGINT,
                    player_name VARCHAR(100),
                    join_order INT DEFAULT 0,
                    hand TEXT DEFAULT '[]',
                    points INT DEFAULT 0,
                    team INT DEFAULT 0,
                    vote VARCHAR(10), -- team, solo
                    last_msg_id BIGINT,
                    uno_called BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE,
                    UNIQUE(room_id, user_id))''')

    # 5. إضافة أعمدة إضافية للغرف إذا لم تكن موجودة
    try:
        # أعمدة جدول rooms
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS direction INT DEFAULT 1;")
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS current_color VARCHAR(10);")
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS challenge_active BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS challenge_card TEXT;")
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS challenger_index INT;")
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS target_index INT;")
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS chosen_color VARCHAR(10);")
        
        # أعمدة جدول room_players
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS id SERIAL PRIMARY KEY;")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS join_order INT DEFAULT 0;")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS hand TEXT DEFAULT '[]';")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS points INT DEFAULT 0;")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS team INT DEFAULT 0;")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS vote VARCHAR(10);")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS uno_called BOOLEAN DEFAULT FALSE;")
        cur.execute("ALTER TABLE room_players ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        
    except Exception as e:
        print(f"⚠️ تحديث الأعمدة: {e}")

    # 6. جدول لاعبي الحاسبة
    cur.execute('''CREATE TABLE IF NOT EXISTS calc_players (
                    id SERIAL PRIMARY KEY,
                    player_name VARCHAR(100),
                    creator_id BIGINT,
                    wins INTEGER DEFAULT 0,
                    total_points INTEGER DEFAULT 0,
                    UNIQUE(player_name, creator_id))''')
    
    # 7. جدول لتاريخ المباريات
    cur.execute('''CREATE TABLE IF NOT EXISTS match_history (
                    id SERIAL PRIMARY KEY,
                    room_id VARCHAR(10),
                    winner_id BIGINT,
                    winner_name VARCHAR(100),
                    game_mode VARCHAR(10),
                    score_limit INT,
                    total_players INT,
                    winner_points INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    
    # إنشاء فهارس لتحسين الأداء
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_room_players_room_id ON room_players(room_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_room_players_user_id ON room_players(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rooms_status ON rooms(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rooms_creator ON rooms(creator_id);")
    except Exception as e:
        print(f"⚠️ إنشاء الفهارس: {e}")
    
    cur.close()
    conn.close()
    print("✅ قاعدة البيانات محدثة وجاهزة لنظام الغرف الجديد!")

def cleanup_old_rooms():
    """تنظيف الغرف القديمة التي انتهت من أكثر من 24 ساعة"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # حذف الغرف المنتهية منذ أكثر من 24 ساعة
        cur.execute("""
            DELETE FROM rooms 
            WHERE status = 'finished' 
            AND created_at < NOW() - INTERVAL '24 hours'
        """)
        
        # حذف الغرف المنتظرة منذ أكثر من 2 ساعة
        cur.execute("""
            DELETE FROM rooms 
            WHERE status = 'waiting' 
            AND created_at < NOW() - INTERVAL '2 hours'
        """)
        
        conn.commit()
        print("✅ تم تنظيف الغرف القديمة")
    except Exception as e:
        print(f"❌ خطأ في تنظيف الغرف: {e}")
    finally:
        cur.close()
        conn.close()

def get_player_stats(user_id):
    """الحصول على إحصائيات اللاعب"""
    stats = {
        'games_played': 0,
        'games_won': 0,
        'total_points': 0,
        'win_rate': 0
    }
    
    try:
        # إجمالي المباريات التي لعبها
        result = db_query("""
            SELECT COUNT(*) as count FROM match_history 
            WHERE room_id IN (SELECT room_id FROM room_players WHERE user_id = %s)
        """, (user_id,))
        
        if result and result[0]['count']:
            stats['games_played'] = result[0]['count']
        
        # المباريات التي فاز بها
        result = db_query("""
            SELECT COUNT(*) as count FROM match_history 
            WHERE winner_id = %s
        """, (user_id,))
        
        if result and result[0]['count']:
            stats['games_won'] = result[0]['count']
        
        # حساب معدل الفوز
        if stats['games_played'] > 0:
            stats['win_rate'] = round((stats['games_won'] / stats['games_played']) * 100, 1)
        
        # النقاط الإجمالية
        result = db_query("""
            SELECT online_points FROM users WHERE user_id = %s
        """, (user_id,))
        
        if result and result[0]['online_points']:
            stats['total_points'] = result[0]['online_points']
            
    except Exception as e:
        print(f"❌ خطأ في جلب الإحصائيات: {e}")
    
    return stats

def save_match_history(room_id, winner_id, winner_name, game_mode, score_limit, total_players, winner_points):
    """حفظ تاريخ المباراة"""
    try:
        db_query("""
            INSERT INTO match_history 
            (room_id, winner_id, winner_name, game_mode, score_limit, total_players, winner_points) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (room_id, winner_id, winner_name, game_mode, score_limit, total_players, winner_points), commit=True)
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ تاريخ المباراة: {e}")
        return False

def get_active_rooms_count():
    """الحصول على عدد الغرف النشطة"""
    try:
        result = db_query("""
            SELECT COUNT(*) as count FROM rooms 
            WHERE status IN ('waiting', 'voting', 'playing')
        """)
        return result[0]['count'] if result else 0
    except:
        return 0

def get_room_details(room_id):
    """الحصول على تفاصيل الغرفة"""
    try:
        room = db_query("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        if room:
            players = db_query("""
                SELECT user_id, player_name, points, team, join_order 
                FROM room_players 
                WHERE room_id = %s 
                ORDER BY join_order
            """, (room_id,))
            
            room_details = room[0]
            room_details['players'] = players if players else []
            return room_details
    except Exception as e:
        print(f"❌ خطأ في جلب تفاصيل الغرفة: {e}")
    
    return None

def update_player_hand(room_id, user_id, hand):
    """تحديد يد اللاعب"""
    try:
        return db_query("""
            UPDATE room_players 
            SET hand = %s 
            WHERE room_id = %s AND user_id = %s
        """, (json.dumps(hand), room_id, user_id), commit=True)
    except Exception as e:
        print(f"❌ خطأ في تحديث يد اللاعب: {e}")
        return False

def get_player_hand(room_id, user_id):
    """الحصول على يد اللاعب"""
    try:
        result = db_query("""
            SELECT hand FROM room_players 
            WHERE room_id = %s AND user_id = %s
        """, (room_id, user_id))
        
        if result and result[0]['hand']:
            return json.loads(result[0]['hand'])
    except Exception as e:
        print(f"❌ خطأ في جلب يد اللاعب: {e}")
    
    return []

def add_points_to_player(room_id, user_id, points):
    """إضافة نقاط للاعب في الغرفة"""
    try:
        return db_query("""
            UPDATE room_players 
            SET points = points + %s 
            WHERE room_id = %s AND user_id = %s
        """, (points, room_id, user_id), commit=True)
    except Exception as e:
        print(f"❌ خطأ في إضافة النقاط: {e}")
        return False

def reset_room_game(room_id):
    """إعادة تعيين لعبة الغرفة"""
    try:
        # إعادة تعيين حالة الغرفة
        db_query("""
            UPDATE rooms 
            SET status = 'playing', 
                turn_index = 0, 
                direction = 1, 
                challenge_active = FALSE,
                challenge_card = NULL,
                challenger_index = NULL,
                target_index = NULL,
                chosen_color = NULL
            WHERE room_id = %s
        """, (room_id,), commit=True)
        
        # إعادة تعيين أيدي اللاعبين
        db_query("""
            UPDATE room_players 
            SET hand = '[]', 
                uno_called = FALSE
            WHERE room_id = %s
        """, (room_id,), commit=True)
        
        return True
    except Exception as e:
        print(f"❌ خطأ في إعادة تعيين اللعبة: {e}")
        return False

def cleanup_room(room_id):
    """تنظيف بيانات الغرفة"""
    try:
        # حذف بيانات اللاعبين
        db_query("DELETE FROM room_players WHERE room_id = %s", (room_id,), commit=True)
        
        # حذف الغرفة
        db_query("DELETE FROM rooms WHERE room_id = %s", (room_id,), commit=True)
        
        print(f"✅ تم تنظيف الغرفة: {room_id}")
        return True
    except Exception as e:
        print(f"❌ خطأ في تنظيف الغرفة: {e}")
        return False

# تشغيل التهيئة عند استدعاء الملف
init_db()

# تنظيف الغرف القديمة عند بدء التشغيل
cleanup_old_rooms()
