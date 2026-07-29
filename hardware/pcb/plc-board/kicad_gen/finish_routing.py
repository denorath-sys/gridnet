"""Route whatever Freerouting left behind, and fail loudly if it cannot.

Freerouting sometimes finishes this board reporting zero unrouted connections
and then hands back a session file that is missing some of them. The gaps seen
so far: J1 pad B7 -- the second of the two D- pads on the reversible USB-C
receptacle, whose partner pad sits physically between the pair on a 0.5mm
pitch -- and /USART2_RX, which comes back with U5's pad 40 sealed inside a
2x5.6mm pocket of F.Cu with no via site anywhere in it. Which gaps appear
varies between runs; that they are silent does not. The router's own success
report cannot be trusted, so the pipeline verifies with DRC and repairs what is
missing rather than assuming.

Repair is a maze router: a fixed grid, one connection at a time, two copper
layers, no rip-up except as a deliberate fallback. That is enough for
finishing a handful of leftover connections on an otherwise-routed board, and
unlike the autorouter it is deterministic.

Note on what does NOT work, so it is not tried again: routing these
connections *before* Freerouting, so it has to work around them, makes
Freerouting v2.2.4 either hang for over nine minutes or die outright with a
NullPointerException in its own PolylineTrace.normalize -- reliably, whenever
the pre-existing wiring lands on J1's 0.5mm-pitch pads. Repair after the fact
is the only order that works.

Run after importing the Freerouting session and before pouring ground:

    python3 finish_routing.py
"""

from __future__ import annotations

import heapq
import math
import json
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pcbnew

BOARD_PATH = "../plc-board.kicad_pcb"
# 0.05mm, not 0.1mm: J1's pad rows sit on a 0.5mm pitch with their centres at
# x.x5 coordinates, so a 0.1mm grid cannot land on a pad centre at all, and the
# escape lane between two neighbouring pads is exactly 0.45mm wide -- exactly
# the clearance a 0.2mm trace needs. Half a grid cell of rounding closes it.
GRID = 0.05         # mm per cell
CLEARANCE = 0.2     # mm, matches the board's Default netclass
# Geometry that clears by exactly the rule is legal (KiCad's DRC compares in
# integer nanometres), so back off by a hair to keep floating-point rounding
# from rejecting it.
EPSILON = 1e-6
TRACK_WIDTH = 0.2
VIA_DIAMETER = 0.6
VIA_DRILL = 0.3
BOARD_MARGIN = 0.5  # mm kept clear of the board outline
VIA_COST = 12       # in cells, to keep the router from stitching gratuitously


Cell = Tuple[int, int, int]  # (x index, y index, layer index 0=F.Cu 1=B.Cu)
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

# Net-specific track width and clearance, taken from the same table
# build_pcb.py writes into the project file. KiCad 9's Python binding returns
# NETINFO_ITEM.GetNetClass() as a bare SwigPyObject with no accessors, so the
# rules cannot be read back off the board; importing the source of truth is
# both simpler and harder to get out of step.
from build_pcb import NETCLASSES  # noqa: E402

NET_RULES = {
    net: (width, clearance)
    for _name, (width, clearance, nets) in NETCLASSES.items()
    for net in nets
}


def drc_unconnected(board_path: str) -> List[Tuple[float, float, float, float]]:
    """Ask kicad-cli which connections are missing.

    KiCad's ratsnest is not reachable through the Python API (GetRatsnestForNet
    hands back an opaque SWIG object), so the DRC report is the way to find out
    what is unconnected without reimplementing connectivity analysis.
    """
    with tempfile.NamedTemporaryFile(suffix=".json") as report:
        subprocess.run(
            ["kicad-cli", "pcb", "drc", board_path, "--format", "json",
             "--severity-all", "-o", report.name],
            check=True, capture_output=True,
        )
        data = json.load(open(report.name, encoding="utf-8"))

    pairs = []
    for violation in data.get("unconnected_items", []):
        items = violation.get("items", [])
        if len(items) == 2:
            a, b = (item["pos"] for item in items)
            pairs.append((a["x"], a["y"], b["x"], b["y"]))
    return pairs


