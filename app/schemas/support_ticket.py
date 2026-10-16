from typing import Optional
from pydantic import BaseModel

class TicketUpdate(BaseModel):
    reply: Optional[str] = None
    status: str