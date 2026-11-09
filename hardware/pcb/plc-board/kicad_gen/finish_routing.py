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
MAX_REPAIRS = 60    # rounds, each one DRC check plus one attempted repair


Cell = Tuple[int, int, int]  # (x index, y index, layer index 0=F.Cu 1=B.Cu)
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

# Net-specific track width and clearance, taken from the same table
# build_pcb.py writes into the project file. KiCad 9's Python binding returns
# NETINFO_ITEM.GetNetClass() as a bare SwigPyObject with no accessors, so the
# rules cannot be read back off the board; importing the source of truth is
# both simpler and harder to get out of step.
from build_pcb import (  # noqa: E402
    ESCAPE_AREAS, ESCAPE_CLEARANCE, ESCAPE_WIDTH, NETCLASSES, PLANES,
    escape_area_name, escape_nets,
)

NET_RULES = {
    net: (width, clearance)
    for _name, (width, clearance, nets) in NETCLASSES.items()
    for net in nets
}

PLANE_NETS = {name for name, _layer in PLANES}


def segment_distance(item: "pcbnew.PCB_TRACK", point: Tuple[float, float]) -> float:
    """Distance in mm from `point` to a track's centreline (or a via's centre).

    Not to its endpoints. A long track running straight past a stranded pad
    has both ends far away and is exactly as much in the way.
    """
    ax, ay = item.GetStart().x / 1e6, item.GetStart().y / 1e6
    bx, by = item.GetEnd().x / 1e6, item.GetEnd().y / 1e6
    ex, ey = bx - ax, by - ay
    length_sq = ex * ex + ey * ey
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((point[0] - ax) * ex + (point[1] - ay) * ey) / length_sq))
    return math.hypot(point[0] - (ax + t * ex), point[1] - (ay + t * ey))


def board_outline(board: "pcbnew.BOARD") -> Tuple[float, float, float, float]:
    """(left, top, right, bottom) in mm of the Edge.Cuts geometry itself.

    Not GetBoardEdgesBoundingBox(), which includes the outline's drawn line
    width and so sits 0.05mm outside the real edge on every side. Measured
    from that, a Freerouting track 0.465mm from the top edge passed the
    0.5mm check, and the repair router itself laid track 0.45mm from it --
    six times over, each one "finishing" a gap it had not closed.
    """
    xs, ys = [], []
    for item in board.GetDrawings():
        if item.GetLayer() != pcbnew.Edge_Cuts:
            continue
        for point in (item.GetStart(), item.GetEnd()):
            xs.append(point.x / 1e6)
            ys.append(point.y / 1e6)
    if not xs:
        raise SystemExit("board has no Edge.Cuts outline")
    return min(xs), min(ys), max(xs), max(ys)


def refill_zones(board: "pcbnew.BOARD") -> None:
    """Re-pour every copper zone around whatever copper is on the board now.

    The pour runs *before* repair (see route.sh), so every track this script
    lays goes down on top of an existing GND fill, and the router does not
    treat that fill as an obstacle -- it is about to be recomputed, and the
    refill is what carves clearance around the new copper. Until then the
    stale fill overlaps it, which is a short as far as DRC is concerned. So
    the refill happens after every repair, before the board is saved and
    before DRC is asked what is still unconnected: a refill can strand a
    piece of pour as easily as it frees one.
    """
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    pcbnew.ZONE_FILLER(board).Fill(zones)


