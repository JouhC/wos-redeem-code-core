from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.db.supabase import init_db, add_player
from app.utils.wos_api import PlayerAPI

is_ready: bool = False  # exported

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # local dev: ensure .env is loaded via pydantic settings (already handled)
    if not settings.RENDER and settings.DEFAULT_PLAYER:
        async def init_default_player():
            api = None
            try:
                api = PlayerAPI()
                login = await api.login_player(settings.DEFAULT_PLAYER, settings.SALT)
                if not login:
                    raise RuntimeError("DEFAULT_PLAYER login failed.")
                add_player(login["token"])
            finally:
                if api:
                    await api.close_session()
        await init_default_player()

    global is_ready
    is_ready = True

    yield
