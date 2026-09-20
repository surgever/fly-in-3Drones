import os
import sys
import json
import argparse
import webbrowser
import uvicorn
from typing import Any
import socket
import urllib.parse
import subprocess
import time
from dotenv import load_dotenv
from server import app, generate_simulation_payload


load_dotenv()


def is_server_running(host: str, port: int) -> bool:
    """Checks if a local server is actively listening on the given port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments for the simulation engine."""
    parser = argparse.ArgumentParser(description="Fly-in Simulation System")
    parser.add_argument("-i", "--input", type=str, help="Path to  map file.")
    parser.add_argument("--serve", action="store_true", help="Start server.")
    parser.add_argument("--ssserve", action="store_true", help="Silent serv.")
    parser.add_argument("-hide-turns", action="store_true", help="Hid turns.")
    parser.add_argument("-visual", action="store_true", help="Open frontend.")
    parser.add_argument("-export-json", action="store_true", help="Export.")
    return parser.parse_args()


def export_simulation_data(map_name: str, payload: dict[str, Any]) -> None:
    """Formats and exports the simulation run to a static JSON file."""
    os.makedirs(os.path.join("static", "data", "maps"), exist_ok=True)

    out_path = os.path.join(
        "static", "data", "maps", f"{map_name.replace('.txt', '')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Exported JSON to {out_path}")


def run_single_simulation(args: argparse.Namespace, filepath: str) -> None:
    """Executes a single simulation instance based on CLI flags."""
    rel_map_name = filepath.replace("\\", "/")
    if rel_map_name.startswith("maps/"):
        rel_map_name = rel_map_name[5:]
    else:
        rel_map_name = os.path.basename(filepath)

    try:
        payload = generate_simulation_payload(filepath, rel_map_name)
    except Exception as e:
        print(f"Failed to load map {rel_map_name}: {e}", file=sys.stderr)
        return

    print(f"\n= Flying: {rel_map_name} =")
    if not args.hide_turns:
        print(payload["turns_output"])
    print(f"Number of turns taken: {payload['total_turns']}")

    if args.export_json:
        export_payload = payload.copy()
        del export_payload["turns_output"]
        export_simulation_data(rel_map_name, export_payload)

    if args.visual:
        api_host = os.getenv("API_HOST")
        if not api_host:
            api_host = "http://127.0.0.1:8080"
            if not is_server_running("127.0.0.1", 8080):
                print("=> Local server offline. Booting API in background...")
                subprocess.Popen([sys.executable, "fly_in.py", "--ssserve"])
                time.sleep(2.5)

        safe_map = urllib.parse.quote(rel_map_name)
        target_url = f"{api_host}/?map={safe_map}"
        print(f"=> Pushing visualization to {api_host}")
        webbrowser.open(target_url)


def main() -> None:
    """Main orchestration function for CLI or Server execution."""
    args = parse_arguments()

    if args.serve or args.ssserve:
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
