"""Build hardware/pcb/plc-board/plc-board.kicad_pcb -- component PLACEMENT,
the isolation barrier, ground pour and design rules. No copper routing yet.

Structurally this is the Main Board's build_pcb.py with one thing added that
board never had to think about: **half of this board is at mains potential**.
Everything here follows from that.

  x = 0                     BARRIER_X = 36                       x = 100
  |<----- mains side ------>|<-- 7.96mm -->|<--- isolated side --->|
  | J1 mains in, TVS, MOV,  |   no copper  | ST7580 + coupling     |
  | X1 cap, series inductor |  either side | filter, ESP32, power  |
  |                         |              | tree, USB-C to the    |
  |         U1 (HLK-5M05) --+--------------+-- Terminal, LEDs      |
  |         T1 (coupling) --+--------------+                       |

Only two parts cross that band, and each one crosses it *inside its own
body*, where the manufacturer -- not this project -- is responsible for the
insulation: the HLK-5M05 (AC pins one end, DC pins 33.6mm away at the other)
and the coupling transformer (primary and secondary 10.16mm apart). The
barrier's width is not a number this project picked either; it is what T1's
own land pattern leaves between its primary and secondary pads once the
2.2mm pads are subtracted from the 10.16mm pitch. Wuerth chose it for
exactly this job.

check_isolation_barrier() enforces it on every pad of every net, and the
ground pour is clipped to the isolated side so a copper fill can never quietly
bridge what the placement carefully separated.

Reads the netlist exported from plc-board.kicad_sch (ref -> footprint, and
net -> [(ref, pin), ...]) and places each footprint's pads on the right net,
so the board opens in KiCad with a full ratsnest ready for routing.

Also writes ../plc-board.kicad_pro's net_settings section (NETCLASSES below
-- KiCad 7+ keeps netclasses in the project file, not the board file), so the
rules are in place before any copper is laid.

Regenerate the netlist this script reads with:
    kicad-cli sch export netlist ../plc-board.kicad_sch --format kicadsexpr -o /tmp/plc-board.net
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pcbnew

FOOTPRINT_DIR = "/usr/share/kicad/footprints"
# Project-local footprints not in KiCad's bundled libraries -- currently just
# the real ESP32-C3-MINI-1U, vendored from Espressif's official KiCad library
# (CC-BY-SA 4.0, same license terms as KiCad's own libraries -- see
# ../gridnet_footprints.pretty/README.md for provenance).
LOCAL_FOOTPRINT_LIBS = {"gridnet_footprints": "../gridnet_footprints.pretty"}
NETLIST_PATH = "/tmp/plc-board.net"
PROJECT_PATH = "../plc-board.kicad_pro"
BOARD_W = 100.0
BOARD_H = 80.0

# ---------------------------------------------------------------------- #
# The isolation barrier.
#
# BARRIER_X is where the board stops being a low-voltage board. It moved from
# 30 to 36 when routing proved the mains column too narrow: four mains nets
# (/AC_L, /AC_N, /PLC_LINE, /PLC_LINE_X1) at 1.0mm track and 2.5mm clearance
# need a 3.5mm pitch, so ~16.5mm of channel including margins, and the column
# had 9.7mm once the parts were in it. /AC_N failed to route twice with the
# repair router closing nothing at all -- deterministic, not unlucky. The
# isolated side gives up 6mm it was no longer short of. Nothing on
# the mains side may have copper right of MAINS_MAX, nothing on the isolated
# side may have copper left of SELV_MIN, and the band between them carries no
# copper on either layer.
#
# HALF_GAP is not a number chosen here. T1's land pattern puts its primary and
# secondary pads 10.16mm apart with 2.2mm pads, leaving 7.96mm of bare
# laminate between them; half of that is 3.98. Wuerth sized that gap for a
# transformer whose whole purpose is to sit across a mains barrier, so the
# board adopts it rather than inventing its own.
#
# For context on what the standards ask: reinforced insulation from 230V mains
# to a user-accessible SELV circuit is usually quoted around 5mm creepage and
# 3-4mm clearance (IEC 60950-1 / 62368-1, pollution degree 2, material group
# IIIa), with 8mm a widely used industry rule of thumb that includes margin.
# 7.96mm sits in that band. The exact requirement depends on pollution degree,
# material group and whether the insulation is basic or reinforced -- and this
# barrier is reinforced, because the user physically handles the USB-C cable
# on the isolated side while the adapter is in a wall socket. Confirming the
# number against the standard itself is listed in README.md as open.
#
# If a higher class is ever needed, the escalation is a routed slot down the
# middle of the band, which lengthens creepage without needing more board.
# ---------------------------------------------------------------------- #
# ---------------------------------------------------------------------- #
# Stackup.
#
# Four layers, and not for signal density: this board could very nearly be
# routed on two. It is four because of what has to be *planed*.
#
# The ST7580 puts nine +5V pads on three edges of a 48-pin 0.5mm-pitch
# package. Nothing passes between adjacent pads there -- a 0.2mm track with
# 0.2mm clearance needs 0.6mm and the gap is 0.25mm -- so every pin escapes
# radially and those nine have to find each other around the outside of the
# others. Four full two-layer routing runs failed on exactly that, never on
# the same pad twice: (52.05,6.70), (59.45,11.25), (59.45,8.25), and the
# pin 3 / pin 48 pair that wraps the top-left corner. A fifth run with a
# filled +5V island on F.Cu routed cleanly and was then broken by its own
# ground pour, which chopped the island from 413mm2 to 109mm2 and stranded
# eight connections. That net wants a plane, and on two layers both are spoken
# for by ground.
#
#   L1  F.Cu    signals, all components
#   L2  In1.Cu  GND plane
#   L3  In2.Cu  +5V plane
#   L4  B.Cu    signals
#
# The barrier goes through all four. An inner plane that crossed it would
# bridge mains to SELV inside the laminate, where no inspection would ever
# find it -- which is why add_keepout_zones() and the plane outlines below
# both take their limits from the same two constants everything else does.
COPPER_LAYERS = 4
SIGNAL_LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
PLANES = (("GND", pcbnew.In1_Cu), ("+5V", pcbnew.In2_Cu))

BARRIER_X = 36.0
HALF_GAP = 3.98
MAINS_MAX = BARRIER_X - HALF_GAP   # 26.02 -- mains copper must end here
SELV_MIN = BARRIER_X + HALF_GAP    # 33.98 -- isolated copper may start here

# Nets that are at mains potential. Everything not listed here is on the
# isolated secondary. /PLC_LINE and /PLC_LINE_X1 are the coupling path between
# T1's secondary and the live conductor -- they carry the PLC signal, but they
# are referenced to the mains, not to this board's ground.
MAINS_NETS = ("/AC_L", "/AC_N", "/PLC_LINE", "/PLC_LINE_X1")

# The two parts allowed to have pads on both sides, because each contains the
# insulation the barrier is made of: the AC-DC module and the transformer.
BARRIER_CROSSING = ("U1", "T1")

# ---------------------------------------------------------------------- #
# Trace widths and clearances.
#
# Sizing is IPC-2221's external-layer curve at 1oz copper and a 10 deg C rise:
# 0.2mm carries 0.74A, 0.4mm 1.23A, 0.8mm 2.03A, 1.0mm 2.4A.
#
# - Mains. The current here is trivial -- the HLK-5M05 draws about 30mA at
#   230V for its 5W output, which 0.2mm would carry ten times over. 1.0mm is
#   not about current at all: it is mechanical and thermal robustness on a
#   trace that can see a surge through the MOV and the TVS, and it is the
#   width every mains reference design uses for the same reason. The 2.5mm
#   clearance is the L-to-N spacing (basic insulation between two mains
#   conductors); the much larger mains-to-isolated distance is the barrier,
#   enforced geometrically rather than by a clearance rule.
# - +12V feeds the ST7580's PA. The transmit current limit is set to 500mA rms
#   by R14, and the datasheet's I(VCC) curve puts supply current near 500mA at
#   full output, so 0.4mm (1.23A) has ample margin.
# - +5V is the board's main rail: everything downstream of the ORing diodes,
#   including the boost's input and the supercapacitor's inrush through R11.
#
# GND deliberately has no class and stays at the default -- its current is
# carried by the pour, not by traces. The two 3V3 rails carry the ESP32's
# ~350mA transmit peak, inside 0.2mm's 0.74A.
# ---------------------------------------------------------------------- #
NETCLASSES: Dict[str, Tuple[float, float, List[str]]] = {
    "Mains": (1.0, 2.5, list(MAINS_NETS)),
    "Power_12V": (0.4, 0.2, ["/+12V", "/BOOST_SW"]),
    "Power_5V": (0.4, 0.2, ["+5V", "/PSU_5V", "/USB_5V"]),
}

# Reference-designator text nudges, in mm relative to where the footprint puts
# it by default. Only for the few that land on a neighbour's silkscreen or on
# exposed copper in this layout -- both are DRC warnings, and both mean the
# designator is unreadable on the finished board, which is the whole point of
# printing it. The power-tree column is tight enough that D1's and U1's
# default text positions overlap J1's and J2's outlines.
REFERENCE_OFFSETS: Dict[str, Tuple[float, float]] = {
    # U2 sits hard against the right edge so its antenna can, and its refdes
    # text lands off the board there. Pulled back inboard.
    "U2": (-5.5, 11.5),
}

# Ground pour / stitching geometry
ZONE_INSET = 0.5      # mm from the board outline
STITCH_PITCH = 5.0    # mm between stitching vias, across the whole board
VIA_DIAMETER = 0.6
VIA_DRILL = 0.3


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


@dataclass
class CompInfo:
    ref: str
    footprint: str
    value: str


def parse_netlist(path: str) -> Tuple[Dict[str, CompInfo], Dict[str, List[Tuple[str, str]]]]:
    text = open(path, encoding="utf-8").read()
    comps: Dict[str, CompInfo] = {}
    for ref, value, fp in re.findall(
        r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)', text
    ):
        comps[ref] = CompInfo(ref=ref, footprint=fp, value=value)

    nets: Dict[str, List[Tuple[str, str]]] = {}

    # Parse each (net (code..) (name..) (node..)* ) block via our own
    # balanced-paren scanner (sexp.py, already built for the schematic
    # generator) since node lists have nested parens regex can't cleanly
    # bound.
    import sexp

    idx = text.index("(nets")
    nets_block = sexp.extract_balanced(text, idx)
    pos = 0
    while True:
        net_idx = nets_block.find("(net ", pos)
        if net_idx == -1:
            break
        net_text = sexp.extract_balanced(nets_block, net_idx)
        pos = net_idx + len(net_text)
        name_m = re.search(r'\(name "([^"]+)"\)', net_text)
        if not name_m:
            continue
        name = name_m.group(1)
        nodes = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', net_text)
        nets.setdefault(name, []).extend(nodes)
    return comps, nets


def write_project_netclasses() -> None:
    """Write NETCLASSES into ../plc-board.kicad_pro.

    KiCad 7+ stores netclasses in the project file rather than the board, and
    the Specctra DSN exporter reads them from there -- so this has to run
    before the DSN is handed to Freerouting for the widths to mean anything.
    """
    with open(PROJECT_PATH, encoding="utf-8") as f:
        project = json.load(f)

    settings = project["net_settings"]
    default = next(c for c in settings["classes"] if c["name"] == "Default")
    classes = [default]
    patterns = []
    for name, (width, clearance, nets) in NETCLASSES.items():
        cls = dict(default)
        cls.update(name=name, track_width=width, clearance=clearance,
                   priority=len(classes))
        # Vias on a power net should not be a bottleneck narrower than the
        # trace feeding them; default 0.6/0.3 is fine up to ~1A, wider above.
        if width >= 0.6:
            cls.update(via_diameter=0.8, via_drill=0.4)
        classes.append(cls)
        patterns += [{"netclass": name, "pattern": net} for net in nets]

    settings["classes"] = classes
    settings["netclass_patterns"] = patterns
    with open(PROJECT_PATH, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)
    print(f"wrote {PROJECT_PATH} ({len(NETCLASSES)} netclasses, {len(patterns)} net assignments)")


def add_gnd_zones(board: "pcbnew.BOARD", gnd_net: "pcbnew.NETINFO_ITEM") -> None:
    """Fill both copper layers with a GND pour -- on the isolated side only.

    This is the one place the Main Board's version could not be reused as-is.
    There, the pour is the whole board inset from the outline. Here a pour that
    ran the full width would put GND copper straight through the isolation
    barrier and out into the mains side, which is the exact thing the placement
    exists to prevent -- and it would do it silently, since a zone is not a
    track and does not show up in a routing review.

    So the pour starts at SELV_MIN and runs to the right edge. The mains side
    gets no plane at all, which is also correct on its own terms: there is no
    mains-referenced ground net on this board (no PE conductor -- the Schuko
    plug's earth pin is not used), so there is nothing for a plane over there
    to be.
    """
    left = max(SELV_MIN, ZONE_INSET)
    right = BOARD_W - ZONE_INSET
    top, bottom = ZONE_INSET, BOARD_H - ZONE_INSET
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(gnd_net)
        zone.SetIsFilled(False)  # see pour_ground() -- the fill is a later step
        # Solid pad connections rather than thermal reliefs: this board is
        # reflow-assembled, and solid copper buys a lower-impedance return on
        # every ground pin. Same reasoning and same trade as the Main Board.
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetLocalClearance(mm(0.2))
        zone.SetMinThickness(mm(0.2))
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((left, top), (right, top), (right, bottom), (left, bottom)):
            outline.Append(mm(x), mm(y))
        board.Add(zone)


ALL_COPPER = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)


def add_plane_zones(board: "pcbnew.BOARD", nets: Dict[str, "pcbnew.NETINFO_ITEM"]) -> int:
    """Pour the two inner planes, isolated side only.

    These go in with the ground pour, AFTER routing -- which is a reversal of
    how they were first built, and the reversal is the point.

    Pouring them before the DSN export makes Freerouting treat GND and +5V as
    already connected wherever the plane reaches, so it lays no copper for
    them. That assumption is false: a pad on F.Cu is not connected to a plane
    on In2.Cu without a via, and nothing was placing those vias. Eight routing
    attempts ended one connection short, and the holdouts were not random --
    four of eight were U4's pin 3 / pin 48 pair, and the other four were its
    right-edge +5V pads. Freerouting thought it was done; DRC knew better.

    So the planes now arrive after the router has connected those nets the
    ordinary way, with four layers to do it on. The planes then reinforce what
    is already electrically correct rather than standing in for it.

    Both stop at SELV_MIN. There is no mains-referenced plane on this board
    and there is no plane crossing the barrier; the Schuko earth pin is unused,
    so the mains side has nothing a plane could be for.
    """
    left = max(SELV_MIN, ZONE_INSET)
    right = BOARD_W - ZONE_INSET
    top, bottom = ZONE_INSET, BOARD_H - ZONE_INSET
    for net_name, layer in PLANES:
        net = nets.get(net_name)
        if net is None:
            raise SystemExit(f"no {net_name} net -- cannot pour its plane")
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(net)
        zone.SetIsFilled(False)
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetLocalClearance(mm(0.2))
        zone.SetMinThickness(mm(0.2))
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        zone.SetZoneName(f"plane-{net_name}")
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((left, top), (right, top), (right, bottom), (left, bottom)):
            outline.Append(mm(x), mm(y))
        board.Add(zone)
    return len(PLANES)


def add_keepout_zones(board: "pcbnew.BOARD") -> int:
    """Rule areas the autorouter has to respect, added at PLACEMENT time.

    Placement keeps mains copper and isolated copper apart, but placement only
    controls pads. Once the board goes to Freerouting the barrier band is just
    empty board area, and empty board area on a dense two-layer design is
    exactly where a router looks for room. Nothing in the DSN would tell it
    otherwise: KiCad's Specctra exporter turns rule areas into `keepout`
    records, so a rule area here is the only thing that does.

    A smoke test bears out that the risk is real rather than theoretical only
    in one direction: a two-pass run without this zone happened not to cross
    the band, because no *net* has pads on both sides and so no connection
    needs to. But a longer run optimising net length has every reason to cut
    through it, and "it did not happen the first time" is not a design rule.

    Two areas:

    1. The isolation barrier, both copper layers, full board height.
    2. The strip between the ESP32's antenna keepout and the right board edge.
       Espressif's own rule area stops 0.7mm short of the edge, so the ground
       pour would otherwise fill a sliver of copper directly off the end of a
       PCB antenna. Outside the manufacturer's declared keepout and therefore
       legal, but copper at a radiating edge is not something to ship because
       a datasheet did not explicitly forbid it.
    """
    specs = [
        ("barrier", [(MAINS_MAX, 0.0), (SELV_MIN, 0.0), (SELV_MIN, BOARD_H), (MAINS_MAX, BOARD_H)]),
    ]
    esp = board.FindFootprintByReference("U2")
    if esp is None:
        raise SystemExit("U2 not placed -- cannot extend its antenna keepout to the edge")
    antenna = next((z for z in esp.Zones() if z.GetIsRuleArea()), None)
    if antenna is None:
        raise SystemExit("U2's footprint has no antenna rule area -- wrong footprint variant?")
    bb = antenna.Outline().BBox()
    right = bb.GetRight() / 1e6
    if right < BOARD_W:
        top, bottom = bb.GetTop() / 1e6, bb.GetBottom() / 1e6
        specs.append(("antenna-to-edge",
                      [(right, top), (BOARD_W, top), (BOARD_W, bottom), (right, bottom)]))

    for name, points in specs:
        zone = pcbnew.ZONE(board)
        zone.SetIsRuleArea(True)
        zone.SetDoNotAllowTracks(True)
        zone.SetDoNotAllowVias(True)
        zone.SetDoNotAllowPads(True)
        zone.SetDoNotAllowCopperPour(True)
        layers = pcbnew.LSET()
        for layer in ALL_COPPER:
            layers.AddLayer(layer)
        zone.SetLayerSet(layers)
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in points:
            outline.Append(mm(x), mm(y))
        zone.SetZoneName(name)
        board.Add(zone)
    return len(specs)


def make_via(board: "pcbnew.BOARD", net: "pcbnew.NETINFO_ITEM", x_nm: int, y_nm: int) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(x_nm, y_nm))
    # SetFrontWidth, not the layer-less SetWidth: KiCad 9's padstack model wants
    # a layer, and the one-argument overload trips an assertion per via.
    via.SetFrontWidth(mm(VIA_DIAMETER))
    via.SetDrill(mm(VIA_DRILL))
    via.SetNet(net)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(via)


# Parts whose footprint has an exposed/thermal pad that wants stitching down
# into the ground plane, and the pad number that carries it.
THERMAL_PADS = {
    "U2": "49",   # ESP32-C3-MINI-1's 3x3 thermal-pad array, per Espressif's
                  # hardware design guidelines.
    "U4": "49",   # ST7580's exposed pad. Its datasheet asks for it in as many
                  # words -- "recommended that the exposed pad be thermally
                  # connected to a copper ground plane for enhanced electrical
                  # and thermal performance" (Table 2) -- and its 50 degC/W
                  # thermal resistance is measured on a board that does it.
                  #
                  # U4 used the ..._ThermalVias footprint variant first, which
                  # carries its own 25-hole array. Two problems with it: the
                  # vias here then stacked on top of the footprint's, and the
                  # library's holes are 0.2mm, under the 0.3mm minimum in this
                  # project's board setup (and JLCPCB's standard process, which
                  # hardware/bom.md's PCB line assumes). DRC reported all 25 as
                  # drill_out_of_range. The plain footprint plus this table
                  # puts every via on the board through one function at one
                  # size.
}


# For a thermal pad that is a single exposed pad rather than an array of
# islands, how many vias to put across it. AN4068 measures the ST7580's
# 50 degC/W on "2-side PCB with thermal pad and 4x4 thermal via array", so that
# is the number, not a guess.
THERMAL_ARRAY = {"U4": 4}


def add_thermal_vias(board: "pcbnew.BOARD", gnd_net: "pcbnew.NETINFO_ITEM") -> int:
    """Stitch every exposed thermal pad down into the ground plane.

    Two shapes of thermal pad turn up on this board and they need different
    treatment:

    - The ESP32-C3-MINI-1's pad 49 is nine separate copper islands in the
      footprint, so one via per island lands in the right place by definition.
    - The ST7580's is one 5.1 x 5.1mm exposed pad. A single via at its centre
      would be a token gesture; AN4068 measures the part's thermal resistance
      with a 4x4 array, so THERMAL_ARRAY spreads that many across the pad,
      inset far enough that no via breaks the pad edge.

    These go in at PLACEMENT time, not with the rest of the stitching after
    routing, because the router has to know they are there: given the space an
    autorouter will run B.Cu traces straight under a module, and vias added
    afterwards land on top of them. Two nets got shorted that way on the Main
    Board before the ordering was fixed.
    """
    count = 0
    for ref, pad_number in THERMAL_PADS.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            raise SystemExit(f"{ref} not placed -- cannot add its thermal vias")
        pads = [p for p in fp.Pads() if p.GetNumber() == pad_number]
        if not pads:
            raise SystemExit(f"{ref} has no pad {pad_number} -- thermal pad missing from the footprint")
        if len(pads) > 1:
            for pad in pads:
                pos = pad.GetPosition()
                make_via(board, gnd_net, pos.x, pos.y)
                count += 1
            continue
        pad = pads[0]
        n = THERMAL_ARRAY.get(ref, 1)
        if n <= 1:
            pos = pad.GetPosition()
            make_via(board, gnd_net, pos.x, pos.y)
            count += 1
            continue
        centre = pad.GetPosition()
        # Keep the whole via annulus inside the pad, with the board's own
        # clearance to spare, then spread n of them evenly across what is left.
        inset = mm(VIA_DIAMETER / 2 + 0.2)
        span_x = pad.GetSizeX() - 2 * inset
        span_y = pad.GetSizeY() - 2 * inset
        if span_x <= 0 or span_y <= 0:
            raise SystemExit(f"{ref} pad {pad_number} is too small for a {n}x{n} via array")
        for i in range(n):
            for j in range(n):
                x = centre.x - span_x / 2 + span_x * i / (n - 1)
                y = centre.y - span_y / 2 + span_y * j / (n - 1)
                make_via(board, gnd_net, int(x), int(y))
                count += 1
    return count


# Fine-pitch parts whose power pins get a fanout stub and via at build time.
FANOUT_PARTS = ("U4",)


def add_power_fanout(board: "pcbnew.BOARD", nets: Dict[str, "pcbnew.NETINFO_ITEM"]) -> int:
    """Give every power pad on a fine-pitch part its own stub and via, outward.

    This is what a person does by hand on a 48-pin QFN and what no autorouter
    on this board would do for itself. The ST7580 has nine +5V pads spread over
    three edges; nothing passes between adjacent pads at 0.5mm pitch, so each
    one escapes radially, and the router then has to bring nine radial escapes
    back together around the outside of eleven others. Every routing run this
    project has made ended on that: with planes declared up front it was the
    top-left corner pair and the right edge, with planes deferred it was the
    right edge three times out of three, pins 28, 31 and 34 at x=59.45.

    A stub and a via turns each of those from "find your way to the other
    eight" into "go 1.6mm and drop to the plane". The vias are placed before
    the DSN export, so Freerouting sees them as copper already on the net and
    routes to whichever is convenient instead of chasing pads.
    """
    planed = {name for name, _layer in PLANES}
    clear = mm(VIA_DIAMETER / 2 + 0.25)
    obstacles = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            obstacles.append((pad.GetBoundingBox(), pad.GetNetname()))
    # Holes already on the board, so the fanout does not drill into its own
    # neighbours. U4's power pads sit on a 0.5mm pitch; sending each one the
    # same 1.6mm outward puts their vias on that same pitch, which with a
    # 0.3mm drill is 0.2mm hole-to-hole against a 0.25mm rule. Three pairs came
    # back from DRC exactly that way once the stackup made the rule real. The
    # distance sweep below now steps a crowded neighbour further out instead.
    holes = [(v.GetPosition().x, v.GetPosition().y, v.GetDrillValue())
             for v in board.GetTracks() if isinstance(v, pcbnew.PCB_VIA)]
    hole_gap = mm(STACKUP["min_hole_to_hole_mm"])

    def hole_clear(x: int, y: int) -> bool:
        need = mm(VIA_DRILL) / 2 + hole_gap
        return all((x - hx) ** 2 + (y - hy) ** 2 >= (need + hd / 2) ** 2
                   for hx, hy, hd in holes)

    placed = 0
    for ref in FANOUT_PARTS:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            raise SystemExit(f"{ref} not placed -- cannot fan out its power pins")
        centre = fp.GetPosition()
        for pad in fp.Pads():
            name = pad.GetNetname()
            if name not in planed or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            pos = pad.GetPosition()
            dx, dy = pos.x - centre.x, pos.y - centre.y
            # Straight out from the package, along whichever axis the pad's
            # own edge faces.
            if abs(dx) > abs(dy):
                step = (mm(1.0) if dx > 0 else mm(-1.0), 0)
            else:
                step = (0, mm(1.0) if dy > 0 else mm(-1.0))
            for distance in (1.6, 2.0, 2.4, 2.8):
                vx = pos.x + int(step[0] * distance)
                vy = pos.y + int(step[1] * distance)
                spot = pcbnew.BOX2I(pcbnew.VECTOR2I(vx - clear, vy - clear),
                                    pcbnew.VECTOR2I(2 * clear, 2 * clear))
                if any(box.Intersects(spot) and net != name for box, net in obstacles):
                    continue
                if not hole_clear(vx, vy):
                    continue
                make_via(board, nets[name], vx, vy)
                holes.append((vx, vy, mm(VIA_DRILL)))
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pos)
                track.SetEnd(pcbnew.VECTOR2I(vx, vy))
                track.SetWidth(mm(0.2))
                track.SetLayer(pcbnew.F_Cu)
                track.SetNet(nets[name])
                board.Add(track)
                obstacles.append((pcbnew.BOX2I(pcbnew.VECTOR2I(vx - clear, vy - clear),
                                               pcbnew.VECTOR2I(2 * clear, 2 * clear)), name))
                placed += 1
                break
    return placed


def add_stitching_vias(board: "pcbnew.BOARD", gnd_net: "pcbnew.NETINFO_ITEM") -> int:
    """Tie the two GND pours together with a grid of vias across the board.

    Keeps the pours at the same potential everywhere rather than only where a
    component happens to bridge them. Runs after routing, so candidates are
    rejected against any footprint's courtyard (a via under a part is a
    fabrication problem, not a DRC one, so nothing downstream would catch it),
    any pad, and any existing track or via.
    """
    # One box per footprint, not one per courtyard graphic: a courtyard drawn
    # as four separate line segments has four thin bounding boxes whose union
    # is the outline only, leaving the part's whole interior looking free.
    #
    # Inflated once, here, and never inside the candidate loop. BOX2I.Inflate()
    # grows the box in place and returns *itself*, so `bb.Inflate(clear)` in the
    # per-candidate test grew the same boxes again on every candidate that
    # reached them: the boxes ratcheted outwards until they covered the board
    # and every remaining site was rejected. See README.md's "The stitching
    # grid was one column of nine vias".
    clear = mm(VIA_DIAMETER / 2 + 0.3)
    keepouts = [box for _ref, box in courtyard_boxes(board)]
    keepouts += [pad.GetBoundingBox() for fp in board.GetFootprints() for pad in fp.Pads()]
    for box in keepouts:
        box.Inflate(clear)

    # Rule areas -- the isolation band and the antenna keepout -- forbid vias
    # outright. DRC reports a via inside one as items_not_allowed.
    rule_areas = [z for z in board.Zones() if z.GetIsRuleArea()]
    for fp in board.GetFootprints():
        rule_areas += [z for z in fp.Zones() if z.GetIsRuleArea()]

    # Copper obstacles are tested as (start, end, half-width) segments rather
    # than bounding boxes. A diagonal track's bounding box is a poor stand-in
    # for the track: it is far too big in the empty corners, so box-based
    # rejection throws away good via sites, and a via placed just off the
    # box's edge can still land on the copper. Six shorts got through that
    # way. Point-to-segment distance is exact and no harder.
    segments = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            pos = item.GetPosition()
            segments.append((pos, pos, item.GetWidth(pcbnew.F_Cu) / 2))
        else:
            segments.append((item.GetStart(), item.GetEnd(), item.GetWidth() / 2))

    def clear_of_copper(pt: "pcbnew.VECTOR2I", need: float) -> bool:
        for start, end, half_width in segments:
            dx, dy = end.x - start.x, end.y - start.y
            length_sq = dx * dx + dy * dy
            if length_sq == 0:
                t = 0.0
            else:
                t = ((pt.x - start.x) * dx + (pt.y - start.y) * dy) / length_sq
                t = max(0.0, min(1.0, t))
            near_x, near_y = start.x + t * dx, start.y + t * dy
            if (pt.x - near_x) ** 2 + (pt.y - near_y) ** 2 < (need + half_width) ** 2:
                return False
        return True

    count = 0
    margin = ZONE_INSET + VIA_DIAMETER
    # Left edge of the grid is SELV_MIN, not the board edge: the pour only
    # exists on the isolated side, so a stitching via anywhere left of the
    # barrier would be a GND via with no plane to tie together and copper
    # where the barrier says there is none.
    # SELV_MIN plus the via's own radius and clearance: the limit applies to
    # the copper edge, not the centre, and a via centred on the line hangs
    # 0.3mm into the band. check_isolation_barrier() caught exactly this.
    x_start = max(margin, SELV_MIN + VIA_DIAMETER / 2 + 0.2)
    span = BOARD_W - margin - x_start
    xs = [x_start + i * STITCH_PITCH for i in range(int(span // STITCH_PITCH) + 1)]
    ys = [margin + i * STITCH_PITCH for i in range(int((BOARD_H - 2 * margin) // STITCH_PITCH) + 1)]
    for x in xs + [BOARD_W - margin]:
        for y in ys + [BOARD_H - margin]:
            pt = pcbnew.VECTOR2I(mm(x), mm(y))
            if any(bb.Contains(pt) for bb in keepouts):
                continue
            if any(area.HitTestFilledArea(pcbnew.F_Cu, pt, 0) or area.Outline().Collide(pt, mm(VIA_DIAMETER / 2 + 0.2))
                   for area in rule_areas):
                continue
            if not clear_of_copper(pt, clear):
                continue
            make_via(board, gnd_net, pt.x, pt.y)
            count += 1
    return count


def courtyard_boxes(board: "pcbnew.BOARD") -> List[Tuple[str, "pcbnew.BOX2I"]]:
    """(ref, courtyard bounding box) for every footprint that has a courtyard."""
    boxes = []
    for fp in board.GetFootprints():
        parts = [
            item.GetBoundingBox()
            for item in fp.GraphicalItems()
            if item.GetLayerName() in ("F.Courtyard", "B.Courtyard")
        ]
        if not parts:
            continue
        box = parts[0]
        for bb in parts[1:]:
            box.Merge(bb)
        boxes.append((fp.GetReference(), box))
    return boxes


def pour_ground(board_path: str) -> None:
    """Add the GND pours, stitch them, and fill -- on an already-routed board.

    Deliberately a separate step run *after* Freerouting, not part of the
    placement pass. Zones present at DSN-export time become Specctra planes,
    and the router then treats GND as already-connected and lays no GND copper
    at all -- which leaves every ground connection depending on the pour
    reaching that exact pad. On a dense two-layer board it does not: routing
    chops the F.Cu pour into islands, and DRC found 16 GND fragments and pads
    stranded that way. Routing GND as ordinary traces first and pouring on top
    gives connectivity the router can guarantee, with the pour's lower
    impedance and thermal path on top of it rather than instead of it.

    Filling has to happen on a board loaded from disk: ZONE_FILLER segfaults
    on one built by CreateEmptyBoard, since it reaches for design settings
    that only exist once a board is loaded together with its .kicad_pro.
    `kicad-cli pcb drc` does not fill zones itself, so an unfilled board
    reports every GND pad as unconnected.
    """
    board = pcbnew.LoadBoard(board_path)
    gnd = board.FindNet("GND")
    if gnd is None:
        raise SystemExit("board has no GND net")
    # Rule areas are expected here -- build_pcb.py puts the isolation barrier
    # and the antenna keepout in at placement time, and they have to survive
    # into the routed board or the DSN loses them. It is a *filled* zone that
    # would mean this step had already run.
    already = [z for z in board.Zones()
               if not z.GetIsRuleArea() and not z.GetZoneName().startswith("plane-")]
    if already:
        raise SystemExit("board already has ground zones -- regenerate it with build_pcb.py first")

    add_gnd_zones(board, gnd)
    add_plane_zones(board, {n.GetNetname(): n for n in board.GetNetInfo().NetsByName().values()})
    stitches = add_stitching_vias(board, gnd)
    board.BuildConnectivity()
    copper_zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    if not pcbnew.ZONE_FILLER(board).Fill(copper_zones):
        raise SystemExit("zone fill failed")
    board.Save(board_path)
    areas = ", ".join(
        f"{board.GetLayerName(z.GetLayer())} {z.GetFilledArea() / 1e12:.0f}mm2" for z in copper_zones
    )
    print(f"poured GND: {areas}, {stitches} stitching vias")


def check_on_board(board: "pcbnew.BOARD") -> None:
    """Fail the build if any footprint's courtyard leaves the board outline.

    Added after moving the JTAG header to the top edge without checking its
    height: 13.79mm upright, centred at y=4.6, put a third of it past y=0. A
    whole routing run went by before anything noticed, and what noticed was
    the repair router reporting an unconnected item at y=-0.58. DRC does flag
    copper outside the outline -- but only after a full route, and this is one
    line of arithmetic at placement time.
    """
    off = []
    for fp in board.GetFootprints():
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if (bb.GetLeft() < 0 or bb.GetTop() < 0
                or bb.GetRight() > mm(BOARD_W) or bb.GetBottom() > mm(BOARD_H)):
            off.append(
                f"{fp.GetReference()}: x {bb.GetLeft()/1e6:.2f}..{bb.GetRight()/1e6:.2f}, "
                f"y {bb.GetTop()/1e6:.2f}..{bb.GetBottom()/1e6:.2f}"
            )
    if off:
        raise SystemExit(
            f"Footprints outside the {BOARD_W}x{BOARD_H}mm outline:\n  " + "\n  ".join(off)
        )


def check_isolation_barrier(board: "pcbnew.BOARD") -> None:
    """Fail the build if any pad lands in, or on the wrong side of, the barrier.

    Checked on pad bounding boxes rather than pad centres, because it is the
    copper edge that matters for creepage, and checked for every pad on the
    board rather than only the parts thought of as "mains" -- the point of a
    geometric check is that it does not depend on anyone having classified the
    part correctly.

    DRC will not do this. KiCad has no concept of a mains barrier: to it the
    band is empty board area, and copper placed in it is legal.
    """
    mains_nets = set(MAINS_NETS)
    problems = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net:
                continue
            bb = pad.GetBoundingBox()
            left, right = bb.GetLeft() / 1e6, bb.GetRight() / 1e6
            if net in mains_nets:
                if right > MAINS_MAX:
                    problems.append(
                        f"{ref} pad {pad.GetNumber()} ({net}) reaches x={right:.2f}, "
                        f"past the mains limit {MAINS_MAX:.2f}"
                    )
            elif left < SELV_MIN:
                problems.append(
                    f"{ref} pad {pad.GetNumber()} ({net}) starts at x={left:.2f}, "
                    f"left of the isolated limit {SELV_MIN:.2f}"
                )
    # Copper, not just pads. On the placed board there is none of it yet, but
    # this same function runs again after routing, where it is the only thing
    # standing between the design and a track that took a shortcut through the
    # band. A track is checked along its whole length, not at its endpoints: a
    # segment from one side of the board to the other has both ends legal.
    for item in board.GetTracks():
        net = item.GetNetname()
        if not net:
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            pos = item.GetPosition()
            half = item.GetWidth(pcbnew.F_Cu) / 2
            lo = hi = pos.x
        else:
            half = item.GetWidth() / 2
            lo = min(item.GetStart().x, item.GetEnd().x)
            hi = max(item.GetStart().x, item.GetEnd().x)
        lo = (lo - half) / 1e6
        hi = (hi + half) / 1e6
        what = "via" if isinstance(item, pcbnew.PCB_VIA) else "track"
        if net in mains_nets:
            if hi > MAINS_MAX:
                problems.append(f"{what} on {net} reaches x={hi:.2f}, past the mains limit {MAINS_MAX:.2f}")
        elif lo < SELV_MIN:
            problems.append(f"{what} on {net} reaches x={lo:.2f}, left of the isolated limit {SELV_MIN:.2f}")

    # Filled copper. This is the case the barrier is most exposed to, because
    # it is the one nobody looks at: a zone is not a track, so it appears in no
    # routing review and in no ratsnest. add_gnd_zones() clips the pour to the
    # isolated side by construction, and this is what proves it did.
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        net = zone.GetNetname()
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            # GetFilledPolysList throws on a layer the zone is not on, rather
            # than returning empty.
            if not zone.IsOnLayer(layer):
                continue
            poly = zone.GetFilledPolysList(layer)
            if poly.IsEmpty():
                continue
            bb = poly.BBox()
            lo, hi = bb.GetLeft() / 1e6, bb.GetRight() / 1e6
            if net in mains_nets:
                if hi > MAINS_MAX:
                    problems.append(f"filled zone on {net} reaches x={hi:.2f}, past the mains limit {MAINS_MAX:.2f}")
            elif lo < SELV_MIN:
                problems.append(f"filled zone on {net} reaches x={lo:.2f}, left of the isolated limit {SELV_MIN:.2f}")

    if problems:
        raise SystemExit(
            "Isolation barrier violated:\n  " + "\n  ".join(problems[:20])
            + (f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else "")
        )

    crossing = sorted(
        fp.GetReference() for fp in board.GetFootprints()
        if {p.GetNetname() for p in fp.Pads()} & mains_nets
        and {p.GetNetname() for p in fp.Pads()} - mains_nets - {""}
    )
    if crossing != sorted(BARRIER_CROSSING):
        raise SystemExit(
            f"Parts with pads on both sides of the barrier: {crossing}, "
            f"expected exactly {sorted(BARRIER_CROSSING)}"
        )


def check_courtyard_overlaps(board: "pcbnew.BOARD") -> None:
    """Fail the build if any two footprints' courtyards overlap.

    DRC catches this too, but only once someone runs it; placement is
    generated, so it is cheaper to refuse to write a colliding board at all.
    """
    boxes = courtyard_boxes(board)
    clashes = []
    for i, (ref_a, box_a) in enumerate(boxes):
        for ref_b, box_b in boxes[i + 1:]:
            if box_a.Intersects(box_b):
                clashes.append(f"{ref_a} <-> {ref_b}")
    if clashes:
        raise SystemExit("Courtyard overlaps in PLACEMENT:\n  " + "\n  ".join(clashes))


# Manufacturing constraints, written into the board's design rules so DRC
# enforces them. KiCad's minimums default to zero -- the Main Board carried
# m_TrackMinWidth = 0.0 and m_MinClearance = 0.0 all the way through routing,
# so a 0.05mm trace would have passed every check this project runs.
#
# Four layers on the same 1.6mm FR-4 as Board 2. Inner copper on a standard
# 4-layer stack is lighter than outer, which does not affect this board: the
# inner layers carry only planes, and every current-carrying trace -- the
# 1.0mm mains nets included -- is on an outer layer at 1oz, which is what the
# IPC-2221 widths in NETCLASSES assume.
#
# The minimums are what the board already uses, promoted from convention to
# rule. Not a claim about any fab's capability; confirming them against the
# chosen manufacturer is a separate step, listed in the README.
STACKUP = {
    "thickness_mm": 1.6,
    "copper_weight_outer_oz": 1,
    "copper_weight_inner_oz": 0.5,
    "min_track_mm": 0.2,
    "min_clearance_mm": 0.2,
    "min_via_diameter_mm": 0.6,
    "min_via_drill_mm": 0.3,
    "min_hole_to_hole_mm": 0.25,
    "min_annular_ring_mm": 0.15,
}


def apply_stackup(board: "pcbnew.BOARD") -> None:
    """Write STACKUP into the board's design rules so DRC enforces it."""
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(STACKUP["thickness_mm"]))
    ds.m_TrackMinWidth = mm(STACKUP["min_track_mm"])
    ds.m_MinClearance = mm(STACKUP["min_clearance_mm"])
    ds.m_ViasMinSize = mm(STACKUP["min_via_diameter_mm"])
    ds.m_MinThroughDrill = mm(STACKUP["min_via_drill_mm"])
    ds.m_HoleToHoleMin = mm(STACKUP["min_hole_to_hole_mm"])
    ds.m_ViasMinAnnularWidth = mm(STACKUP["min_annular_ring_mm"])