class Grid:
    """Per-layer occupancy for one net's routing attempt."""

    def __init__(self, board: "pcbnew.BOARD", width_mm: float, height_mm: float) -> None:
        self.board = board
        self.nx = int(width_mm / GRID) + 1
        self.ny = int(height_mm / GRID) + 1
        self.width_mm = width_mm
        self.height_mm = height_mm

    def _blank(self) -> "np.ndarray":
        return np.zeros((self.nx, self.ny), dtype=bool)

    def _stamp(self, grid: "np.ndarray", a: Tuple[float, float], b: Tuple[float, float], radius: float) -> None:
        """Mark every cell whose centre is within `radius` of segment ab."""
        lo_x = max(0, int((min(a[0], b[0]) - radius) / GRID))
        hi_x = min(self.nx - 1, int((max(a[0], b[0]) + radius) / GRID) + 1)
        lo_y = max(0, int((min(a[1], b[1]) - radius) / GRID))
        hi_y = min(self.ny - 1, int((max(a[1], b[1]) + radius) / GRID) + 1)
        if lo_x > hi_x or lo_y > hi_y:
            return
        xs = np.arange(lo_x, hi_x + 1) * GRID
        ys = np.arange(lo_y, hi_y + 1) * GRID
        px, py = np.meshgrid(xs, ys, indexing="ij")
        ax, ay = a
        ex, ey = b[0] - a[0], b[1] - a[1]
        length_sq = ex * ex + ey * ey
        if length_sq == 0:
            t = np.zeros_like(px)
        else:
            t = np.clip(((px - ax) * ex + (py - ay) * ey) / length_sq, 0.0, 1.0)
        dist_sq = (px - (ax + t * ex)) ** 2 + (py - (ay + t * ey)) ** 2
        limit = max(radius - EPSILON, 0.0)
        grid[lo_x:hi_x + 1, lo_y:hi_y + 1] |= dist_sq < limit * limit

    def _stamp_box(self, grid: "np.ndarray", rect: Tuple[float, float, float, float], margin: float) -> None:
        """Mark every cell inside `rect` grown by `margin` on all sides."""
        left, top, right, bottom = rect
        lo_x = max(0, int((left - margin) / GRID) + 1)
        hi_x = min(self.nx - 1, int((right + margin) / GRID))
        lo_y = max(0, int((top - margin) / GRID) + 1)
        hi_y = min(self.ny - 1, int((bottom + margin) / GRID))
        if lo_x > hi_x or lo_y > hi_y:
            return
        grid[lo_x:hi_x + 1, lo_y:hi_y + 1] = True

    def rules_for(self, net_code: int) -> Tuple[float, float]:
        """(track width, clearance) in mm for this net, from its netclass.

        Not the module constants. This board has a Mains netclass at 1.0mm /
        2.5mm, and the repair router used to lay 0.2mm track at 0.2mm
        clearance into it -- which on the mains side is not a style question,
        it is the live-to-neutral spacing. Seven clearance errors in one run,
        every one of them on /AC_L, /AC_N or /PLC_LINE, all of them laid by
        this router while 'finishing' what the autorouter dropped.
        """
        net = self.board.FindNet(net_code)
        if net is None:
            return TRACK_WIDTH, CLEARANCE
        return NET_RULES.get(net.GetNetname(), (TRACK_WIDTH, CLEARANCE))

    def build(self, net_code: int) -> Tuple[List["np.ndarray"], List["np.ndarray"]]:
        """Return (blocked-for-track, blocked-for-via) grids.

        Copper already on the net being routed is not an obstacle -- the
        router is free to run along it, since joining it is the whole point.
        """
        width, clearance = self.rules_for(net_code)
        track_radius = width / 2 + clearance
        via_radius = VIA_DIAMETER / 2 + clearance

        blocked = [self._blank(), self._blank()]
        via_blocked = [self._blank(), self._blank()]

        def obstacle(layer_idx: Optional[int], a, b, half_width: float) -> None:
            targets = [layer_idx] if layer_idx is not None else [0, 1]
            for idx in targets:
                self._stamp(blocked[idx], a, b, half_width + track_radius)
                self._stamp(via_blocked[idx], a, b, half_width + via_radius)

        for item in self.board.GetTracks():
            is_via = isinstance(item, pcbnew.PCB_VIA)
            pos_a = (item.GetStart().x / 1e6, item.GetStart().y / 1e6)
            pos_b = (item.GetEnd().x / 1e6, item.GetEnd().y / 1e6)
            half = (item.GetWidth(pcbnew.F_Cu) if is_via else item.GetWidth()) / 2e6
            if item.GetNetCode() == net_code:
                continue
            if not is_via and item.GetLayer() not in LAYERS:
                # Copper on an inner plane layer. This router only lays track
                # on F.Cu and B.Cu, and inner-plane copper does not obstruct
                # either -- the plane refill after routing carves its own
                # clearance around whatever vias end up going through it.
                continue
            obstacle(None if is_via else LAYERS.index(item.GetLayer()), pos_a, pos_b, half)

        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetNetCode() == net_code:
                    continue
                # Pads are stamped as rectangles, not as the stadium shape an
                # earlier version used: a stadium tucks inside a rectangle's
                # corners, so a via placed diagonally off a 0603 pad passed the
                # check and then failed DRC by 0.03mm. Growing the bounding box
                # instead over-blocks the corners slightly, which is the safe
                # direction to be wrong in.
                box = pad.GetBoundingBox()
                rect = (box.GetLeft() / 1e6, box.GetTop() / 1e6,
                        box.GetRight() / 1e6, box.GetBottom() / 1e6)
                on_front = pad.IsOnLayer(pcbnew.F_Cu)
                on_back = pad.IsOnLayer(pcbnew.B_Cu)
                layers = [0] if on_front and not on_back else ([1] if on_back and not on_front else [0, 1])
                for idx in layers:
                    self._stamp_box(blocked[idx], rect, track_radius)
                    self._stamp_box(via_blocked[idx], rect, via_radius)

        # Rule areas -- the isolation barrier, and both antenna keepouts.
        #
        # Freerouting is told about these through the DSN's `keepout` records.
        # This router is told about them here, and it has to be: it is the
        # step that runs *after* the autorouter, on exactly the connections
        # the autorouter could not place, which is precisely when an empty
        # 8mm-wide corridor down the middle of the board looks attractive. A
        # repair that closes a net by cutting through the mains barrier is a
        # worse outcome than the unrouted net it fixes.
        #
        # Both board-level zones and footprint-level ones (the ESP32 module
        # carries its antenna keepout inside its own footprint) are collected.
        rule_areas = [z for z in self.board.Zones() if z.GetIsRuleArea()]
        for footprint in self.board.GetFootprints():
            rule_areas += [z for z in footprint.Zones() if z.GetIsRuleArea()]
        for zone in rule_areas:
            box = zone.Outline().BBox()
            rect = (box.GetLeft() / 1e6, box.GetTop() / 1e6,
                    box.GetRight() / 1e6, box.GetBottom() / 1e6)
            for idx in range(2):
                # Half the track, not the clearance. A keepout is a boundary,
                # not a conductor: copper may come right up to its edge, it
                # just may not cross. Stamping it with the netclass clearance
                # put a 3mm halo around the isolation band for mains nets --
                # reaching x=29.02, which swallowed T1's own mains pad at
                # 30.92 and made that pad unroutable by construction. /AC_N
                # failed identically on every attempt of two runs before this
                # was found.
                self._stamp_box(blocked[idx], rect, width / 2)
                self._stamp_box(via_blocked[idx], rect, VIA_DIAMETER / 2)

        # Keep off the board edge.
        edge = int(BOARD_MARGIN / GRID)
        for grid in blocked + via_blocked:
            grid[:edge, :] = True
            grid[-edge:, :] = True
            grid[:, :edge] = True
            grid[:, -edge:] = True

        return blocked, via_blocked

    def simplify(self, path: List[Cell], blocked: List["np.ndarray"], goals) -> List[Cell]:
        """Pull the staircase straight.

        A* on a four-neighbour grid can only step along the axes, so a route
        that wants to go diagonally comes out as dozens of alternating
        one-cell jogs. Left alone those become dozens of copper segments,
        which is both ugly and hard for the autorouter to work around
        afterwards. This walks the path and replaces each run it can with a
        single straight line, keeping the layer changes where they are.
        """
        def line_clear(a: Cell, b: Cell) -> bool:
            if a[2] != b[2]:
                return False
            # Horizontal, vertical or exactly 45 degrees. Arbitrary angles are
            # legal copper but they are not what a PCB looks like, and
            # Freerouting slows to a crawl trying to route around pre-existing
            # wiring at odd angles -- a 50-second run became a 9-minute
            # timeout before this restriction went in.
            dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
            if dx and dy and dx != dy:
                return False
            layer = a[2]
            steps = max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 2
            for i in range(steps + 1):
                t = i / steps if steps else 0.0
                x = int(round(a[0] + (b[0] - a[0]) * t))
                y = int(round(a[1] + (b[1] - a[1]) * t))
                if blocked[layer][x, y] and (x, y, layer) not in goals:
                    return False
            return True

        simplified = [path[0]]
        i = 0
        while i < len(path) - 1:
            best = i + 1
            for j in range(len(path) - 1, i, -1):
                if line_clear(path[i], path[j]):
                    best = j
                    break
            simplified.append(path[best])
            i = best
        return simplified

    def route(
        self,
        start: Tuple[float, float],
        start_layers: Sequence[int],
        target: Tuple[float, float],
        target_layers: Sequence[int],
        net_code: int,
    ) -> Optional[List[Cell]]:
        blocked, via_blocked = self.build(net_code)
        sx, sy = int(round(start[0] / GRID)), int(round(start[1] / GRID))
        tx, ty = int(round(target[0] / GRID)), int(round(target[1] / GRID))
        if not (0 <= sx < self.nx and 0 <= sy < self.ny):
            return None
        goals = {(tx, ty, layer) for layer in target_layers}

        # A* with integer costs: 1 per orthogonal step, VIA_COST per layer
        # change (a plain BFS would treat vias as free and stitch between
        # layers constantly). The heuristic is Manhattan distance to the
        # target, which never overestimates, so the result is still optimal --
        # it just stops the search fanning out across the whole board, which
        # matters on an otherwise-empty board where there is nothing to
        # constrain it.
        INF = 1 << 30
        dist: Dict[Cell, int] = {}
        prev: Dict[Cell, Optional[Cell]] = {}
        queue: List[Tuple[int, Cell]] = []

        def heuristic(x: int, y: int) -> int:
            return abs(x - tx) + abs(y - ty)

        for layer in start_layers:
            cell = (sx, sy, layer)
            dist[cell] = 0
            prev[cell] = None
            heapq.heappush(queue, (heuristic(sx, sy), cell))

        while queue:
            _priority, cell = heapq.heappop(queue)
            x, y, layer = cell
            if cell in goals:
                path = []
                node: Optional[Cell] = cell
                while node is not None:
                    path.append(node)
                    node = prev[node]
                return self.simplify(list(reversed(path)), blocked, goals)

            base = dist[cell]
            neighbours = (
                ((x + 1, y, layer), 1), ((x - 1, y, layer), 1),
                ((x, y + 1, layer), 1), ((x, y - 1, layer), 1),
                ((x, y, 1 - layer), VIA_COST),
            )
            for nb, step in neighbours:
                nx_, ny_, nl = nb
                if not (0 <= nx_ < self.nx and 0 <= ny_ < self.ny):
                    continue
                if step == VIA_COST:
                    if via_blocked[0][nx_, ny_] or via_blocked[1][nx_, ny_]:
                        continue
                elif blocked[nl][nx_, ny_] and nb not in goals:
                    continue
                nd = base + step
                if nd < dist.get(nb, INF):
                    dist[nb] = nd
                    prev[nb] = cell
                    heapq.heappush(queue, (nd + heuristic(nx_, ny_), nb))
        return None


