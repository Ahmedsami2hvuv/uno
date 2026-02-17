import os
import psycopg2


def get_conn():
    # Try to get the connection using DATABASE_URL first
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url)

    # Fall back to individual PostgreSQL connection variables
    host = os.getenv('PGHOST')
    port = os.getenv('PGPORT')
    user = os.getenv('PGUSER')
    password = os.getenv('PGPASSWORD')
    database = os.getenv('PGDATABASE')

    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=database
    )
