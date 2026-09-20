from typing import Dict, List
from pydantic import BaseModel, Field
from .Connection import Connection
from .Dron import Dron
from .Hub import Hub


class Map(BaseModel):
    """Collects drons, hubs, connections and status."""
    drons: List[Dron] = Field(...)
    hubs: Dict[str, Hub] = Field(...)
    connections: Dict[str, Connection] = Field(...)
    adjacency: Dict[str, List[str]] = Field(...)
