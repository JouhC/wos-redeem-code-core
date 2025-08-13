from fastapi import HTTPException 

async def require_ready():
    """
    Ensures the application is ready before handling the request.
    Useful for health checks and blocking requests until startup tasks finish.
    """
    from app.core.lifespan import is_ready
    if not is_ready:
        raise HTTPException(status_code=503, detail="Service not ready")
    return True