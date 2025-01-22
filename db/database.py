import sqlite3
from datetime import datetime

DB_FILE = "giftcode_system.db"

def init_db():
    """Initialize the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create tables if they don't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT UNIQUE NOT NULL,
            subscribed_date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS giftcodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            created_date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT NOT NULL,
            code TEXT NOT NULL,
            redeemed_date TEXT,
            FOREIGN KEY (player_id) REFERENCES players(player_id),
            FOREIGN KEY (code) REFERENCES giftcodes(code)
        )
    """)

    conn.commit()
    conn.close()

def add_player(player_id):
    """Add a new player to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO players (player_id, subscribed_date)
            VALUES (?, ?)
        """, (player_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        print(f"Player '{player_id}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"Player '{player_id}' already exists.")
    finally:
        conn.close()

def get_players():
    """Retrieve all subscribed players."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT player_id FROM players")
    players = [row[0] for row in cursor.fetchall()]
    conn.close()
    return players

def add_giftcode(code):
    """Add a new gift code to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO giftcodes (code, created_date)
            VALUES (?, ?)
        """, (code, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        print(f"Gift code '{code}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"Gift code '{code}' already exists.")
    finally:
        conn.close()

def get_giftcodes():
    """Retrieve all gift codes."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM giftcodes")
    codes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return codes

def record_redemption(player_id, code):
    """Record a gift code redemption for a player."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO redemptions (player_id, code, redeemed_date)
            VALUES (?, ?, ?)
        """, (player_id, code, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        print(f"Redemption recorded: Player '{player_id}' redeemed code '{code}'.")
    finally:
        conn.close()

def get_redeemed_codes(player_id):
    """Get all redeemed codes for a player."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT code FROM redemptions WHERE player_id = ?
    """, (player_id,))
    redeemed_codes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return redeemed_codes