def path_to_tracks(board: "pcbnew.BOARD", path: Sequence[Cell], net: "pcbnew.NETINFO_ITEM") -> int:
    """Turn a simplified path into copper: a track per leg, a via per layer change."""
    added = 0

    def point(cell: Cell) -> "pcbnew.VECTOR2I":
        return pcbnew.VECTOR2I(pcbnew.FromMM(cell[0] * GRID), pcbnew.FromMM(cell[1] * GRID))

    for previous, cell in zip(path, path[1:]):
        if cell[2] != previous[2]:
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(point(cell))
            # SetFrontWidth, not the layer-less SetWidth: KiCad 9's padstack
            # model wants a layer, and the one-argument overload trips an
            # assertion per via. Same fix as build_pcb.py's make_via().
            via.SetFrontWidth(pcbnew.FromMM(VIA_DIAMETER))
            via.SetDrill(pcbnew.FromMM(VIA_DRILL))
            via.SetNet(net)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            board.Add(via)
            added += 1
        elif previous[:2] != cell[:2]:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(point(previous))
            track.SetEnd(point(cell))
            width, _clearance = NET_RULES.get(net.GetNetname(), (TRACK_WIDTH, CLEARANCE)) if net else (TRACK_WIDTH, CLEARANCE)
            track.SetWidth(pcbnew.FromMM(width))
            track.SetLayer(LAYERS[cell[2]])
            track.SetNet(net)
            board.Add(track)
            added += 1
    return added


