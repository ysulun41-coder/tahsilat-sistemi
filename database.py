import sqlite3

def get_connection():
    conn = sqlite3.connect("data.db", check_same_thread=False)
    return conn

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # Öğrenciler
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ogrenciler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT,
        veli TEXT,
        telefon TEXT
    )
    """)

    # Ödeme planı
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS odemeler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ogrenci TEXT,
        vade DATE,
        tutar REAL,
        durum TEXT
    )
    """)

    conn.commit()
    conn.close()