import os
from datetime import datetime, timezone
from unittest import mock
import unittest


os.environ.setdefault("SALT", "test-salt")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("PRIORITY_ACCOUNT", "test-priority")
os.environ.setdefault("RENDER", "true")

from app.db import supabase


class FakeCursor:
    def __init__(self, *, fetchone_results=None, fetchall_result=None, rowcount=0):
        self.executions = []
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_result = fetchall_result or []
        self.rowcount = rowcount

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executions.append((str(query), params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        return self.fetchall_result


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


def patch_connect(cursor):
    return mock.patch.object(supabase, "_connect", return_value=FakeConnection(cursor))


class SupabaseTests(unittest.TestCase):
    def test_init_db_creates_timestamp_columns(self):
        cursor = FakeCursor()

        with patch_connect(cursor), mock.patch.object(supabase, "_ensure_timestamp_column") as ensure:
            supabase.init_db()

        schema_sql = "\n".join(query for query, _ in cursor.executions)
        self.assertIn("subscribed_date TIMESTAMPTZ", schema_sql)
        self.assertIn("created_date TIMESTAMPTZ", schema_sql)
        self.assertIn("last_checked TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP", schema_sql)
        self.assertIn("redeemed_date TIMESTAMPTZ", schema_sql)

        ensure.assert_has_calls([
            mock.call(cursor, "players", "subscribed_date"),
            mock.call(cursor, "giftcodes", "created_date"),
            mock.call(cursor, "giftcodes", "last_checked", "CURRENT_TIMESTAMP"),
            mock.call(cursor, "redemptions", "redeemed_date"),
        ])

    def test_add_player_writes_timezone_aware_subscribed_date(self):
        cursor = FakeCursor()
        now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
        player = {
            "fid": "player-1",
            "nickname": "Tester",
            "kid": 1,
            "stove_lv": 2,
            "stove_lv_content": "2",
            "avatar_image": "avatar.png",
            "total_recharge_amount": 0,
        }

        with patch_connect(cursor), mock.patch.object(supabase, "_now", return_value=now):
            supabase.add_player(player)

        _, params = cursor.executions[-1]
        self.assertIs(params["subscribed_date"], now)
        self.assertIsNotNone(params["subscribed_date"].tzinfo)

    def test_add_giftcode_uses_database_current_timestamp(self):
        cursor = FakeCursor(fetchone_results=[("CODE1",)])

        with patch_connect(cursor):
            result = supabase.add_giftcode("CODE1")

        query, params = cursor.executions[-1]
        self.assertEqual(result, "CODE1")
        self.assertEqual(params, ("CODE1",))
        self.assertIn("CURRENT_TIMESTAMP", query)
        self.assertIn("ON CONFLICT", query)

    def test_record_redemption_writes_timezone_aware_redeemed_date(self):
        cursor = FakeCursor()
        now = datetime(2026, 6, 3, 12, 5, tzinfo=timezone.utc)

        with patch_connect(cursor), mock.patch.object(supabase, "_now", return_value=now):
            supabase.record_redemption("player-1", "CODE1")

        _, params = cursor.executions[-1]
        self.assertEqual(params, ("player-1", "CODE1", now))
        self.assertIsNotNone(params[2].tzinfo)

    def test_update_giftcode_checkedtime_writes_timezone_aware_last_checked(self):
        cursor = FakeCursor()
        now = datetime(2026, 6, 3, 12, 10, tzinfo=timezone.utc)

        with patch_connect(cursor), mock.patch.object(supabase, "_now", return_value=now):
            supabase.update_giftcode_checkedtime("CODE1")

        _, params = cursor.executions[-1]
        self.assertEqual(params, (now, "CODE1"))
        self.assertIsNotNone(params[0].tzinfo)

    def test_get_giftcodes_unchecked_skips_recent_default_player_redemptions(self):
        cursor = FakeCursor(fetchall_result=[("CODE1",), ("CODE2",)])

        with patch_connect(cursor):
            codes = supabase.get_giftcodes_unchecked("286136250")

        query, params = cursor.executions[-1]
        self.assertEqual(codes, ["CODE1", "CODE2"])
        self.assertEqual(params, ["286136250"])
        self.assertIn("NOT EXISTS", query)
        self.assertIn("redeemed_date >= CURRENT_TIMESTAMP - INTERVAL '1 day'", query)

    def test_get_unredeemed_query_uses_redeemed_date_column(self):
        cursor = FakeCursor(fetchall_result=[{"fid": "player-1", "code": "CODE1"}])

        with patch_connect(cursor):
            rows = supabase.get_unredeemed_code_player_list()

        query, _ = cursor.executions[-1]
        self.assertEqual(rows, [{"fid": "player-1", "code": "CODE1"}])
        self.assertIn("r.redeemed_date", query)
        self.assertNotIn("redeemed_at", query)


if __name__ == "__main__":
    unittest.main()