def add_board_outline(board: "pcbnew.BOARD") -> None:
    pts = [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        seg.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.15))
        board.Add(seg)


# ---------------------------------------------------------------------- #
# Placement plan: ref -> (x_mm, y_mm, rotation_degrees, expected_value)
#
# `expected_value` is checked against the netlist's own value field for that
# refdes before anything is placed. This dict is keyed by reference
# designator, so it is only correct as long as build_schematic.py assigns
# the same refdes to the same part -- which it did NOT for one revision:
# refdes used to be auto-numbered by call order, so inserting the IP5306's
# inductor and snubber mid-file renumbered every later R and C by +1 and
# silently swapped their board positions (README.md, "Reference-designator
# drift"). build_schematic.py now declares every refdes explicitly, and this
# check is the second lock on the same door: if the two files ever disagree
# again, placement fails loudly instead of quietly building a wrong board.
#
# Board is 100x80mm (hardware/bom.md, Board 2 -- Main Board). Layout groups
# by subsystem, edge connectors facing outward for case cutouts:
#   - left edge: USB-C power in, battery connector
#   - top edge: display / keyboard-controller / keyboard-backlight headers
#     (these route up into the clamshell's lid/base)
#   - right edge: microSD card slot
#   - bottom edge: speaker header
#   - center: MCU with crystal/reset/boot/SWD around it
#   - center-right: SPI flash/SRAM + RTC (near the MCU's SPI1/I2C1 pins)
#   - lower-right: ESP32-C3 module (its antenna leaves on a cable from the
#     module's own jack, so no antenna connector is placed on the board)
#   - lower-center: audio amp + keyboard-backlight FET, near the speaker
#     and keyboard-backlight headers they feed
# ---------------------------------------------------------------------- #

