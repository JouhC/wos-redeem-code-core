import sqlite3
from datetime import datetime
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_FILE = os.getenv("DB_FILE")

def init_db():
    """Initialize the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create tables if they don't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fid TEXT UNIQUE NOT NULL,
            nickname TEXT NOT NULL,
            kid INTEGER NOT NULL,
            stove_lv INTEGER NOT NULL,
            stove_lv_content INTEGER NOT NULL,
            avatar_image TEXT NOT NULL,
            total_recharge_amount INTEGER NOT NULL,
            subscribed_date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS giftcodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            created_date TEXT,
            status TEXT CHECK (Status IN ('Active', 'Inactive')) 
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

def add_player(player_data):
    """Add a new player to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO players (fid, nickname, kid, stove_lv, stove_lv_content, avatar_image, total_recharge_amount, subscribed_date)
            VALUES (:fid, :nickname, :kid, :stove_lv, :stove_lv_content, :avatar_image, :total_recharge_amount, :subscribed_date)
        """, {**player_data, 'subscribed_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        conn.commit()
        print(f"Player '{player_data['fid']}' added successfully.")
    except sqlite3.IntegrityError:
        print(f"Player '{player_data['fid']}' already exists.")
    finally:
        conn.close()

def get_players():
    """Retrieve all subscribed players."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # This allows rows to be accessed as dictionaries
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players")
    players = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return players

def add_giftcode(code):
    """Add a new gift code to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO giftcodes (code, created_date, status)
            VALUES (?, ?, ?)
        """, (code, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Active"))
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
    cursor.execute("SELECT code FROM giftcodes WHERE status='Active'")
    codes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return codes

def deactivate_giftcode(code):
    """Set the status of a specific gift code to 'Inactive'."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        # Check if the gift code exists and is currently 'Active'
        cursor.execute("SELECT status FROM giftcodes WHERE code = ?", (code,))
        result = cursor.fetchone()
        if result is None:
            print(f"Gift code '{code}' does not exist.")
            message = f"Gift code '{code}' does not exist."
        elif result[0] == 'Inactive':
            print(f"Gift code '{code}' is already inactive.")
            message = f"Gift code '{code}' is already inactive."
        else:
            # Update the status to 'Inactive'
            cursor.execute("UPDATE giftcodes SET status = 'Inactive' WHERE code = ?", (code,))
            conn.commit()
            print(f"Gift code '{code}' has been set to 'Inactive'.")
            message = f"Gift code '{code}' has been set to 'Inactive'."
    except Exception as e:
        print(f"An error occurred: {e}")
        message = f"An error occurred: {e}"
    finally:
        conn.close()
        return message

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
