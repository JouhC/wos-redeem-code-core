from fastapi import APIRouter, HTTPException, Depends
from app.api.dependencies import require_ready
from app.db.supabase import get_giftcodes, add_giftcode, deactivate_giftcode
from app.utils.fetch_gc_async import fetch_latest_codes_async

router = APIRouter(prefix="/giftcodes", tags=["giftcodes"], dependencies=[Depends(require_ready)])

@router.get("")
async def list_giftcodes():
    return {"giftcodes": get_giftcodes()}

@router.post("/fetch")
async def fetch_giftcodes():
    fetched = await fetch_latest_codes_async("whiteoutsurvival", "gift code")
    new_codes = [c for c in (add_giftcode(code) for code in fetched) if c]
    return {"message": "Gift codes fetched.", "new_codes": new_codes}

@router.post("/deactivate")
async def set_inactive(payload: dict):
    try:
        msg = deactivate_giftcode(payload["code"])
        return {"message": msg}
    except Exception as e:
        raise HTTPException(400, str(e))