#
# Coordinates below were derived programmatically (a small shelf-packing
# script, not hand-guessed) from each footprint's REAL courtyard size, to
# guarantee zero courtyard overlaps before ever loading pcbnew -- a first
# hand-placed attempt at these positions produced 7 courtyard overlaps and
# several net-shorting clearance violations once real footprint sizes
# (e.g. the CR2032 holder's actual 27x24mm body, far bigger than its
# schematic symbol suggests) were taken into account.
PLACEMENT: Dict[str, Tuple[float, float, float, str]] = {
    # (courtyard-centre x, courtyard-centre y, rotation, expected schematic value)
    #
    # The fourth field is not documentation. build_pcb.py refuses to write a
    # board when it disagrees with the netlist, because the Main Board silently
    # placed a dozen parts in each other's positions when this dict drifted out
    # of step with the schematic's refdes assignment -- crystal load caps 51mm
    # from their crystal, and nothing caught it until a design-review pass.
    #
    # Coordinates started from a two-region packer (mains left of the barrier,
    # isolated right of it) that scored each candidate slot by distance to the
    # centroid of the parts it is actually connected to, then were grouped by
    # hand. Sizes come from each footprint's real courtyard, measured through
    # pcbnew -- not guessed.

    # --- Mains side: everything here is at line potential ---------------- #
    # Laid out to leave a clear 9.7mm channel at x 16.3..26.02, running the
    # full height of the board, for /AC_L and /AC_N. The Mains netclass is
    # 1.0mm track at 2.5mm clearance -- 6mm of channel per trace -- and RV1
    # lying flat is 22mm wide, which blocked the column outright: routing
    # failed on /AC_N with 2mm of space beside it. The varistor and the X1
    # capacitor now stand on end.
    # Order down the left edge follows the signal: the coupling path to the
    # line at the top, mains entry and its protection below it, and the AC-DC
    # module at the bottom.
    "C17": (6.0, 12.0, 90, "150nF X1"),      # X1 safety cap into AC_L
    "L3": (7.0, 30.0, 0, "12uH"),          # coupling series inductor
    "J1": (12.0, 40.0, 0, "MAINS_L_N"),     # mains entry, left edge. Moved in from
                                            # x=8 -- the Wuerth block's silkscreen
                                            # outline runs wider than its courtyard
                                            # and was clipped by Edge.Cuts there.
    "RV1": (14.0, 14.0, 90, "S20K275"),      # MOV across L/N (Layer 2)
    "D1": (10.0, 48.0, 0, "P6KE250CA"),     # TVS across L/N (Layer 1)

    # --- The barrier itself ---------------------------------------------- #
    # Both of these have pads on both sides and are the only parts allowed to.
    # T1 sets HALF_GAP: its 10.16mm pad pitch less two 1.1mm pad radii.
    # U1's AC and DC pins are 33.6mm apart, far more than the barrier needs,
    # so it is placed to put its AC pads at x=12 and its DC pads at x=45.6.
    "T1": (36.0, 12.0, 180, "750510231"),   # rotated: secondary (10/7) faces the mains side
    "U1": (34.8, 64.0, 0, "HLK-5M05"),

    # --- Isolated side: coupling filter into the ST7580 ------------------- #
    # Kept tight against T1's primary pads at x=35.08. This chain is the whole
    # transmit and receive path and its loop areas are what a redesign would
    # regret first.
    "C16": (47.0, 6.0, 0, "10uF/50V X5R"),  # DC block into T1's primary
    "R20": (49.0, 10.28, 0, "150R"),        # Rx series resistor
    "L2": (47.0, 14.0, 0, "150uH"),         # Rx resonant inductor
    "C15": (52.5, 3.77, 0, "12nF"),        # Rx resonant capacitor
    "C13": (57.0, 16.27, 0, "68pF C0G"),     # Sallen-Key feedback cap
    "C14": (49.0, 20.77, 0, "68pF C0G"),    # Sallen-Key shunt cap
    "R18": (58.0, 19.27, 0, "33k"),          # PA gain, feedback leg
    "R19": (65.0, 22.27, 0, "10k"),         # PA gain, ground leg
    "R17": (45.0, 24.77, 0, "22k"),         # Sallen-Key second series R
    "R16": (43.5, 30.77, 0, "5.1k"),        # Sallen-Key first series R
    "R15": (44.5, 21.77, 0, "1k"),           # Tx pre-filter series R
    "C12": (45.0, 27.77, 0, "1nF C0G"),      # Tx pre-filter shunt C
    "R14": (62.5, 19.27, 0, "270R"),         # PA current-limit resistor on CL

    # --- ST7580 and its support ------------------------------------------ #
    "U4": (56.0, 10.0, 270, "ST7580"),
    "Y1": (55.0, 26.5, 0, "8MHz"),
    "C2": (68.0, 8.78, 0, "100nF"),        # VDD_A
    "C3": (63.0, 12.28, 0, "100nF"),         # VDD_B
    "C4": (53.5, 20.77, 0, "100nF"),         # VDD_REG_1V8
    "C5": (68.0, 11.78, 0, "100nF"),        # VDD_PLL
    "C6": (63.22, 9.03, 0, "1uF"),          # VCCA
    "C11": (52.5, 17.6, 0, "100nF"),       # VCC (12V) local decoupling
    "FB1": (48.3, 17.6, 0, "FB"),          # VSSA-to-GND bridge
    "FB2": (61.77, 3.4, 0, "FB"),          # VDD_A to VDD_PLL
    "R6": (57.0, 3.77, 0, "10k"),          # RESETN pull-up
    # BR0 and BR1 are adjacent pads on the QFN's top edge (40 and 39, at
    # x=57.25 and 57.75, y=6.55), so both escape upwards. R8 used to sit at
    # (66, 15.78), below and right of the chip, which asked /ST_BR0 to travel
    # around the whole east face of a 48-pin 0.5mm-pitch package. Freerouting
    # could not place it and neither could the repair router. Its pull-up now
    # sits beside BR1's, on the side the pin actually leaves from.
    "R7": (61.5, 16.27, 0, "10k"),           # BR1
    "R8": (66.0, 15.28, 0, "10k"),           # BR0
    "J3": (72.0, 4.6, 90, "ST7580_JTAG_DEBUG"),   # right edge

    # --- ESP32-C3 --------------------------------------------------------- #
    "U2": (90.5, 28.0, 270, "ESP32-C3-MINI-1"),
    "J2": (78.0, 28.0, 0, "ESP32_UART0_PROGRAMMING"),
    "R4": (86.0, 18.77, 0, "10k"),          # EN pull-up
    "R5": (73.0, 31.77, 0, "10k"),          # IO9/BOOT pull-up
    "R9": (90.5, 64.78, 0, "5.1k"),         # USB-C CC1 pull-down
    "R10": (95.0, 64.78, 0, "5.1k"),        # USB-C CC2 pull-down

    # --- Power tree, fed from U1's DC pads at x=45.6 ---------------------- #
    "D5": (58.52, 33.3, 0, "SS34"),         # ORing, mains supply
    "D6": (58.52, 46.8, 0, "SS34"),         # ORing, Terminal supply
    "D7": (50.02, 33.3, 0, "SS34"),         # supercapacitor discharge
    "D8": (79.02, 42.8, 0, "SS34"),         # boost rectifier
    "C1": (68.78, 50.8, 0, "220uF"),         # HLK output bulk
    "C7": (68.77, 39.79, 0, "1F 5.5V"),       # supercapacitor hold-up
    "C10": (71.42, 25.95, 0, "100uF"),        # +5V bulk
    "R11": (47.8, 37.67, 0, "10R"),         # supercapacitor inrush limit
    "C8": (60.82, 51.2, 0, "22uF"),         # boost input
    "C9": (60.82, 55.2, 0, "22uF"),         # boost output
    "L1": (88.0, 48.0, 0, "22uH"),          # boost inductor
    "U5": (80.0, 48.0, 0, "MT3608"),        # 5V -> 12V boost
    "R12": (79.0, 51.77, 0, "19.1k"),       # boost feedback, top
    "R13": (80.0, 54.77, 0, "1k"),          # boost feedback, bottom
    "U3": (57.42, 40.15, 0, "AMS1117-3.3"),   # 3V3 for the ESP32

    # --- User-facing, at the board edges ---------------------------------- #
    "J4": (92.0, 72.0, 0, "TERMINAL_5V_IN"),   # USB-C from the Terminal
    "D2": (60.0, 76.0, 0, "LED (green)"),      # power
    "D3": (70.0, 76.0, 0, "LED (amber)"),      # PLC activity
    "D4": (80.0, 76.0, 0, "LED (blue)"),       # Wi-Fi
    "R1": (63.15, 65.05, 0, "1k"),
    "R2": (71.15, 69.55, 0, "1k"),
    "R3": (82.65, 38.05, 0, "330R"),
}


