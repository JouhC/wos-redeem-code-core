from fastapi import APIRouter
from app.core.lifespan import is_ready

router = APIRouter(tags=["health"])

@router.get("/")
async def root():
    return {"message": "Welcome to the Gift Code Redemption API!"}

@router.get("/healthz")
async def healthz():
    return {"ready": is_ready}

@router.get("/health")
async def health():
    return {"status": "ok"}