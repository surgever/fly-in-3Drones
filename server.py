import os
import webbrowser
import uvicorn
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agents.MapLoader import MapLoader
from agents.MapSimulator import MapSimulator


class SimRequest(BaseModel):
    map_name: str
    nb_drones: int | None = None


class SimulationServer:
    """Encapsulates the FastAPI application and Three.js routing."""
    
    def __init__(self, port: int = 8080, silent: bool = False):
        self.port = port
        self.silent = silent
        self.app = FastAPI(title="Fly-in Simulation API")
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.mount(
            "/static",
            StaticFiles(directory="static"), name="static")

        @self.app.get("/api/maps")
        def list_maps() -> List[str]:
            """Recursively scans map directory and gets txt files."""
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
                            rel_path = os.path.join(rel_dir, file)
                            rel_path = rel_path.replace("\\", "/")
                            map_files.append(rel_path)

            def map_sort_key(map_path: str) -> tuple[int, str]:
                lower_path = map_path.replace("\\", "/").lower()
                parts = lower_path.split("/")
                folder = parts[0] if len(parts) > 1 else ""
                priorities = {
                    "easy": 1, "medium": 2, "hard": 3, "challenger": 4}
                priority = priorities.get(folder, 5)
                return (priority, map_path)

            return sorted(map_files, key=map_sort_key)

        @self.app.post("/api/simulate")
        def run_simulation(req: SimRequest) -> Dict[str, Any]:
            """Executes simulation and returns the JSON payload."""
            map_path: str = os.path.join("maps", req.map_name)
            if not os.path.exists(map_path):
                raise HTTPException(status_code=404, detail="Map not found")

            try:
                sim_map = MapLoader.load_map(map_path)
                if not sim_map:
                    raise ValueError("Failed to parse map")
                
                engine = MapSimulator(sim_map)
                result = engine.run()
                if not result:
                    raise ValueError("Deadlock detected")
                total_turns, turns_output = result
                payload = engine.generate_payload(
                    req.map_name, total_turns, turns_output)

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

        @self.app.get("/")
        def serve_index() -> FileResponse:
            """Main frontend."""
            return FileResponse("static/index.html")

    def start(self) -> None:
        """Boots the Uvicorn server and optionally opens the browser."""
        if not self.silent:
            webbrowser.open(f"http://127.0.0.1:{self.port}")
        uvicorn.run(
            self.app, host="127.0.0.1", 
            port=self.port, log_level="info", 
            access_log=False
        )
