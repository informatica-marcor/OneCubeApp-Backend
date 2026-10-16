from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class TicketOut(BaseModel):
    ticket_id:int
    client_id:int
    subject: str
    description: str
    uploaded_at:str
    reply_user_id:Optional[int] = None
    # reply_user_name: Optional[str] = None
    reply:Optional[str] = None
    resolved_at:Optional[str] = None