def save_refilled(board: "pcbnew.BOARD", path: str) -> None:
    """Save `board`, then refill its zones in a separate Python process.

    Not on the board in hand, and not even in this process. Once items have
    been taken off a board -- every rip-up and the edge-clearance strip do --
    KiCad 9's SWIG layer starts reporting "memory leak of type 'PCB_TRACK *',
    no destructor found", and from then on it hands back *any* board's
    Zones(), even one freshly loaded from disk, as bare SwigPyObjects; the
    process then segfaults on exit. A clean interpreter has none of that.
    """
    board.Save(path)
    subprocess.run(
        [sys.executable, "-c",
         "import sys, pcbnew\n"
         "b = pcbnew.LoadBoard(sys.argv[1])\n"
         "zones = [z for z in b.Zones() if not z.GetIsRuleArea()]\n"
         "pcbnew.ZONE_FILLER(b).Fill(zones)\n"
         "b.Save(sys.argv[1])\n",
         path],
        check=True, capture_output=True,
    )


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
        # The U4 escape areas (see build_pcb.ESCAPE_AREAS): inside one,
        # clearance is ESCAPE_CLEARANCE, and the part's signal nets route at
        # ESCAPE_WIDTH everywhere.
        self.escape_rects = []
        names = {escape_area_name(ref) for ref in ESCAPE_AREAS}
        for zone in board.Zones():
            if zone.GetIsRuleArea() and zone.GetZoneName() in names:
                box = zone.Outline().BBox()
                self.escape_rects.append((box.GetLeft() / 1e6, box.GetTop() / 1e6,
                                          box.GetRight() / 1e6, box.GetBottom() / 1e6))
        self.escape_nets = set(escape_nets(board))
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
        if net.GetNetname() in self.escape_nets:
            return ESCAPE_WIDTH, CLEARANCE
        return NET_RULES.get(net.GetNetname(), (TRACK_WIDTH, CLEARANCE))

    def in_escape(self, rect: Tuple[float, float, float, float]) -> bool:
        """Does this bounding box touch an escape area?"""
        left, top, right, bottom = rect
        return any(left <= r and right >= l and top <= b and bottom >= t
                   for l, t, r, b in self.escape_rects)

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

        # Inside an escape area the clearance to an obstacle is the escape
        # rule's. Decided per obstacle, by whether it touches the area: the
        # DRC rule matches when either item does, so this is the conservative
        # half of it.
        def radii(rect) -> Tuple[float, float]:
            clr = min(clearance, ESCAPE_CLEARANCE) if self.in_escape(rect) else clearance
            return width / 2 + clr, VIA_DIAMETER / 2 + clr

        def obstacle(layer_idx: Optional[int], a, b, half_width: float) -> None:
            t_radius, v_radius = radii((min(a[0], b[0]) - half_width, min(a[1], b[1]) - half_width,
                                        max(a[0], b[0]) + half_width, max(a[1], b[1]) + half_width))
            targets = [layer_idx] if layer_idx is not None else [0, 1]
            for idx in targets:
                self._stamp(blocked[idx], a, b, half_width + t_radius)
                self._stamp(via_blocked[idx], a, b, half_width + v_radius)

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
                t_radius, v_radius = radii(rect)
                for idx in layers:
                    self._stamp_box(blocked[idx], rect, t_radius)
                    self._stamp_box(via_blocked[idx], rect, v_radius)

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
            # By what the area forbids, not by being a rule area: the escape
            # areas forbid nothing and exist only to be named by a DRC rule.
            for idx in range(2):
                # Half the track, not the clearance. A keepout is a boundary,
                # not a conductor: copper may come right up to its edge, it
                # just may not cross. Stamping it with the netclass clearance
                # put a 3mm halo around the isolation band for mains nets --
                # reaching x=29.02, which swallowed T1's own mains pad at
                # 30.92 and made that pad unroutable by construction. /AC_N
                # failed identically on every attempt of two runs before this
                # was found.
                if zone.GetDoNotAllowTracks():
                    self._stamp_box(blocked[idx], rect, width / 2)
                if zone.GetDoNotAllowVias():
                    self._stamp_box(via_blocked[idx], rect, VIA_DIAMETER / 2)

        # Keep off the board edge -- measured from the copper's edge, and from
        # the board's real outline.
        #
        # Both used to be wrong. The margin was applied to a track's
        # centreline, so a track the router laid exactly on the margin sat
        # 0.1mm inside the 0.5mm rule. And the far edges were counted from the
        # end of the grid, which is built 1mm larger than the board: on the
        # right and bottom the blocked strip lay off the board entirely and
        # the router could run copper up to the outline.
        left, top, right, bottom = board_outline(self.board)
        for grids, half in ((blocked, width / 2), (via_blocked, VIA_DIAMETER / 2)):
            margin = BOARD_MARGIN + half
            lo_x = int(math.ceil((left + margin) / GRID - EPSILON))
            hi_x = int(math.floor((right - margin) / GRID + EPSILON))
            lo_y = int(math.ceil((top + margin) / GRID - EPSILON))
            hi_y = int(math.floor((bottom - margin) / GRID + EPSILON))
            for grid in grids:
                grid[:max(lo_x, 0), :] = True
                grid[hi_x + 1:, :] = True
                grid[:, :max(lo_y, 0)] = True
                grid[:, hi_y + 1:] = True

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


