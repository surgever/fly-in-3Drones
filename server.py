import os
import json
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agents.MapLoader import MapLoader
from agents.MapSimulator import MapSimulator


app = FastAPI(title="Fly-in Simulation API")


class SimRequest(BaseModel):
    map_name: str
    nb_drones: int | None = None


@app.get("/api/maps")
def list_maps() -> List[str]:
    """Recursively scans the maps directory and returns available text files."""
    if not os.path.exists("maps"):
        return []

    map_files: List[str] = []
    for root, _, files in os.walk("maps"):
        for file in files:
            if file.endswith(".txt"):
                # Calculate the relative path (e.g., 'medium/01_map.txt')
                rel_dir = os.path.relpath(root, "maps")
                if rel_dir == ".":
                    map_files.append(file)
                else:
                    # Force forward slashes for web consistency
                    rel_path = os.path.join(rel_dir, file).replace("\\", "/")
                    map_files.append(rel_path)

    def map_sort_key(map_path: str) -> tuple[int, str]:
        """Defines custom sorting priority based on folder names."""
        lower_path = map_path.replace("\\", "/").lower()
        parts = lower_path.split("/")
        folder = parts[0] if len(parts) > 1 else ""
        priorities = {
            "easy": 1,
            "medium": 2,
            "hard": 3,
            "challenger": 4
        }
        # Assign priority 5 (last) to any folder not in the list or root maps
        priority = priorities.get(folder, 5)
        return (priority, map_path)

    return sorted(map_files, key=map_sort_key)


@app.post("/api/simulate")
def run_simulation(req: SimRequest) -> Dict[str, Any]:
    """Executes simulation and returns the JSON."""
    map_path: str = os.path.join("maps", req.map_name)
    if not os.path.exists(map_path):
        raise HTTPException(status_code=404, detail="Map not found")

    try:
        sim_map: Any = MapLoader.load_map(map_path)
    except ValueError as e:
        print(f"\n[!] Incorrect value in {req.map_name}:\n    {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"\n[!] Failed to load {req.map_name}:\n    {e}")
        raise HTTPException(status_code=400, detail=str(e))
    if not sim_map:
        raise HTTPException(status_code=400, detail="Failed to parse map")

    # if req.nb_drones is not None:
    #   sim_map.update_drone_count(req.nb_drones)

    try:
        engine: MapSimulator = MapSimulator(sim_map)
        result = engine.run()
    except Exception as e:
        print(f"\n[!] Failed to simulate {req.map_name}:\n    {e}")
        raise HTTPException(status_code=400, detail=str(e))

    if not result:
        raise HTTPException(status_code=500, detail="Deadlock detected")

    total_turns, turns_output = result

    print(f"\n= Flying: {req.map_name} =")
    print(turns_output)
    timeline_data: List[Dict[str, str]] = [{}]

    clean_output = engine.clean_ansi_codes(turns_output)
    for line in clean_output.strip().split('\n'):
        if not line or line.startswith("Numbers"):
            continue
        turn_moves: Dict[str, str] = {}
        for move in line.split():
            if '-' in move:
                parts = move.split('-', 1)
                if len(parts) == 2:
                    turn_moves[parts[0].strip()] = parts[1].strip()
        timeline_data.append(turn_moves)

    try:
        map_json_data: Dict[str, Any] = json.loads(
            sim_map.model_dump_json())
    except AttributeError:
        map_json_data = json.loads(sim_map.json())

    return {
        "map_name": req.map_name,
        "map_data": map_json_data,
        "timeline": timeline_data,
        "total_turns": total_turns
    }


app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)


@app.get("/")
def serve_index() -> FileResponse:
    """Main frontend."""
    return FileResponse("static/index.html")