def route_pad_chain(board: "pcbnew.BOARD", grid: "Grid", net: "pcbnew.NETINFO_ITEM") -> bool:
    """Route every pad of a net, nearest-neighbour, joining as it goes."""
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads() if pad.GetNetCode() == net.GetNetCode()]
    if len(pads) < 2:
        return False
    remaining, current, total = pads[1:], pads[0], 0
    while remaining:
        here = (current.GetPosition().x / 1e6, current.GetPosition().y / 1e6)
        remaining.sort(key=lambda p: (p.GetPosition().x / 1e6 - here[0]) ** 2
                       + (p.GetPosition().y / 1e6 - here[1]) ** 2)
        nxt = remaining.pop(0)
        target = (nxt.GetPosition().x / 1e6, nxt.GetPosition().y / 1e6)
        start_layers = [i for i, layer in enumerate(LAYERS) if current.IsOnLayer(layer)] or [0]
        target_layers = [i for i, layer in enumerate(LAYERS) if nxt.IsOnLayer(layer)] or [0]
        path = grid.route(here, start_layers, target, target_layers, net.GetNetCode())
        if path is None:
            return False
        total += path_to_tracks(board, path, net)
        current = nxt
    print(f"re-routed {net.GetNetname()} from scratch: {total} segments/vias")
    return True


