import os
import sys
import json
import argparse
import webbrowser
import uvicorn
from typing import Optional

from agents.MapLoader import MapLoader
from agents.MapSimulator import MapSimulator
from server import app

import socket
import base64
import urllib.parse
import subprocess
import time
from dotenv import load_dotenv


load_dotenv()


def is_server_running(host: str, port: int) -> bool:
    """Checks if a local server is actively listening on the given port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments for the simulation engine."""
    parser = argparse.ArgumentParser(description="Fly-in Simulation System")
    parser.add_argument(
        "-i", "--input", type=str,
        help="Path to the map file or directory."
    )
    parser.add_argument(
        "--serve", action="store_true",
        help="Start the FastAPI server and open the browser."
    )
    parser.add_argument(
        "-hide-turns", action="store_true",
        help="Suppress standard output of turn movements."
    )
    parser.add_argument(
        "-visual", "--visual", action="store_true",
        help="Open browser and push visualization data."
    )
    parser.add_argument(
        "-export-json", action="store_true",
        help="Export simulation result to static/data/maps/."
    )
    return parser.parse_args()


def export_simulation_data(map_name: str, payload: dict) -> None:
    """Formats and exports the simulation run to a static JSON file."""
    os.makedirs(os.path.join("static", "data", "maps"), exist_ok=True)

    out_path = os.path.join("static", "data", "maps",
        f"{map_name.replace(".txt","")}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Exported JSON to {out_path}")


def run_single_simulation(args: argparse.Namespace, filepath: str) -> None:
    """Executes a single simulation instance based on CLI flags."""
    sim_map = MapLoader.load_map(filepath)
    if not sim_map:
        print(f"Failed to load map: {filepath}", file=sys.stderr)
        return

    engine = MapSimulator(sim_map)
    result = engine.run()

    if not result:
        print("Simulation failed or deadlocked.", file=sys.stderr)
        return

    total_turns, turns_output = result

    print(f"\n= Flying: {os.path.basename(filepath)} =")
    if args.hide_turns:
        pass
    else:
        print(turns_output)
    print(f"Number of turns taken: {total_turns}")

    map_name = os.path.basename(filepath)

    try:
        map_json = sim_map.model_dump_json()
    except AttributeError:
        map_json = sim_map.json()

    cleaned_output = engine.clean_ansi_codes(turns_output)
    timeline = [{}]
    for line in cleaned_output.strip().split('\n'):
        if not line or line.startswith("Numbers"):
            continue
        moves = {}
        for move in line.split():
            if '-' in move:
                parts = move.split('-', 1)
                if len(parts) == 2:
                    moves[parts[0].strip()] = parts[1].strip()
        timeline.append(moves)

    payload = {
        "map_name": map_name,
        "map_data": json.loads(map_json),
        "timeline": timeline
    }

    if args.export_json:
        export_simulation_data(map_name, payload)

    if args.visual:
        api_host = os.getenv("API_HOST")
        if not api_host:
            api_host = "http://127.0.0.1:8080"
            if not is_server_running("127.0.0.1", 8080):
                print("=> Local server offline. Booting API in background...")
                subprocess.Popen([sys.executable, "fly_in.py", "--serve"])
                time.sleep(2.5)  # Give Uvicorn time to bind the port
        json_str = json.dumps(payload)
        b64_bytes = base64.b64encode(json_str.encode('utf-8'))
        safe_b64 = urllib.parse.quote(b64_bytes.decode('utf-8'))
        target_url = f"{api_host}/?data={safe_b64}"
        print(f"=> Pushing visualization to {api_host}")
        webbrowser.open(target_url)


def main() -> None:
    """Main orchestration function for CLI or Server execution."""
    args = parse_arguments()

    if args.serve:
        webbrowser.open("http://127.0.0.1:8080")
        uvicorn.run(
            app, host="127.0.0.1",
            port=8080, log_level="info",
            access_log=False
            )
        return

    if not args.input:
        print("Error: Must provide an input map with -i", file=sys.stderr)
        sys.exit(1)

    if os.path.isdir(args.input):
        for filename in os.listdir(args.input):
            if filename.endswith(".txt"):
                path = os.path.join(args.input, filename)
                print(f"\nRunning {path}...")
                run_single_simulation(args, path)
    else:
        run_single_simulation(args, args.input)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("\nProgram terminated:", e)
        sys.exit(1)
