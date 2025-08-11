from pydantic import BaseModel

class RedemptionRequest(BaseModel):
    player_id: str