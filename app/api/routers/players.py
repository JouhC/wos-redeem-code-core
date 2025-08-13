from fastapi import APIRouter, HTTPException, Depends
from app.api.dependencies import require_ready
from app.schemas.players import Player
from app.db.database import get_players, add_player, remove_player, update_player
from app.utils.wos_api import PlayerAPI
from app.utils.rclone import backup_db
from app.core.config import settings

router = APIRouter(prefix="/players", tags=["players"], dependencies=[Depends(require_ready)])

@router.get("")
async def list_players():
    return {"players": get_players()}

@router.post("/create")
async def create_player(player: Player):
    api = None
    try:
        api = PlayerAPI()
        login = await api.login_player(player.player_id, settings.SALT)
        if not login:
            raise HTTPException(400, f"Adding '{player.player_id}' failed.")
        add_player(login["token"])
        return {"message": f"Player '{player.player_id}' added successfully.", "backup": backup_db()}
    finally:
        if api: await api.close_session()

@router.post("/update")
async def update_player_profile(player: Player):
    api = None
    try:
        api = PlayerAPI()
        login = await api.login_player(player.player_id, settings.SALT)
        update_player(login["token"])
        return {"message": f"Player '{player.player_id}' info updated.", "backup": backup_db()}
    finally:
        if api: await api.close_session()

@router.post("/remove")
async def remove_player_db(player: Player):
    resp = remove_player(player.player_id)
    return {"response": resp, "backup": backup_db()}
