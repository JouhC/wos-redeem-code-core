from pydantic import BaseModel

class AutomationRequest(BaseModel):
    n: str = "all"