def path_to_tracks(board: "pcbnew.BOARD", grid: "Grid", path: Sequence[Cell], net: "pcbnew.NETINFO_ITEM") -> int:
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
            width, _clearance = grid.rules_for(net.GetNetCode()) if net else (TRACK_WIDTH, CLEARANCE)
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
        total += path_to_tracks(board, grid, path, net)
        current = nxt
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

    Planed nets are the exception. On this board the copper in a stranded
    pad's way is as often GND or +5V as a signal -- /PLC_LED on U4's pin 41
    was walled in by a GND via Freerouting put 1mm from the pad -- and
    re-routing GND "from scratch" as a pad chain would mean threading a track
    through every ground pad on the board. So a planed neighbour loses only
    its copper inside the neighbourhood, and is not re-routed here at all: the
    pieces that cut off show up in the next DRC round as ordinary unconnected
    pairs, and the plane-stitching repair below closes them with a via to
    their own plane, which is what that copper was doing anyway.
    """
    victims = [net.GetNetCode()]
    local_only: List["pcbnew.PCB_TRACK"] = []
    if near is not None:
        for item in board.GetTracks():
            code = item.GetNetCode()
            if code in victims or code == 0 or item.IsLocked():
                continue
            if segment_distance(item, near) > radius:
                continue
            if board.FindNet(code).GetNetname() in PLANE_NETS:
                local_only.append(item)
            else:
                victims.append(code)

    # Locked copper stays: build_pcb.py locks what it places on purpose
    # (thermal, stitching and fanout vias, fanout stubs), and none of it is
    # something a pad chain would rebuild.
    doomed = [t for t in board.GetTracks() if t.GetNetCode() in victims and not t.IsLocked()] + local_only
    for track in doomed:
        board.Remove(track)

    # Order matters, and the first order tried is rarely the right one. The
    # stranded net goes first and takes the shortest way out, which is usually
    # straight across the neighbour it was competing with: in the first run
    # with this loop, all four set-aside nets were routed and then lost
    # because one neighbour (/ST_BR0, /ST_RXD, /ST_CL, /ST_RESETN) could not
    # get back in. So a victim that fails moves to the front and the whole
    # set is tried again, until every net has had a turn at the front or an
    # order repeats.
    order = list(victims)
    tried = set()
    while tuple(order) not in tried:
        tried.add(tuple(order))
        routed: List[int] = []
        failed_code = None
        for code in order:
            if route_pad_chain(board, grid, board.FindNet(code)):
                routed.append(code)
            else:
                failed_code = code
                break
        if failed_code is None:
            break
        # Clear this attempt's copper before the next order: partial results
        # are worse than what was there.
        for track in list(board.GetTracks()):
            if (track.GetNetCode() in routed or track.GetNetCode() == failed_code) and not track.IsLocked():
                board.Remove(track)
        order.remove(failed_code)
        order.insert(0, failed_code)
    else:
        name = board.FindNet(order[0]).GetNetname()
        if near is not None:
            print(f"  rip-up around ({near[0]:.2f},{near[1]:.2f}): no order of {len(victims)} nets fits ({name} last to fail); undoing")
        for track in doomed:
            board.Add(track)
        return False
    # Reported only now, once nothing is going to be undone. It used to be
    # printed per net as each one routed, so a rip-up that was then rolled
    # back still logged "re-routed /ST_TMS from scratch" -- twice in one run,
    # for a net that ended the run unrouted.
    names = ", ".join(board.FindNet(code).GetNetname() for code in routed)
    where = f" around ({near[0]:.2f},{near[1]:.2f})" if near is not None else ""
    print(f"re-routed {names} from scratch{where}")
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
            added = path_to_tracks(board, grid, path, net)
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


def orphan_plane_pads(board: "pcbnew.BOARD") -> List[Tuple["pcbnew.NETINFO_ITEM", "pcbnew.PAD"]]:
    """Planed-net SMD pads that reach their net through nothing but a sliver.

    A pad counts as connected if a track or via of its net touches it, or if
    the piece of pour it sits in carries a via of its net. U4's pin 45 had
    neither: no fanout site, no track from the autorouter, and the F.Cu GND
    pour around it was a 1.8mm2 island with no via -- which DRC reports as
    two GND zones unconnected at the zone's corner, 20mm from the pad.
    """
    found = []
    for name in PLANE_NETS:
        net = board.FindNet(name)
        if net is None:
            continue
        code = net.GetNetCode()
        copper = [t for t in board.GetTracks() if t.GetNetCode() == code]
        vias = [t.GetPosition() for t in copper if isinstance(t, pcbnew.PCB_VIA)]
        fills = []
        for zone in board.Zones():
            if zone.GetIsRuleArea() or zone.GetNetCode() != code:
                continue
            for layer in LAYERS:
                if zone.IsOnLayer(layer):
                    fills.append((layer, zone.GetFilledPolysList(layer)))
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetNetCode() != code or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                    continue
                if any(pad.HitTest(t.GetStart()) or pad.HitTest(t.GetEnd()) for t in copper):
                    continue
                pos = pad.GetPosition()
                fed = False
                for layer, polys in fills:
                    if not pad.IsOnLayer(layer):
                        continue
                    for i in range(polys.OutlineCount()):
                        island = pcbnew.SHAPE_POLY_SET()
                        island.AddOutline(polys.Outline(i))
                        if island.Contains(pos) or island.Collide(pos, pcbnew.FromMM(0.2)):
                            if any(island.Contains(v) for v in vias):
                                fed = True
                            break
                if not fed:
                    found.append((net, pad))
    return found


def clear_island_and_stitch(board: "pcbnew.BOARD", grid: "Grid", net: "pcbnew.NETINFO_ITEM", pad: "pcbnew.PAD") -> bool:
    """via_in_island(), after lifting the few signal segments in the way.

    The island vouches only for its own layer; on the far side a signal can
    run straight under it -- /ST_CL on B.Cu under U4 pin 33's GND island --
    and leave no legal via site at all. So the site is chosen first, among
    the island's points, as the one that costs the fewest segments, and only
    the segments that actually come within clearance of it are lifted. Their
    cut ends are ordinary unconnected pairs for the next rounds. Lifting
    everything near the island instead took 48 segments of eight nets for one
    via.
    """
    code = net.GetNetCode()
    island = None
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetCode() != code:
            continue
        for layer in LAYERS:
            if not (zone.IsOnLayer(layer) and pad.IsOnLayer(layer)):
                continue
            polys = zone.GetFilledPolysList(layer)
            for i in range(polys.OutlineCount()):
                candidate = pcbnew.SHAPE_POLY_SET()
                candidate.AddOutline(polys.Outline(i))
                if candidate.Contains(pad.GetPosition()) or candidate.Collide(pad.GetPosition(), pcbnew.FromMM(0.2)):
                    island = candidate
    if island is None:
        return False

    liftable, fixed = [], []
    for item in board.GetTracks():
        if item.GetNetCode() in (0, code):
            continue
        if item.IsLocked() or item.GetNetname() in PLANE_NETS:
            fixed.append(item)
        else:
            liftable.append(item)
    pad_boxes = []
    for footprint in board.GetFootprints():
        for other in footprint.Pads():
            if other.GetNetCode() != code:
                box = other.GetBoundingBox()
                pad_boxes.append((box.GetLeft() / 1e6, box.GetTop() / 1e6, box.GetRight() / 1e6, box.GetBottom() / 1e6))

    def half(item) -> float:
        return (item.GetWidth(pcbnew.F_Cu) if isinstance(item, pcbnew.PCB_VIA) else item.GetWidth()) / 2e6

    def too_close(item, x: float, y: float) -> bool:
        clr = ESCAPE_CLEARANCE if grid.in_escape((x, y, x, y)) else CLEARANCE
        return segment_distance(item, (x, y)) < VIA_DIAMETER / 2 + clr + half(item)

    reach = VIA_DIAMETER / 2 + 0.02
    box = island.BBox()
    x0, y0 = pad.GetPosition().x / 1e6, pad.GetPosition().y / 1e6
    best = None
    gx = box.GetLeft() / 1e6
    while gx <= box.GetRight() / 1e6:
        gy = box.GetTop() / 1e6
        while gy <= box.GetBottom() / 1e6:
            probes = [(gx, gy)] + [(gx + reach * math.cos(math.radians(a)), gy + reach * math.sin(math.radians(a)))
                                   for a in range(0, 360, 30)]
            if all(island.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(px), pcbnew.FromMM(py))) for px, py in probes):
                clr = ESCAPE_CLEARANCE if grid.in_escape((gx, gy, gx, gy)) else CLEARANCE
                r = VIA_DIAMETER / 2 + clr
                pad_hit = any(l - r < gx < rr + r and t - r < gy < bb + r for l, t, rr, bb in pad_boxes)
                if not pad_hit and not any(too_close(item, gx, gy) for item in fixed):
                    blockers = [item for item in liftable if too_close(item, gx, gy)]
                    key = (len(blockers), math.hypot(gx - x0, gy - y0))
                    if blockers and (best is None or key < best[0]):
                        best = (key, gx, gy, blockers)
            gy += GRID
        gx += GRID
    if best is None:
        return False
    _key, _x, _y, lifted = best
    for item in lifted:
        board.Remove(item)
    if via_in_island(board, grid, net, pad):
        names = sorted({item.GetNetname() for item in lifted})
        print(f"  lifted {len(lifted)} segment(s) of {', '.join(names)} to make room; the cut ends follow as ordinary gaps")
        return True
    for item in lifted:
        board.Add(item)
    return False


def via_in_island(board: "pcbnew.BOARD", grid: "Grid", net: "pcbnew.NETINFO_ITEM", pad: "pcbnew.PAD") -> bool:
    """Stitch the pour island an orphan pad sits in, anywhere inside it.

    drop_via_to_plane() runs a track from the pad to a via site, which needs
    an escape lane. U4's pin 33 (GND) has none -- pin 34's +5V fanout stub
    runs 0.5mm away -- but it does not need one: it already sits in a 3.3mm2
    island of F.Cu GND pour, and a via anywhere in that island connects it.
    The pour keeps its own clearance from every other net, so a via whose
    whole annulus lies inside the island is clear of them by construction;
    what is left to check is the drill against other holes.
    """
    code = net.GetNetCode()
    pos = pad.GetPosition()
    island = None
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetCode() != code:
            continue
        for layer in LAYERS:
            if not (zone.IsOnLayer(layer) and pad.IsOnLayer(layer)):
                continue
            polys = zone.GetFilledPolysList(layer)
            for i in range(polys.OutlineCount()):
                candidate = pcbnew.SHAPE_POLY_SET()
                candidate.AddOutline(polys.Outline(i))
                if candidate.Contains(pos) or candidate.Collide(pos, pcbnew.FromMM(0.2)):
                    island = candidate
                    break
    if island is None:
        return False
    holes = [(v.GetPosition().x / 1e6, v.GetPosition().y / 1e6, v.GetDrillValue() / 1e6)
             for v in board.GetTracks() if isinstance(v, pcbnew.PCB_VIA)]
    for footprint in board.GetFootprints():
        for other in footprint.Pads():
            if other.GetDrillSizeX() > 0:
                holes.append((other.GetPosition().x / 1e6, other.GetPosition().y / 1e6,
                              other.GetDrillSizeX() / 1e6))
    hole_gap = 0.25  # STACKUP min_hole_to_hole_mm
    reach = VIA_DIAMETER / 2 + 0.02
    # The island only vouches for its own layer. The via goes through the
    # board, so on every other signal layer it is an ordinary via and has to
    # clear whatever is there -- the first one this placed landed on a
    # /ST_CL track on B.Cu, 0.035mm away.
    _blocked, via_blocked = grid.build(code)
    box = island.BBox()
    x0, y0 = pos.x / 1e6, pos.y / 1e6
    sites = []
    gx = box.GetLeft() / 1e6
    while gx <= box.GetRight() / 1e6:
        gy = box.GetTop() / 1e6
        while gy <= box.GetBottom() / 1e6:
            sites.append((math.hypot(gx - x0, gy - y0), gx, gy))
            gy += GRID
        gx += GRID
    for _d, x, y in sorted(sites):
        probes = [(x, y)] + [(x + reach * math.cos(math.radians(a)), y + reach * math.sin(math.radians(a)))
                             for a in range(0, 360, 30)]
        if not all(island.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(px), pcbnew.FromMM(py))) for px, py in probes):
            continue
        if any(math.hypot(x - hx, y - hy) < VIA_DRILL / 2 + hd / 2 + hole_gap for hx, hy, hd in holes):
            continue
        cx, cy = int(round(x / GRID)), int(round(y / GRID))
        if not (0 <= cx < grid.nx and 0 <= cy < grid.ny) or any(v[cx, cy] for v in via_blocked):
            continue
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        via.SetFrontWidth(pcbnew.FromMM(VIA_DIAMETER))
        via.SetDrill(pcbnew.FromMM(VIA_DRILL))
        via.SetNet(net)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)
        ref = pad.GetParentFootprint().GetReference()
        print(f"stitched {net.GetNetname()} island around {ref} pin {pad.GetNumber()} down at ({x:.2f},{y:.2f})")
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
        # Two zones, not a pad or a track: almost always a planed-net pad
        # that nothing reached, sitting on its own sliver of pour. KiCad
        # names the zones and puts both ends on the zone's corner, so the
        # pad has to be found rather than read off the report.
        for orphan_net, pad in orphan_plane_pads(board):
            layers = [i for i, layer in enumerate(LAYERS) if pad.IsOnLayer(layer)] or [0]
            origin = (pad.GetPosition().x / 1e6, pad.GetPosition().y / 1e6)
            if drop_via_to_plane(board, grid, orphan_net, origin, layers):
                return None
            if via_in_island(board, grid, orphan_net, pad):
                return None
            if clear_island_and_stitch(board, grid, orphan_net, pad):
                return None
        return f"({x1:.2f},{y1:.2f}) -> ({x2:.2f},{y2:.2f}): could not identify both ends"
    net_code, start_layers = start
    _target_net, target_layers = target
    net = board.FindNet(net_code)

    path = grid.route((x1, y1), start_layers, (x2, y2), target_layers, net_code)
    if path is not None:
        added = path_to_tracks(board, grid, path, net)
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
    #
    # The neighbourhood is searched around *each* end, pad first. It used to
    # be (x2, y2) only, and DRC does not promise which end of a pair is the
    # stranded one: every run of REV 0.6 ended with the stranded end first --
    # U4's pin 39 (/ST_BR1) and pin 41 (/PLC_LED), each walled in on the
    # QFN's right edge -- while the neighbourhood search looked at the other
    # end, up to 59mm away, and found nothing worth moving.
    if rip_up_and_reroute(board, grid, net):
        return None
    ends_by_pad = sorted([(x1, y1), (x2, y2)], key=lambda e: not is_pad(*e))
    for end in ends_by_pad:
        if rip_up_and_reroute(board, grid, net, near=end):
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


def strip_edge_violations(board: "pcbnew.BOARD") -> int:
    """Delete autorouter copper that breaks the board-edge clearance rule.

    Freerouting is not told about KiCad's 0.5mm copper-to-edge minimum and
    does not keep it: one run laid /ST_RESETN 0.26mm from the top edge, in
    three segments, and nothing noticed because no run before this had ever
    reached the final DRC. Deleting the offending segments turns them into
    ordinary unconnected pairs, which the loop below then routes with the
    margin applied.
    """
    left, top, right, bottom = board_outline(board)
    doomed = []
    for item in board.GetTracks():
        if item.IsLocked():
            continue  # placed on purpose by build_pcb.py, which checks its own geometry
        is_via = isinstance(item, pcbnew.PCB_VIA)
        half = (item.GetWidth(pcbnew.F_Cu) if is_via else item.GetWidth()) / 2e6
        for end in (item.GetStart(), item.GetEnd()):
            x, y = end.x / 1e6, end.y / 1e6
            if min(x - left, right - x, y - top, bottom - y) - half < BOARD_MARGIN - EPSILON:
                doomed.append(item)
                break
    for item in doomed:
        print(f"removed {item.GetNetname()} copper within {BOARD_MARGIN}mm of the board edge")
        # Delete, not Remove: Remove hands the item's ownership to Python,
        # which has no destructor for it -- see save_refilled().
        board.Delete(item)
    return len(doomed)


def run_step(*args: str) -> subprocess.CompletedProcess:
    """Run one board-changing step of this script in a fresh interpreter.

    Every step that takes copper off a board leaves KiCad 9's SWIG layer in
    a state where later boards in the same process come back as bare
    SwigPyObjects (see save_refilled()). So the loop below never edits a
    board itself: each step loads, changes, saves and exits, and this process
    only asks DRC what is left.
    """
    result = subprocess.run([sys.executable, __file__, *args], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if not line.startswith("ERROR "):  # reported by the caller as "set aside"
            print(line)
    return result


def step_strip() -> None:
    board = pcbnew.LoadBoard(BOARD_PATH)
    if strip_edge_violations(board):
        save_refilled(board, BOARD_PATH)


def step_repair(pair: Tuple[float, float, float, float]) -> None:
    board = pcbnew.LoadBoard(BOARD_PATH)
    error = repair_one(board, pair)
    if error:
        print("ERROR " + error)
        sys.exit(2)
    save_refilled(board, BOARD_PATH)


def main() -> None:
    if run_step("--strip").returncode != 0:
        sys.exit("edge-clearance strip failed")

    # One repair per round, re-checking with DRC in between. Repairs change
    # the board -- a rip-up can complete several connections at once, or move
    # where the remaining gap is -- so a list of pairs collected up front goes
    # stale after the first fix and produces phantom failures.
    #
    # A pair that cannot be repaired is set aside, not fatal. This loop used
    # to stop at the first one, which is why every REV 0.6 run was reported
    # as "one connection short": that was the first pair the loop could not
    # close, not the last pair on the board. The board behind one of those
    # reports still had nine. Closing the others first also changes what is
    # in the way of the hard one, so after any round that made progress the
    # set-aside pairs get another try. Only a full pass with no progress at
    # all is a failure, and then every remaining gap is listed.
    #
    # Capped, because a repair is allowed to open gaps as well as close them
    # -- cutting a planed neighbour's copper is a deliberate example -- and a
    # loop that only checks for progress could trade the same two gaps back
    # and forth forever.
    failed: Dict[Tuple[float, float, float, float], str] = {}
    best = len(drc_unconnected(BOARD_PATH))
    for _round in range(MAX_REPAIRS):
        pairs = drc_unconnected(BOARD_PATH)
        if not pairs:
            print("routing complete -- DRC reports no unconnected items")
            return
        pair = next((p for p in pairs if p not in failed), None)
        if pair is None:
            print(f"could not finish -- {len(pairs)} unconnected:")
            for p in pairs:
                print("  " + failed.get(p, f"{p}: not attempted"))
            sys.exit(1)

        result = run_step("--repair", *(repr(v) for v in pair))
        if result.returncode != 0:
            errors = [l[len("ERROR "):] for l in result.stdout.splitlines() if l.startswith("ERROR ")]
            error = errors[0] if errors else f"{pair}: repair step crashed\n{result.stderr[-2000:]}"
            print("set aside: " + error)
            failed[pair] = error
            continue
        # Progress is fewer gaps than ever before, not a repair that reported
        # success: those are not the same thing. One run "finished"
        # /ST_VDD_A's gap six times with copper that never closed it, and
        # each time cleared the set-aside list and re-ran every expensive
        # rip-up behind it. A gap a repair claims to have closed but that is
        # still there is set aside like any other.
        after = drc_unconnected(BOARD_PATH)
        if len(after) < best:
            best = len(after)
            failed.clear()  # whatever was set aside may have a way through now
        else:
            reverse = (pair[2], pair[3], pair[0], pair[1])
            if pair in after or reverse in after:
                note = f"{pair}: repaired, but DRC still reports it unconnected"
                print("set aside: " + note)
                failed[pair] = failed[reverse] = note
    print(f"could not finish -- gave up after {MAX_REPAIRS} repair rounds")
    sys.exit(1)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--strip"]:
        step_strip()
    elif sys.argv[1:2] == ["--repair"]:
        step_repair(tuple(float(v) for v in sys.argv[2:6]))
    else:
        main()
