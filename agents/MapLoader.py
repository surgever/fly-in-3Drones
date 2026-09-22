from typing import Optional, List, Dict, Tuple, Set
from pydantic import ValidationError
from elements import Map, Hub, Connection, Dron, HubRoles, ZoneType
import sys
import re


class MapLoader:
    """Read map and parse data."""

    @staticmethod
    def _load_lines(
        file_path: str
    ) -> Tuple[Optional[List[str]], Optional[str]]:
        try:
            with open(file_path, encoding="utf-8") as config_file:
                return config_file.read().splitlines(), None
        except OSError as error:
            return None, f"Cannot read map config file: {error}"

    @staticmethod
    def _parse_metadata(metadata_str: str) -> Dict[str, str]:
        metadata: Dict[str, str] = {}
        if not metadata_str:
            return metadata
        match_metadata = re.fullmatch(r"([^\[\]]+)", metadata_str)
        if not match_metadata:
            raise ValueError("Invalid metadata format: extra brackets")

        metadata_str = metadata_str.strip("[]")

        parts = metadata_str.split()
        for part in parts:
            if "=" in part:
                key, val = part.split("=", 1)
                val_match = re.fullmatch(r"([\w\-]+)", val)
                if not val_match or key not in {
                        "max_drones", "color", "max_link_capacity", "zone"}:
                    raise ValueError("Invalid metadata: wrong meta")
                metadata[key] = val
            else:
                raise ValueError("Invalid metadata format: missing equal")
        return metadata

    @classmethod
    def load_map(cls, file_path: str) -> Optional[Map]:
        lines_data = cls._load_lines(file_path)
        lines, lines_error = lines_data

        if lines_error or lines is None:
            print(lines_error, file=sys.stderr)
            return None

        if not lines:
            raise ValueError("Error: Empty file provided.")

        nb_drones = 0
        hubs: Dict[str, Hub] = {}
        connections: Dict[str, Connection] = {}
        adjacency: Dict[str, List[str]] = {}

        has_start = False
        has_end = False
        drones_parsed = False

        hub_pattern = (
            r"^(start_hub|end_hub|hub)\s*:\s*"
            + r"([^\s-]+)\s+(-?\d+)\s+(-?\d+)(?:\s+\[(.*?)\])?$"
        )
        conn_pattern = (
            r"^connection\s*:\s*([^\s-]+)-([^\s-]+)(?:\s+\[(.*?)\])?$"
        )
        drones_pattern = r"^nb_drones\s*:\s*(\d+)$"

        used_hub_coord: Set[str] = set()
        for line_num, line in enumerate(lines, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if not drones_parsed:
                drones_match = re.fullmatch(drones_pattern, line)
                if not drones_match:
                    raise ValueError(
                        f"Error on line {line_num}: The first directive "
                        "must be 'nb_drones: <positive_integer>'.",
                    )
                nb_drones = int(drones_match.group(1))
                if nb_drones <= 0:
                    raise ValueError(
                        f"Error on line {line_num}: nb_drones must be > 0.")
                elif nb_drones > 1000:
                    raise ValueError("Error on nb_drones: that's a lot.")
                drones_parsed = True
                continue

            hub_match = re.fullmatch(hub_pattern, line)
            if hub_match:
                role_str, name, x, y, meta_str = hub_match.groups()

                if name in hubs:
                    raise ValueError(
                        f"Error on line {line_num}: Zone '{name}' "
                        "is already defined."
                    )
                if f"{x},{y}" in used_hub_coord:
                    raise ValueError(
                        f"Error on line {line_num}: Zone '{name}' "
                        "coordinates are occupied."
                    )
                else:
                    used_hub_coord.add(f"{x},{y}")
                meta = cls._parse_metadata(meta_str) if meta_str else {}

                try:
                    role_enum = HubRoles(role_str)
                    z_type = ZoneType(meta.get("zone", "normal"))
                except ValueError as exc:
                    raise ValueError(
                        f"Error on line {line_num}: Invalid Enum type "
                        f"provided. {exc}"
                    )
                try:
                    max_d_str = meta.get("max_drones", "1")
                    max_d = int(max_d_str)
                except ValueError:
                    raise ValueError(
                        f"Error on line {line_num}: max_drones must "
                        "be an integer."
                    )

                if role_enum == HubRoles.start:
                    if has_start:
                        raise ValueError(
                            f"Error on line {line_num}: Multiple start_hubs.",
                        )
                    has_start = True
                    max_d = 999999

                if role_enum == HubRoles.end:
                    if has_end:
                        raise ValueError(
                            f"Error on line {line_num}: Multiple end_hubs.",
                        )
                    has_end = True
                    max_d = 999999

                try:
                    hubs[name] = Hub(
                        name=name, x=int(x), y=int(y), role=role_enum,
                        zone_type=z_type, color=meta.get("color"),
                        max_drones=max_d
                    )
                except ValidationError as e:
                    raise ValueError(
                        f"Error on line {line_num}: Hub Validation fail.\n{e}"
                    )

                adjacency[name] = []
                continue

            conn_match = re.fullmatch(conn_pattern, line)
            if conn_match:
                z1, z2, meta_str = conn_match.groups()
                if z1 not in hubs or z2 not in hubs:
                    raise ValueError(
                        f"Error on line {line_num}: Connection links unknown "
                        f"zones {z1}-{z2}."
                    )
                conn_name_1 = f"{z1}-{z2}"
                conn_name_2 = f"{z2}-{z1}"
                if conn_name_1 in connections or conn_name_2 in connections:
                    raise ValueError(
                        f"Error on line {line_num}: Connection between {z1} "
                        f"and {z2} already exists."
                    )
                meta = cls._parse_metadata(meta_str) if meta_str else {}
                try:
                    max_cap_str = meta.get("max_link_capacity", "1")
                    max_cap = int(max_cap_str)
                except ValueError:
                    raise ValueError(
                        f"Error on line {line_num}: max_link_capacity "
                        "must be an integer."
                    )

                try:
                    connections[conn_name_1] = Connection(
                        name=conn_name_1, zone1=z1, zone2=z2,
                        max_link_capacity=max_cap
                    )
                except ValidationError as e:
                    raise ValueError(
                        f"Error on line {line_num}: Connection Validation "
                        f"failed.\n{e}"
                    )

                adjacency[z1].append(z2)
                adjacency[z2].append(z1)
                continue

            raise ValueError(
                f"Parsing error: Invalid syntax -> '{line}'"
            )

        if not has_start or not has_end:
            raise ValueError(
                "Error: Map requires exactly one start_hub and one end_hub.",
            )
        start_hub = next(h for h in hubs.values() if h.role == HubRoles.start)
        drons = [
            Dron(id=f"D{i+1}", current_location=start_hub.name)
            for i in range(nb_drones)
        ]
        hubs[start_hub.name].occupants = nb_drones

        return Map(
            drons=drons, hubs=hubs, connections=connections,
            adjacency=adjacency
        )
