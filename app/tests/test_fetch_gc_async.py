import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("SALT", "test-salt")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("PRIORITY_ACCOUNT", "test-priority")
os.environ.setdefault("ADMIN_ACTION_PASSWORD", "test-password")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("USER_AGENT", "test-user-agent")

from app.utils.fetch_gc_async import _fetch_rss_codes, fetch_latest_codes_async


class GiftCodeFeedTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.utils.fetch_gc_async.requests.get")
    def test_fetch_rss_codes_uses_item_titles(self, mock_get):
        response = Mock(
            content=b"<rss><channel><item><title>WOS0803</title></item></channel></rss>"
        )
        mock_get.return_value = response

        self.assertEqual(_fetch_rss_codes("https://example.test/rss"), ["WOS0803"])
        mock_get.assert_called_once_with("https://example.test/rss", timeout=15)
        response.raise_for_status.assert_called_once_with()

    @patch("app.utils.fetch_gc_async.fetch_codes_from_urls_async", new_callable=AsyncMock)
    @patch("app.utils.fetch_gc_async._fetch_reddit_codes_async", new_callable=AsyncMock)
    async def test_combines_and_deduplicates_sources(self, reddit_fetch, url_fetch):
        reddit_fetch.return_value = ["CODE1", "SHARED"]
        url_fetch.return_value = ["SHARED", "CODE2"]

        codes = await fetch_latest_codes_async(
            "whiteoutsurvival", "gift code", ["https://example.test/rss"]
        )

        self.assertEqual(codes, ["CODE1", "SHARED", "CODE2"])
        url_fetch.assert_awaited_once_with(["https://example.test/rss"])


if __name__ == "__main__":
    unittest.main()
