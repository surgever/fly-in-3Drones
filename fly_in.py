import os
import sys
import argparse
import webbrowser
import socket
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
    parser = argparse.ArgumentParser(description="Fly-in Simulation System")
    parser.add_argument("-i", "--input", type=str, help="Path to map file.")
    parser.add_argument("--serve", action="store_true", help="Start server.")
    parser.add_argument("--ssserve", action="store_true", help="Silent serve.")
    parser.add_argument("-hide-turns", action="store_true", help="Hide turns.")
    parser.add_argument("-visual", action="store_true", help="Open frontend.")
    parser.add_argument("-export", action="store_true", help="Export.")
    return parser.parse_args()


class LocalRunner:
    """Manages CLI-based map simulations and visualizations."""

    def __init__(self, args: argparse.Namespace):
        self.args = args

    def run_single(self, filepath: str) -> None:

        from agents.MapLoader import MapLoader
        from agents.MapSimulator import MapSimulator

        rel_map_name = filepath.replace("\\", "/")
        if rel_map_name.startswith("maps/"):
            rel_map_name = rel_map_name[5:]
        else:
            rel_map_name = os.path.basename(filepath)

        try:
            sim_map = MapLoader.load_map(filepath)
            if not sim_map:
                raise ValueError("Failed to parse map")
            engine = MapSimulator(sim_map)
            result = engine.run()
            if not result:
                raise ValueError("Deadlock detected")
            total_turns, turns_output = result
            payload = engine.generate_payload(
                rel_map_name, total_turns, turns_output)
        except Exception as e:
            print(f"Failed to load map {rel_map_name}: {e}", file=sys.stderr)
            return

        print(f"\n= Flying: {rel_map_name} =")
        if not self.args.hide_turns:
            print(payload["turns_output"])
        print(f"Number of turns taken: {payload['total_turns']}")

        if self.args.export or self.args.visual:
            compressed_str = engine.generate_compressed_string(
                rel_map_name, turns_output)
            safe_str = urllib.parse.quote(compressed_str)
            if self.args.export:
                self._export_data(rel_map_name, safe_str)
            if self.args.visual:
                self._push_visual(safe_str)

    def _export_data(self, map_name: str, sim_data: str) -> None:
        os.makedirs(os.path.join("static", "data", "maps"), exist_ok=True)
        out_path = os.path.join(
            "static", "data", "maps", map_name.replace(".txt", ".data")
        )
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(sim_data)
        print(f"Exported JSON to {out_path}")

    def _push_visual(self, sim_data: str) -> None:
        api_host = os.getenv("API_HOST")
        if not api_host:
            api_host = "http://127.0.0.1:8080"
            if not is_server_running("127.0.0.1", 8080):
                print("=> Local server offline. Booting API in background...")
                subprocess.Popen([sys.executable, "fly_in.py", "--ssserve"])
                time.sleep(2.5)

        target_url = f"{api_host}/?data={sim_data}"
        print(f"=> Pushing visualization to {api_host}")
        webbrowser.open(target_url)


def main() -> int:
    args = parse_arguments()

    if args.serve or args.ssserve:
        from server import SimulationServer

        server = SimulationServer(port=8080, silent=args.ssserve)
        server.start()
        return 1

    if not args.input:
        print("Error: Must provide an input map with -i", file=sys.stderr)
        sys.exit(1)

    runner = LocalRunner(args)

    if os.path.isdir(args.input):
        for filename in os.listdir(args.input):
            if filename.endswith(".txt"):
                path = os.path.join(args.input, filename)
                print(f"\nRunning {path}...")
                runner.run_single(path)
    else:
        runner.run_single(args.input)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
        sys.exit(1)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Program terminated: {e}", file=sys.stderr)
        sys.exit(1)
