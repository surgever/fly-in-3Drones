import re
import sys
import heapq
from typing import List, Dict, Tuple, Optional, Set, Any
from elements import Map, ZoneType, DSt, HubRoles
from collections import defaultdict, deque

ANSI_COLORS: Dict[str, str] = {
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "white": "\033[97m",
    "gray": "\033[90m",
    "black": "\033[30m",
    "violet": "\033[38;5;91m",
    "purple": "\033[38;5;129m",
    "brown": "\033[38;5;130m",
    "orange": "\033[38;5;208m",
    "maroon": "\033[38;5;52m",
    "gold": "\033[38;5;220m",
    "darkred": "\033[38;5;88m",
    "crimson": "\033[38;5;196m",
    "lime": "\033[38;5;118m",
}
ANSI_RESET = "\033[0m"


class MapSimulator:
    '''Find best path, check occupations and run turns.'''

    def __init__(self, sim_map: Map) -> None:
        '''Set map and endpoints.'''
        self.map = sim_map
        self.start = next(
            h for h in self.map.hubs.values()if h.role == HubRoles.start).name
        self.end_hub = next(
            h for h in self.map.hubs.values() if h.role == HubRoles.end).name
        self.traps = self._detect_traps()

    def run(self) -> Tuple[int, str]:
        '''Runs the dynamic turn-by-turn pathfinding loop.'''
        total_turns = 0
        final_output = ""

        while any(d.state != DSt.delivered for d in self.map.drons):
            total_turns += 1
            turn_output: List[str] = []
            arrived_this_turn: Set[str] = set()
            links_used_this_turn: Dict[str, int] = {}

            self._process_arrivals(turn_output, arrived_this_turn)
            progress = self._process_dynamic_movements(
                turn_output, arrived_this_turn, links_used_this_turn)

            if turn_output:
                final_output += " ".join(turn_output) + "\n"
            elif not progress and not all(
                    d.state == DSt.delivered for d in self.map.drons):
                raise ValueError("Simulation deadlock was detected.")
                break

        return total_turns, final_output

    def _process_arrivals(
            self, turn_output: List[str], arrived_this_turn: Set[str]) -> None:
        '''Processes drones landing at destinations, and update status.'''
        for d in self.map.drons:
            if d.state == DSt.in_transit:
                d.turns_remaining -= 1
                if d.turns_remaining == 0:
                    dest = str(d.transit_destination)
                    conn = str(d.transit_connection)

                    self.map.connections[conn].occupants -= 1
                    d.current_location = dest
                    d.state = DSt.waiting
                    if dest == self.end_hub:
                        d.state = DSt.delivered
                    d.transit_destination = None
                    d.transit_connection = None

                    colored_text = self._get_colored_string(dest, dest)
                    turn_output.append(f"{d.id}-{colored_text}")
                    arrived_this_turn.add(d.id)

    def _process_dynamic_movements(
            self, turn_output: List[str],
            arrived_this_turn: Set[str], links_used_this_turn: Dict[str, int]
    ) -> bool:
        '''Run calculations to move available waiting droness.'''
        moved_this_turn: Set[str] = set()
        progress_made_overall = False

        while True:
            progress = False
            for d in self.map.drons:
                if (
                    d.state != DSt.waiting
                    or d.current_location == self.end_hub
                    or d.id in moved_this_turn or d.id in arrived_this_turn
                ):
                    continue

                path = self._find_shortest_path(
                    d.current_location, links_used_this_turn)
                if not path or len(path) < 2:
                    continue

                next_hub = path[1]
                target = self.map.hubs[next_hub]
                conn_name = self._get_connection_name(
                    d.current_location, next_hub)

                self._execute_drone_move(
                    d, next_hub, target, conn_name,
                    links_used_this_turn, turn_output)

                moved_this_turn.add(d.id)
                progress = True
                progress_made_overall = True

            if not progress:
                break

        return progress_made_overall

    def _execute_drone_move(
            self, d: Any, next_hub: str, target: Any, conn_name: str,
            links_used: Dict[str, int], turn_output: List[str]
    ) -> None:
        '''Updates drone state, capacities, and output.'''
        if d.current_location != self.start:
            self.map.hubs[d.current_location].occupants -= 1

        if target.zone_type == ZoneType.restricted:
            d.state = DSt.in_transit
            d.transit_destination = next_hub
            d.transit_connection = conn_name
            d.turns_remaining = 1

            self.map.connections[conn_name].occupants += 1
            target.occupants += 1

            colored = self._get_colored_string(conn_name, next_hub)
            turn_output.append(f"{d.id}-{colored}")
        else:
            d.current_location = next_hub
            links_used[conn_name] = links_used.get(conn_name, 0) + 1

            if next_hub == self.end_hub:
                d.state = DSt.delivered
            else:
                target.occupants += 1

            colored = self._get_colored_string(next_hub, next_hub)
            turn_output.append(f"{d.id}-{colored}")

    def _find_shortest_path(
            self, start: str, links_used: Dict[str, int]
    ) -> Optional[List[str]]:
        '''Dijkstra algorithm pondered with capacity, priority, and usage.'''
        queue: List[Tuple[float, int, str, List[str]]] = [
            (0.0, 0, start, [start])]
        visited: Dict[str, Tuple[float, int]] = {}

        while queue:
            cost, neg_prio, current, path = heapq.heappop(queue)

            if current == self.end_hub:
                return path

            if current in visited:
                prev_cost, prev_neg = visited[current]
                if cost > prev_cost or (
                    cost == prev_cost and neg_prio >= prev_neg
                ):
                    continue
            visited[current] = (cost, neg_prio)

            for neighbor in self.map.adjacency[current]:
                if self._evaluate_neighbor_node(
                    start, current, neighbor, links_used,
                    queue, cost, neg_prio, path
                ):
                    continue
        return None

    def _evaluate_neighbor_node(
            self, original_start: str, current: str,
            neighbor: str, links_used: Dict[str, int],
            queue: List[Tuple[float, int, str, List[str]]],
            cost: float, neg_prio: int, path: List[str]
    ) -> bool:
        '''Determines cost for traversing from current to neighboring node.'''
        target = self.map.hubs[neighbor]

        if target.zone_type == ZoneType.blocked:
            return True

        c_name = self._get_connection_name(current, neighbor)
        connection = self.map.connections[c_name]
        current_link_usage = connection.occupants + links_used.get(c_name, 0)
        is_immediate = (current == original_start)

        if is_immediate:
            if (target.occupants >= target.max_drones
                    and neighbor != self.end_hub):
                return True
            if current_link_usage >= connection.max_link_capacity:
                return True

        edge_cost = 2.0 if target.zone_type == ZoneType.restricted else 1.0
        is_prio = -1 if target.zone_type == ZoneType.priority else 0

        if not self.traps:
            if target.occupants > 0 and target.name != self.end_hub:
                edge_cost += 0.1
                if not is_immediate and target.occupants >= target.max_drones:
                    edge_cost += 1.0
            if (not is_immediate
                    and current_link_usage >= connection.max_link_capacity):
                edge_cost += 1.0
        elif target.zone_type == ZoneType.restricted and target.occupants == 0:
            edge_cost -= 0.5

        heapq.heappush(
            queue, (cost + edge_cost, neg_prio + is_prio,
                    neighbor, path + [neighbor]))
        return False

    def _get_connection_name(self, z1: str, z2: str) -> str:
        '''Look in dict of connection names.'''
        if f"{z1}-{z2}" in self.map.connections:
            return f"{z1}-{z2}"
        return f"{z2}-{z1}"

    def _get_colored_string(self, text: str, hub_name: str) -> str:
        '''Set terminal color for hubs.'''
        hub = self.map.hubs.get(hub_name)
        if not hub or not hub.color:
            return text

        color_name = hub.color.lower()
        if color_name == "rainbow":
            rainbow_sequence = [
                "\033[91m", "\033[38;5;208m", "\033[93m",
                "\033[92m", "\033[38;5;39m", "\033[38;5;54m", "\033[38;5;129m"]
            colored_text = "".join(
                rainbow_sequence[i % len(rainbow_sequence)]
                + char for i, char in enumerate(text))
            return f"{colored_text}{ANSI_RESET}"

        if color_name in ANSI_COLORS:
            return f"{ANSI_COLORS[color_name]}{text}{ANSI_RESET}"
        return text

    @staticmethod
    def clean_ansi_codes(text: str) -> str:
        """Removes ANSI terminal color codes."""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def _detect_traps(self) -> bool:
        paths_to_node: Dict[str, Set[int]] = {}
        queue: List[Tuple[str, List[str]]] = [(self.start, [self.start])]
        visited_in_4: Set[str] = set()

        while queue:
            curr, path = queue.pop(0)
            depth = len(path) - 1
            paths_to_node.setdefault(curr, set()).add(depth)
            if depth <= 4:
                visited_in_4.add(curr)
            if depth >= 6:
                continue

            for neighbor in self.map.adjacency[curr]:
                if neighbor not in path:
                    queue.append((neighbor, path + [neighbor]))

        congested = [
            h for h in [n for n, d in paths_to_node.items() if 4 in d]
            if not {0, 1, 2, 3} & paths_to_node[h]
            and {5, 6}.issubset(paths_to_node[h])
        ]

        final_hubs: List[str] = []
        for hub in congested:
            valid_restricted = [
                n for n in self.map.adjacency[hub]
                if self.map.hubs[n].zone_type == ZoneType.restricted
                and n not in visited_in_4
            ]
            if len(valid_restricted) == 2:
                final_hubs.append(hub)

        return len(final_hubs) > 0
