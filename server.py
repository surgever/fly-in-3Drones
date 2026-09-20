import os
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


def generate_simulation_payload(
        map_path: str, map_name: str) -> Dict[str, Any]:
    """Runs the simulation and generates a strictly minimized payload."""
    sim_map = MapLoader.load_map(map_path)
    if not sim_map:
        raise ValueError("Failed to parse map")

    engine = MapSimulator(sim_map)
    result = engine.run()

    if not result:
        raise ValueError("Deadlock detected")

    total_turns, turns_output = result
    # Strip hub defaults (role: hub, type: normal, max_cap: 1)
    min_hubs = {}
    for h_name, h in sim_map.hubs.items():
        min_h = {"x": h.x, "y": h.y}
        if h.role.value != "hub":
            min_h["role"] = h.role.value
        if h.zone_type.value != "normal":
            min_h["zone_type"] = h.zone_type.value
        if h.max_drones != 1:
            min_h["max_drones"] = h.max_drones
        if h.color:
            min_h["color"] = h.color
        min_hubs[h_name] = min_h
    map_data = {
        "drone_number": len(sim_map.drons),
        "hubs": min_hubs,
        "connections": list(sim_map.connections.keys())
    }
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

    return {
        "map_name": map_name,
        "map_data": map_data,
        "timeline": timeline_data,
        "total_turns": total_turns,
        "turns_output": turns_output
    }


@app.get("/api/maps")
def list_maps() -> List[str]:
    """Recursively scans map directory and get txt files."""
    if not os.path.exists("maps"):
        return []

    map_files: List[str] = []
    for root, _, files in os.walk("maps"):
        for file in files:
            if file.endswith(".txt"):
                rel_dir = os.path.relpath(root, "maps")
                if rel_dir == ".":
                    map_files.append(file)
                else:
                    rel_path = os.path.join(rel_dir, file).replace("\\", "/")
                    map_files.append(rel_path)

    def map_sort_key(map_path: str) -> tuple[int, str]:
        lower_path = map_path.replace("\\", "/").lower()
        parts = lower_path.split("/")
        folder = parts[0] if len(parts) > 1 else ""
        priorities = {"easy": 1, "medium": 2, "hard": 3, "challenger": 4}
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
        payload = generate_simulation_payload(map_path, req.map_name)
        print(f"\n= Flying: {req.map_name} =")
        print(payload["turns_output"])
        print(f"Number of turns taken: {payload['total_turns']}")

        del payload["turns_output"]
        return payload

    except ValueError as e:
        print(f"\n[!] Incorrect value in {req.map_name}:\n    {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"\n[!] Failed to simulate {req.map_name}:\n    {e}")
        raise HTTPException(status_code=400, detail=str(e))


app.mount(
    "/static",StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    """Main frontend."""
    return FileResponse("static/index.html")
