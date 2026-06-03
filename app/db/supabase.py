from app.core.config import settings
from datetime import datetime, timezone
import logging

import psycopg
from psycopg import errors
from psycopg import sql
from psycopg.rows import dict_row

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _database_url():
    """Return the Postgres connection URL from the environment."""
    return settings.DATABASE_URL


def _connect(row_factory=None):
    kwargs = {}
    if row_factory is not None:
        kwargs["row_factory"] = row_factory
    return psycopg.connect(_database_url(), **kwargs)


def _now():
    return datetime.now(timezone.utc)


def _normalize_player_id(player_id):
    if player_id is None:
        return player_id
    return str(player_id)


def _normalize_player_data(player_data):
    if 'fid' in player_data:
        player_data['fid'] = _normalize_player_id(player_data['fid'])
    return player_data


def _ensure_timestamp_column(cursor, table_name, column_name, default_sql=None):
    cursor.execute("""
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = current_schema()
        AND table_name = %s
        AND column_name = %s
    """, (table_name, column_name))
    result = cursor.fetchone()

    if result is None:
        return

    if result[0] != "timestamp with time zone":
        cursor.execute(sql.SQL("""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name}
            TYPE TIMESTAMPTZ
            USING NULLIF({column_name}::TEXT, '')::TIMESTAMPTZ
        """).format(
            table_name=sql.Identifier(table_name),
            column_name=sql.Identifier(column_name),
        ))

    if default_sql is not None:
        cursor.execute(sql.SQL("""
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name}
            SET DEFAULT {default_sql}
        """).format(
            table_name=sql.Identifier(table_name),
            column_name=sql.Identifier(column_name),
            default_sql=sql.SQL(default_sql),
        ))


def init_db():
    """Initialize the database."""
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    id BIGSERIAL PRIMARY KEY,
                    fid TEXT UNIQUE NOT NULL,
                    nickname TEXT NOT NULL,
                    kid INTEGER NOT NULL,
                    stove_lv INTEGER NOT NULL,
                    stove_lv_content TEXT NOT NULL,
                    avatar_image TEXT NOT NULL,
                    total_recharge_amount INTEGER NOT NULL,
                    subscribed_date TIMESTAMPTZ
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS giftcodes (
                    id BIGSERIAL PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    created_date TIMESTAMPTZ,
                    status TEXT CHECK (status IN ('Active', 'Inactive')),
                    last_checked TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS redemptions (
                    id BIGSERIAL PRIMARY KEY,
                    player_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    redeemed_date TIMESTAMPTZ,
                    FOREIGN KEY (player_id) REFERENCES players(fid),
                    FOREIGN KEY (code) REFERENCES giftcodes(code)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS captchas (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT,
                    img BYTEA,
                    feedback BOOLEAN DEFAULT FALSE
                )
            """)

            _ensure_timestamp_column(cursor, "players", "subscribed_date")
            _ensure_timestamp_column(cursor, "giftcodes", "created_date")
            _ensure_timestamp_column(cursor, "giftcodes", "last_checked", "CURRENT_TIMESTAMP")
            _ensure_timestamp_column(cursor, "redemptions", "redeemed_date")


def add_player(player_data):
    """Add a new player to the database."""
    try:
        player_data = _normalize_player_data(player_data)
        with _connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO players (
                        fid,
                        nickname,
                        kid,
                        stove_lv,
                        stove_lv_content,
                        avatar_image,
                        total_recharge_amount,
                        subscribed_date
                    )
                    VALUES (
                        %(fid)s,
                        %(nickname)s,
                        %(kid)s,
                        %(stove_lv)s,
                        %(stove_lv_content)s,
                        %(avatar_image)s,
                        %(total_recharge_amount)s,
                        %(subscribed_date)s
                    )
                """, {**player_data, "subscribed_date": _now()})
        logger.info(f"Player '{player_data['fid']}' added successfully.")
    except errors.UniqueViolation:
        logger.info(f"Player '{player_data['fid']}' already exists.")


def update_player(player_data):
    """Update a player in the database."""
    try:
        player_data = _normalize_player_data(player_data)
        with _connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE players
                    SET nickname = %(nickname)s,
                        kid = %(kid)s,
                        stove_lv = %(stove_lv)s,
                        stove_lv_content = %(stove_lv_content)s,
                        avatar_image = %(avatar_image)s,
                        total_recharge_amount = %(total_recharge_amount)s
                    WHERE fid = %(fid)s
                """, player_data)
        logger.info(f"Player '{player_data['fid']}' info updated successfully.")
    except errors.IntegrityError:
        logger.info(f"Player '{player_data['fid']}' info failed to update.")


def remove_player(fid):
    """Removes a player from the database."""
    fid = _normalize_player_id(fid)
    response = f"Player '{fid}' not found in the database."
    try:
        with _connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM players WHERE fid = %s", (fid,))

                if cursor.rowcount == 0:
                    response = f"Player '{fid}' not found in the database."
                else:
                    response = f"Player '{fid}' removed successfully."
    except errors.IntegrityError:
        response = f"Player '{fid}' unable to remove."
    finally:
        logger.info(response)
        return response


def get_players():
    """Retrieve all subscribed players."""
    with _connect(row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                WITH active_codes AS (
                    SELECT code FROM giftcodes WHERE status = 'Active'
                ),
                active_count AS (
                    SELECT COUNT(*) AS n FROM active_codes
                ),
                player_redeemed AS (
                    SELECT r.player_id, COUNT(DISTINCT r.code) AS redeemed_count
                    FROM redemptions r
                    JOIN active_codes a ON a.code = r.code
                    GROUP BY r.player_id
                )
                SELECT
                    p.id AS player_id,
                    p.fid,
                    p.nickname,
                    p.kid,
                    p.stove_lv,
                    p.stove_lv_content,
                    p.avatar_image,
                    p.total_recharge_amount,
                    p.subscribed_date,
                    CASE
                        WHEN ac.n = 0 THEN 0
                        WHEN COALESCE(pr.redeemed_count, 0) = ac.n THEN 1
                        ELSE 0
                    END AS redeemed_all
                FROM players p
                CROSS JOIN active_count ac
                LEFT JOIN player_redeemed pr ON pr.player_id = p.fid
            """)
            players = cursor.fetchall()

    logger.info("Loaded players from Postgres.")
    return players


