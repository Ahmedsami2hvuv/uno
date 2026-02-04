import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_URL

def get_conn():
    return psycopg2.connect(DB_URL)

def db_query(query, params=(), commit=False, fetch=True):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(query, params)
    res = cur.fetchall() if fetch else None
    if commit: conn.commit()
    cur.close()
    conn.close()
    return res

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT)")
    cur.execute('''CREATE TABLE IF NOT EXISTS players_stats (
                    user_id BIGINT, player_name TEXT, wins INTEGER DEFAULT 0, games INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, player_name))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS active_games (
                    game_id SERIAL PRIMARY KEY, p1_id BIGINT, p2_id BIGINT,
                    p1_hand TEXT, p2_hand TEXT, top_card TEXT, deck TEXT,
                    turn BIGINT, status TEXT DEFAULT 'waiting')''')
    conn.commit()
    cur.close()
    conn.close()

