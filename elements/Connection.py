from pydantic import BaseModel, Field


class Connection(BaseModel):
    """Stores connection between two hubs."""
    name: str
    zone1: str
    zone2: str
    max_link_capacity: int = Field(default=1, gt=0)
    occupants: int = 0