def add_giftcode(code):
    """
    Add a new gift code.
    If the code already exists and was created more than 3 months ago,
    reactivate it and refresh its timestamps.
    """
    try:
        with _connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO giftcodes (
                        code,
                        created_date,
                        status,
                        last_checked
                    )
                    VALUES (
                        %s,
                        CURRENT_TIMESTAMP,
                        'Active',
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (code)
                    DO UPDATE
                    SET
                        status = 'Active',
                        created_date = CURRENT_TIMESTAMP,
                        last_checked = CURRENT_TIMESTAMP
                    WHERE giftcodes.created_date <= CURRENT_TIMESTAMP - INTERVAL '3 months'
                    RETURNING code
                """, (code,))

                result = cursor.fetchone()

        if result:
            logger.info(f"Gift code '{code}' added/reactivated successfully.")
            return code

        logger.info(
            f"Gift code '{code}' already exists and is less than 3 months old."
        )
        return None

    except Exception as e:
        logger.exception(f"Failed to add gift code '{code}': {e}")
        return None


def get_giftcodes():
    """Retrieve all gift codes."""
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT code FROM giftcodes WHERE status = 'Active'")
            codes = [row[0] for row in cursor.fetchall()]
    return codes


def get_giftcodes_unchecked(default_player: str | None = None):
    """Retrieve all gift codes that have not been checked in the last 24 hours.

    If a default player is supplied, also skip codes that player has redeemed
    in the last 24 hours.
    """
    with _connect() as conn:
        with conn.cursor() as cursor:
            query = """
                SELECT code
                FROM giftcodes
                WHERE status = 'Active'
                AND last_checked <= CURRENT_TIMESTAMP - INTERVAL '1 day'
            """
            params = []

            if default_player:
                query += """
                    AND NOT EXISTS (
                        SELECT 1 FROM redemptions r
                        WHERE r.code = giftcodes.code
                          AND r.player_id = %s
                          AND r.redeemed_date >= CURRENT_TIMESTAMP - INTERVAL '1 day'
                    )
                """
                params = [default_player]

            cursor.execute(query, params)
            codes = [row[0] for row in cursor.fetchall()]
    return codes


def deactivate_giftcode(code):
    """Set the status of a specific gift code to 'Inactive'."""
    try:
        with _connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT status FROM giftcodes WHERE code = %s", (code,))
                result = cursor.fetchone()
                if result is None:
                    logger.info(f"Gift code '{code}' does not exist.")
                    message = f"Gift code '{code}' does not exist."
                elif result[0] == "Inactive":
                    logger.info(f"Gift code '{code}' is already inactive.")
                    message = f"Gift code '{code}' is already inactive."
                else:
                    cursor.execute("UPDATE giftcodes SET status = 'Inactive' WHERE code = %s", (code,))
                    logger.info(f"Gift code '{code}' has been set to 'Inactive'.")
                    message = f"Gift code '{code}' has been set to 'Inactive'."
    except Exception as e:
        logger.info(f"An error occurred: {e}")
        message = f"An error occurred: {e}"
    finally:
        return message


def record_redemption(player_id, code):
    """Record a gift code redemption for a player."""
    player_id = _normalize_player_id(player_id)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO redemptions (player_id, code, redeemed_date)
                VALUES (%s, %s, %s)
            """, (player_id, code, _now()))
    logger.info(f"Redemption recorded: Player '{player_id}' redeemed code '{code}'.")