def main() -> None:
    comps, nets = parse_netlist(NETLIST_PATH)

    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(COPPER_LAYERS)
    apply_stackup(board)
    add_board_outline(board)

    net_objs: Dict[str, "pcbnew.NETINFO_ITEM"] = {}
    for name in nets:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        net_objs[name] = n

    missing_placement = [r for r in comps if r not in PLACEMENT]
    if missing_placement:
        raise SystemExit(f"No placement coordinates for: {missing_placement}")
    stale_placement = [r for r in PLACEMENT if r not in comps]
    if stale_placement:
        raise SystemExit(f"PLACEMENT has coordinates for parts not in the netlist: {stale_placement}")

    # Guard against this dict drifting out of sync with the schematic's
    # refdes assignment -- see the comment above PLACEMENT for the bug this
    # exists to catch.
    mismatched = [
        f"{ref}: PLACEMENT expects {PLACEMENT[ref][3]!r}, netlist has {info.value!r}"
        for ref, info in sorted(comps.items())
        if PLACEMENT[ref][3] != info.value
    ]
    if mismatched:
        raise SystemExit("PLACEMENT/schematic refdes mismatch:\n  " + "\n  ".join(mismatched))

    # ref+pin -> net name, built from the parsed netlist for pad assignment
    pin_net: Dict[Tuple[str, str], str] = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pin_net[(ref, pin)] = name

    def courtyard_center_mm(fp: "pcbnew.FOOTPRINT") -> Tuple[float, float]:
        xs, ys = [], []
        for item in fp.GraphicalItems():
            if item.GetLayerName() in ("F.Courtyard", "B.Courtyard"):
                bb = item.GetBoundingBox()
                xs += [bb.GetLeft(), bb.GetRight()]
                ys += [bb.GetTop(), bb.GetBottom()]
        if not xs:
            pos = fp.GetPosition()
            return pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
        return pcbnew.ToMM((min(xs) + max(xs)) / 2), pcbnew.ToMM((min(ys) + max(ys)) / 2)

    unmatched_pads = []
    for ref, info in sorted(comps.items()):
        lib_name, fp_name = info.footprint.split(":", 1)
        if lib_name in LOCAL_FOOTPRINT_LIBS:
            lib_path = LOCAL_FOOTPRINT_LIBS[lib_name]
        else:
            lib_path = f"{FOOTPRINT_DIR}/{lib_name}.pretty"
        fp = pcbnew.FootprintLoad(lib_path, fp_name)
        if fp is None:
            raise SystemExit(f"Footprint not found: {info.footprint} (ref {ref})")
        x, y, rot, _expected_value = PLACEMENT[ref]
        fp.SetReference(ref)
        fp.SetValue(info.value)
        # PLACEMENT coordinates mean "courtyard center" -- but a footprint's
        # anchor (what SetPosition moves) is often NOT its courtyard center
        # (e.g. pin headers are anchored at pin 1, not the row's midpoint;
        # the SMA edge-mount connector's body is anchored off to one side).
        # Place naively first, measure the real courtyard center that
        # results, then correct the anchor by the difference -- exact
        # regardless of footprint asymmetry or rotation, and avoids having
        # to hand-derive each footprint's per-rotation offset.
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(rot)
        cx, cy = courtyard_center_mm(fp)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x + (x - cx)), mm(y + (y - cy))))
        if ref in REFERENCE_OFFSETS:
            dx, dy = REFERENCE_OFFSETS[ref]
            text = fp.Reference()
            pos = text.GetPosition()
            text.SetPosition(pcbnew.VECTOR2I(pos.x + mm(dx), pos.y + mm(dy)))
        board.Add(fp)
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            net_name = pin_net.get(key)
            if net_name is None:
                unmatched_pads.append(key)
                continue
            pad.SetNet(net_objs[net_name])

    if unmatched_pads:
        # Expected for J1 and J5, whose real footprints carry shield tabs and
        # mechanical/detect pads with no counterpart in the schematic symbol,
        # and for U9's 14 genuinely NC pads. Print rather than fail so the
        # rest of the board still gets a full ratsnest.
        print(f"Note: {len(unmatched_pads)} pads had no matching net (see comment above): {unmatched_pads}")

    check_courtyard_overlaps(board)
    check_on_board(board)
    check_isolation_barrier(board)
    thermal = add_thermal_vias(board, net_objs["GND"])
    # After placement, because the antenna keepout's geometry comes from U2.
    keepouts = add_keepout_zones(board)
    fanout = add_power_fanout(board, net_objs)


    out_path = "../plc-board.kicad_pcb"
    board.Save(out_path)
    print(f"wrote {out_path} ({len(comps)} components, {len(nets)} nets, {thermal} thermal vias, {keepouts} keepout zones, {fanout} power fanouts)")

    write_project_netclasses()


if __name__ == "__main__":
    import sys

    # Two-stage by design: `build_pcb.py` places parts and writes the
    # netclasses, then the board goes out to Freerouting, then `--pour` adds
    # the ground plane on top of the finished copper. See pour_ground() for
    # why the pour cannot come first, and README.md for the full command
    # sequence.
    if "--pour" in sys.argv:
        pour_ground("../plc-board.kicad_pcb")
    else:
        main()
