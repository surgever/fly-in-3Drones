from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class ZoneType(str, Enum):
    normal = "normal"
    blocked = "blocked"
    restricted = "restricted"
    priority = "priority"


class HubRoles(str, Enum):
    start = "start_hub"
    end = "end_hub"
    hub = "hub"


class Hub(BaseModel):
    """Stores hub config and state."""
    name: str = Field(..., min_length=1)
    x: int
    y: int
    role: HubRoles
    zone_type: ZoneType = ZoneType.normal
    color: Optional[str] = None
    max_drones: int = Field(default=1, gt=0)
    occupants: int = 0
