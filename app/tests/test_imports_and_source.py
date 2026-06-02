import importlib
import os
from pathlib import Path
import unittest


os.environ.setdefault("SALT", "test-salt")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("PRIORITY_ACCOUNT", "test-priority")
os.environ.setdefault("RENDER", "true")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("USER_AGENT", "test-user-agent")


class ImportAndSourceTests(unittest.TestCase):
    def test_core_modules_import_without_local_database_dependencies(self):
        modules = [
            "app.core.config",
            "app.db.supabase",
            "app.core.lifespan",
            "app.api.routers.health",
            "app.api.routers.giftcodes",
            "app.api.routers.players",
            "app.api.routers.redemptions",
            "app.utils.captcha_solver",
        ]

        for module_name in modules:
            with self.subTest(module=module_name):
                importlib.import_module(module_name)

    def test_active_app_code_no_longer_imports_sqlite_or_rclone_layers(self):
        app_root = Path(__file__).resolve().parents[1]
        forbidden = (
            "from db.supabase",
            "from app.db.database",
            "from archive.database",
            "import sqlite3",
            "backup_db",
            "sync_db",
            "rclone",
        )

        for path in app_root.rglob("*.py"):
            relative_parts = path.relative_to(app_root).parts
            if "tests" in relative_parts or "archive" in relative_parts:
                continue
            source = path.read_text(encoding="utf-8")
            for text in forbidden:
                with self.subTest(path=str(path), text=text):
                    self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