def get_redeemed_codes(player_id):
    """Get all redeemed codes for a player."""
    player_id = _normalize_player_id(player_id)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT code FROM redemptions WHERE player_id = %s", (player_id,))
            redeemed_codes = [row[0] for row in cursor.fetchall()]
    return redeemed_codes


def update_players_table(player_data_list):
    """Update players' information from a DataFrame."""
    try:
        with _connect() as conn:
            with conn.cursor() as cursor:
                for player_data in player_data_list:
                    player_data = _normalize_player_data(player_data)
                    cursor.execute("""
                        UPDATE players
                        SET nickname = %(nickname)s,
                            kid = %(kid)s,
                            stove_lv = %(stove_lv)s,
                            stove_lv_content = %(stove_lv_content)s,
                            avatar_image = %(avatar_image)s,
                            total_recharge_amount = %(total_recharge_amount)s
                        WHERE fid = %(fid)s
                    """, player_data)
        logger.info("Players updated successfully.")
    except errors.IntegrityError as e:
        logger.error(f"An error occurred: {e}")


def get_unredeemed_code_player_list():
    with _connect(row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT p.fid, g.code
                FROM players p
                CROSS JOIN giftcodes g
                LEFT JOIN redemptions r
                    ON p.fid = r.player_id
                    AND g.code = r.code
                    AND r.redeemed_date >= g.created_date
                WHERE r.code IS NULL
                  AND g.status = 'Active'
                  AND p.fid != %s
            """, (settings.DEFAULT_PLAYER,))

            unredeemed_codes_players = cursor.fetchall()

    return unredeemed_codes_players


def record_captcha(name, img_data):
    """Record a captcha image with a name."""
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO captchas (name, img)
                VALUES (%s, %s)
                RETURNING id
            """, (name, img_data))
            generated_id = cursor.fetchone()[0]
    logger.info("Captcha recorded!")
    return generated_id


def update_captcha_feedback(captcha_id):
    """Update the feedback for a specific captcha."""
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE captchas SET feedback = TRUE WHERE id = %s", (captcha_id,))
    logger.info(f"Captcha ID '{captcha_id}' feedback set to TRUE.")


def update_giftcode_checkedtime(code):
    """Update the last checked time for a specific gift code."""
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE giftcodes
                SET last_checked = %s
                WHERE code = %s
            """, (_now(), code))
    logger.info(f"Gift code '{code}' last checked time updated.")


if __name__ == "__main__":
    init_db()