def rip_up_and_reroute(
    board: "pcbnew.BOARD",
    grid: "Grid",
    net: "pcbnew.NETINFO_ITEM",
    near: Optional[Tuple[float, float]] = None,
    radius: float = 3.0,
) -> bool:
    """Delete a net's copper and route it again; restore everything if that fails.

    Widens to neighbouring nets when `near` is given. J1's D+ and D- pads
    interleave -- each pair has the other signal's pad sitting between them on
    a 0.5mm pitch -- so whichever pair Freerouting routes first takes the only
    corridor and strands the other. Ripping up just the stranded net does not
    help, because what is in its way belongs to its neighbour. Everything with
    copper near the stranded pad comes up together, the stranded net is routed
    first, and the rest are put back afterwards.
    """
    victims = [net.GetNetCode()]
    if near is not None:
        for item in board.GetTracks():
            code = item.GetNetCode()
            if code in victims or code == 0:
                continue
            for end in (item.GetStart(), item.GetEnd()):
                if math.hypot(end.x / 1e6 - near[0], end.y / 1e6 - near[1]) <= radius:
                    victims.append(code)
                    break

    doomed = [t for t in board.GetTracks() if t.GetNetCode() in victims]
    for track in doomed:
        board.Remove(track)

    routed = []
    for code in victims:
        victim_net = board.FindNet(code)
        if route_pad_chain(board, grid, victim_net):
            routed.append(code)
            continue
        # Undo everything: the partial results are worse than what was there.
        for track in list(board.GetTracks()):
            if track.GetNetCode() in routed or track.GetNetCode() == code:
                if track not in doomed:
                    board.Remove(track)
        for track in doomed:
            board.Add(track)
        return False
    return True


def plane_layers_for(board: "pcbnew.BOARD", net_code: int) -> List[int]:
    """Inner copper layers carrying a filled plane for this net."""
    layers = []
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetCode() != net_code:
            continue
        layer = zone.GetLayer()
        if layer not in LAYERS and not zone.GetFilledPolysList(layer).IsEmpty():
            layers.append(layer)
    return layers


