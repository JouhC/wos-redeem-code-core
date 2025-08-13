from fastapi import APIRouter, HTTPException, Depends
from app.api.dependencies import require_ready
from app.schemas.redemptions import RedemptionRequest
from app.db.database import get_giftcodes, get_redeemed_codes, record_redemption
from app.utils.wos_api import PlayerAPI
from app.utils.rclone import backup_db
from app.core.config import settings

router = APIRouter(prefix="/players", tags=["redemptions"], dependencies=[Depends(require_ready)])

@router.post("/redeem")
async def redeem_giftcode(req: RedemptionRequest):
    api = None
    try:
        codes = get_giftcodes()
        redeemed = set(get_redeemed_codes(req.player_id))
        results = []

        api = PlayerAPI()
        login = await api.login_player(req.player_id, settings.SALT)
        if not login:
            raise HTTPException(400, "Login failed.")

        for code in codes:
            if code in redeemed:
                results.append({"message": f"Code '{code}' already redeemed for '{req.player_id}'."})
                continue
            res = await api.redeem_code(req.player_id, settings.SALT, code)
            if res.get("success"):
                record_redemption(req.player_id, code)
            results.append(res)

        return {"results": results, "backup": backup_db()}
    finally:
        if api: await api.close_session()

@router.get("/{player_id}/redemptions")
async def list_redeemed_codes(player_id: str):
    return {"player_id": player_id, "redeemed_codes": get_redeemed_codes(player_id)}
