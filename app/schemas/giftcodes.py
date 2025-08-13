from pydantic import BaseModel

class GiftCodeSetStatusInactive(BaseModel):
    code: str