def existing_net_copper(board: "pcbnew.BOARD", net_code: int) -> List[Tuple[float, float, float]]:
    """(x, y, radius) for every via and pad already on this net.

    A via dropped on top of one of these connects nothing: the copper is
    already there and already on the net. Same-net copper is deliberately not
    an obstacle to the maze router -- joining it is the point -- which is
    exactly why a via site has to be checked against it separately. Without
    this the stitcher picks the same spot every round, because the via it left
    there last round is invisible to it.
    """
    spots = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA) and item.GetNetCode() == net_code:
            pos = item.GetPosition()
            spots.append((pos.x / 1e6, pos.y / 1e6, item.GetWidth(pcbnew.F_Cu) / 2e6))
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetCode() != net_code:
                continue
            box = pad.GetBoundingBox()
            spots.append((
                (box.GetLeft() + box.GetRight()) / 2e6,
                (box.GetTop() + box.GetBottom()) / 2e6,
                max(box.GetWidth(), box.GetHeight()) / 2e6,
            ))
    return spots


def drop_via_to_plane(
    board: "pcbnew.BOARD",
    grid: "Grid",
    net: "pcbnew.NETINFO_ITEM",
    origin: Tuple[float, float],
    origin_layers: List[int],
) -> bool:
    """Run a short track from `origin` to the nearest usable via site and stitch
    down to this net's plane.

    On a board with power planes this is usually the *correct* repair rather
    than a fallback: a pad on a planed net does not need a track to another
    pad, it needs a via to its own plane. Freerouting knows that and uses it.

    "Usable" carries weight. The site has to be reachable by the same maze
    router that lays everything else -- so clearance, keepouts and existing
    copper are all handled the way they already are -- *and* it has to be
    somewhere this net does not already have copper. Skipping that second test
    is what made an earlier version stitch the identical point three runs
    running, once 0.1mm from pin 48's own pad.
    """
    import math

    if not plane_layers_for(board, net.GetNetCode()):
        return False
    occupied = existing_net_copper(board, net.GetNetCode())
    blocked, via_blocked = grid.build(net.GetNetCode())
    x0, y0 = origin
    clear = VIA_DIAMETER / 2 + CLEARANCE

    def adds_nothing(x: float, y: float) -> bool:
        return any((x - sx) ** 2 + (y - sy) ** 2 < (r + clear) ** 2 for sx, sy, r in occupied)

    # Sweep outwards. Near beats far, for inductance and for board area alike.
    for radius in [r / 10 for r in range(8, 121, 2)]:
        for angle in range(0, 360, 10):
            x = x0 + radius * math.cos(math.radians(angle))
            y = y0 + radius * math.sin(math.radians(angle))
            gx, gy = int(round(x / GRID)), int(round(y / GRID))
            if not (0 <= gx < grid.nx and 0 <= gy < grid.ny):
                continue
            if any(via_blocked[i][gx, gy] for i in range(len(LAYERS))):
                continue
            if adds_nothing(x, y):
                continue
            path = grid.route(origin, origin_layers, (x, y), list(range(len(LAYERS))), net.GetNetCode())
            if path is None:
                continue
            added = path_to_tracks(board, path, net)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
            via.SetFrontWidth(pcbnew.FromMM(VIA_DIAMETER))
            via.SetDrill(pcbnew.FromMM(VIA_DRILL))
            via.SetNet(net)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            board.Add(via)
            print(
                f"stitched {net.GetNetname()} at ({x0:.2f},{y0:.2f}) down to its plane "
                f"via ({x:.2f},{y:.2f}): {added} segments + 1 via"
            )
            return True
    return False


