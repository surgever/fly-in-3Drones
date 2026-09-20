from typing import Optional
from enum import Enum
from pydantic import BaseModel


class DSt(str, Enum):
    waiting = "waiting"
    moving_to_hub = "moving_to_hub"
    in_transit = "in_transit"
    delivered = "delivered"


class Dron(BaseModel):
    """Drone state and tracking."""
    id: str
    current_location: str
    state: DSt = DSt.waiting
    transit_destination: Optional[str] = None
    transit_connection: Optional[str] = None
    turns_remaining: int = 0
