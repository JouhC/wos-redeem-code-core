from contextlib import asynccontextmanager
from app.utils.wos_api import PlayerAPI
from app.core.config import settings

@asynccontextmanager
async def player_session(player_id: str):
    """
    Async context manager for a PlayerAPI session:
    - Logs in the given player
    - Ensures the session is closed after use
    - Yields the logged-in API instance
    """
    api = PlayerAPI()
    try:
        login = await api.login_player(player_id, settings.SALT)
        if not login:
            raise RuntimeError(f"Login failed for player: {player_id}")
        yield api
    finally:
        await api.close_session()