def repair_one(board: "pcbnew.BOARD", pair: Tuple[float, float, float, float]) -> Optional[str]:
    """Fix a single unconnected pair. Returns an error string, or None on success."""
    x1, y1, x2, y2 = pair
    box = board.GetBoardEdgesBoundingBox()
    grid = Grid(board, box.GetWidth() / 1e6 + 1.0, box.GetHeight() / 1e6 + 1.0)

    def endpoint(x: float, y: float) -> Optional[Tuple[int, List[int]]]:
        """(net code, layer indices) for whatever copper sits at (x, y).

        DRC reports each end as either a pad or a track; both are valid places
        to start or finish, but they answer "which layers am I on?" differently.
        """
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                pos = pad.GetPosition()
                if abs(pos.x / 1e6 - x) < 0.02 and abs(pos.y / 1e6 - y) < 0.02:
                    layers = [i for i, layer in enumerate(LAYERS) if pad.IsOnLayer(layer)]
                    return pad.GetNetCode(), layers or [0]
        for item in board.GetTracks():
            if isinstance(item, pcbnew.PCB_VIA):
                pos = item.GetPosition()
                if abs(pos.x / 1e6 - x) < 0.02 and abs(pos.y / 1e6 - y) < 0.02:
                    return item.GetNetCode(), [0, 1]
                continue
            for end in (item.GetStart(), item.GetEnd()):
                if abs(end.x / 1e6 - x) < 0.02 and abs(end.y / 1e6 - y) < 0.02:
                    layer = item.GetLayer()
                    # A track end on an inner plane layer is reachable from
                    # either signal layer through a via, so offer both rather
                    # than looking up an index that does not exist there.
                    if layer not in LAYERS:
                        return item.GetNetCode(), [0, 1]
                    return item.GetNetCode(), [LAYERS.index(layer)]
        return None

    def is_pad(x: float, y: float) -> bool:
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                pos = pad.GetPosition()
                if abs(pos.x / 1e6 - x) < 0.02 and abs(pos.y / 1e6 - y) < 0.02:
                    return True
        return False

    start = endpoint(x1, y1)
    target = endpoint(x2, y2)
    if start is None or target is None:
        return f"({x1:.2f},{y1:.2f}) -> ({x2:.2f},{y2:.2f}): could not identify both ends"
    net_code, start_layers = start
    _target_net, target_layers = target
    net = board.FindNet(net_code)

    path = grid.route((x1, y1), start_layers, (x2, y2), target_layers, net_code)
    if path is not None:
        added = path_to_tracks(board, path, net)
        print(
            f"finished {net.GetNetname()} ({x1:.2f},{y1:.2f}) -> ({x2:.2f},{y2:.2f}): "
            f"{added} segments/vias"
        )
        return None

    # Nothing reaches the stranded pad. Usually that is because copper laid by
    # the autorouter is sitting in the one corridor the pad could have used --
    # it routes J1's first D+ pad straight through the gap the second D+ pad
    # needed. That copper is not an obstacle to *this* search (same net), but
    # the commitment is already made. So throw it away and start over: this
    # net alone first, then this net together with its neighbours.
    if rip_up_and_reroute(board, grid, net) or rip_up_and_reroute(board, grid, net, near=(x2, y2)):
        return None

    # Last resort, and on a board with power planes the *correct* answer more
    # often than the ones above: a pad on a planed net does not need a track to
    # another pad at all. It needs a via down to its own plane.
    #
    # Freerouting knows that and uses it; this router did not, which is why
    # both four-layer runs ended holding a pair of adjacent ST7580 right-edge
    # pads it could not join -- pins 31 and 34, 1.55mm apart, each already
    # sitting over 5000mm2 of the very net it was trying to reach.
    # Pads first. A track end on a planed net is copper that already goes
    # somewhere; the pad is the thing that needs to get down to the plane, and
    # stitching the wrong end leaves the reported gap exactly where it was.
    ends = [((x1, y1), start_layers), ((x2, y2), target_layers)]
    ends.sort(key=lambda e: not is_pad(*e[0]))
    for origin, layers in ends:
        if drop_via_to_plane(board, grid, net, origin, layers):
            return None

    return (
        f"{net.GetNetname()}: no route from ({x1:.2f},{y1:.2f}) to ({x2:.2f},{y2:.2f}), "
        "and re-routing its neighbourhood did not help either"
    )


def main() -> None:
    # One repair per round, re-checking with DRC in between. Repairs change
    # the board -- a rip-up can complete several connections at once, or move
    # where the remaining gap is -- so a list of pairs collected up front goes
    # stale after the first fix and produces phantom failures.
    attempted: set = set()
    while True:
        pairs = drc_unconnected(BOARD_PATH)
        if not pairs:
            print("routing complete -- DRC reports no unconnected items")
            return
        pair = next((p for p in pairs if p not in attempted), None)
        if pair is None:
            print("could not finish:", *sorted(f"{p}" for p in pairs), sep="\n  ")
            sys.exit(1)
        attempted.add(pair)

        board = pcbnew.LoadBoard(BOARD_PATH)
        error = repair_one(board, pair)
        if error:
            print("could not finish:\n  " + error)
            sys.exit(1)
        board.Save(BOARD_PATH)


if __name__ == "__main__":
    main()
