"""Build hardware/pcb/main-board/main-board.kicad_pcb -- component
PLACEMENT, ground pours and design rules (no copper routing; that is
Freerouting's job, see this directory's README.md).

Reads the netlist exported from main-board.kicad_sch (ref -> footprint,
and net -> [(ref, pin), ...]) and uses it to place each footprint's pads on
the right net, so the board opens in KiCad with a full ratsnest ready for
routing. Placement coordinates are hand-picked below, grouped by
subsystem (power tree, MCU, memory, wireless, audio/keyboard, edge
connectors), within the 100x80mm outline from hardware/bom.md's Board 2
line.

This script also writes ../main-board.kicad_pro's net_settings section
(NETCLASSES below -- KiCad 7+ keeps netclasses in the project file, not the
board file), so the widths are in place *before* the board is handed to the
autorouter rather than being retrofitted onto finished copper.

Regenerate the netlist this script reads with:
    kicad-cli sch export netlist ../main-board.kicad_sch --format kicadsexpr -o /tmp/main-board.net
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
NETLIST_PATH = "/tmp/main-board.net"
PROJECT_PATH = "../main-board.kicad_pro"
BOARD_W = 100.0
BOARD_H = 80.0

# ---------------------------------------------------------------------- #
# Trace widths.
#
# Everything on this board used to route at the 0.2mm default, including the
# IP5306's boost path -- flagged for a design-review pass when the inductor
# was added, and fixed here.
#
# Sizing is IPC-2221's external-layer curve at 1oz (35um) copper and a 10 deg C
# rise, which for these widths gives roughly:
#     0.2mm -> 0.74A     0.4mm -> 1.23A
#     0.5mm -> 1.45A     0.8mm -> 2.03A
#
# Design currents come from docs/firmware-arch.md's REV 0.6 power budget
# (355mA at +5V in active use, 14mA standby) and the parts' own datasheets:
#
# - Battery/boost path (/VBATT, /IP5306_SW). The board's own draw is 355mA at
#   5V, i.e. ~545mA on the battery side at 3.7V/88%, ~0.7A peak once boost
#   ripple is counted, plus the MCP73831's ~450mA charge current on the same
#   net. The IP5306 itself is rated to 2.4A, so the trace is sized towards the
#   IC's capability rather than today's load: 0.8mm carries 2.03A at a 10 deg C
#   rise and the full 2.4A at roughly 15 deg C, which is the honest way to state
#   it. It is not 1.0mm (the exact 2.4A/10 deg C width) because U2 is an SOP-8
#   whose pads are only 0.6mm across the trace direction -- a 1.0mm trace would
#   have to neck down at both ends of the shortest, most critical segment.
# - +5V rail and VBUS. The 355mA system budget plus the PAM8403's ~500mA peak
#   into 1W/8ohm, so ~0.9A design maximum; 0.4mm carries 1.23A. VBUS sees only
#   the MCP73831's 450mA charge current and is in the same class for
#   simplicity.
#
# GND and the two 3V3 rails deliberately have NO class of their own and stay
# at the 0.2mm default:
#
# - GND's current is carried by the copper pours (see pour_ground), not by the
#   traces; widening the traces would buy nothing the plane does not already
#   provide.
# - +3V3_MCU carries ~150mA (MCU, flash, SRAM, RTC, microSD and the two
#   logic-level headers) and +3V3_RF peaks near 350mA on ESP32-C3 transmit,
#   both comfortably inside 0.2mm's 0.74A.
#
# A first cut of this table gave all three 0.4mm anyway "for margin", and
# Freerouting could not route any of them: U5 is an LQFP-48 on a 0.5mm pitch,
# and a 0.4mm trace leaving a 0.3mm pad there comes within 0.15mm of the
# neighbouring pad, under the 0.2mm clearance rule. The MCU's own GND and
# 3V3 pins were the failures both times. Wider is not automatically safer --
# it has to fit the escape geometry at both ends.
# ---------------------------------------------------------------------- #
NETCLASSES: Dict[str, Tuple[float, List[str]]] = {
    "Power_Batt": (0.8, ["/VBATT", "/IP5306_SW"]),
    "Power_5V": (0.4, ["+5V", "VBUS"]),
}

# Reference-designator text nudges, in mm relative to where the footprint puts
# it by default. Only for the few that land on a neighbour's silkscreen or on
# exposed copper in this layout -- both are DRC warnings, and both mean the
# designator is unreadable on the finished board, which is the whole point of
# printing it. The power-tree column is tight enough that D1's and U1's
# default text positions overlap J1's and J2's outlines.
REFERENCE_OFFSETS: Dict[str, Tuple[float, float]] = {
    "D1": (0.0, 3.3),    # below the LED, clear of both J1's outline and its own
    "U1": (-5.5, 0.6),   # out to the left, clear of J2's outline
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
    """Write NETCLASSES into ../main-board.kicad_pro.

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
    for name, (width, nets) in NETCLASSES.items():
        cls = dict(default)
        cls.update(name=name, track_width=width, priority=len(classes))
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
    """Fill both copper layers with a GND pour, inset from the board edge.

    Two things this buys beyond tidiness: a low-impedance return path under
    the SPI/I2C buses and the RF module (the board previously had none -- every
    ground connection was an ordinary routed trace), and the copper the
    ESP32-C3-MINI-1U's thermal pad is supposed to dump heat into, per
    Espressif's hardware design guidelines.
    """
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(gnd_net)
        zone.SetIsFilled(False)  # see fill_zones() -- the fill is a later step
        # Solid pad connections rather than thermal reliefs. Thermal spokes
        # were tried first and left 11 pads "starved" (fewer than the two
        # spokes KiCad requires): on 0603 pads with a trace already attached
        # there is not enough pad perimeter left for a second spoke. Solid
        # copper costs some hand-soldering convenience on the ground pins and
        # buys a lower-impedance return everywhere, which is the point of the
        # pour -- this board is reflow-assembled, so that is the right trade.
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        # Drop copper islands that end up connected to nothing, rather than
        # leaving them floating for DRC to report as unconnected GND.
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        # Clearance matches the board rule rather than exceeding it, so the
        # pour can reach between fine-pitch escape traces instead of stopping
        # short of them and stranding copper.
        zone.SetLocalClearance(mm(0.2))
        zone.SetMinThickness(mm(0.2))
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in (
            (ZONE_INSET, ZONE_INSET),
            (BOARD_W - ZONE_INSET, ZONE_INSET),
            (BOARD_W - ZONE_INSET, BOARD_H - ZONE_INSET),
            (ZONE_INSET, BOARD_H - ZONE_INSET),
        ):
            outline.Append(mm(x), mm(y))
        board.Add(zone)


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


def add_thermal_vias(board: "pcbnew.BOARD", gnd_net: "pcbnew.NETINFO_ITEM") -> int:
    """Drop a via through each copper island of U9's thermal pad.

    Espressif's hardware design guidelines want the ESP32-C3-MINI-1U's thermal
    pad tied down into the ground plane; pin 49 is the 3x3 array of pads that
    do it. These go in at PLACEMENT time, not with the rest of the stitching
    after routing, because the router has to know they are there: given the
    space, Freerouting will happily run B.Cu traces straight under the module,
    and vias added afterwards land on top of them (/AUDIO_SHDN and /KBL_DRAIN
    both got shorted this way before the ordering was fixed).
    """
    esp = board.FindFootprintByReference("U9")
    if esp is None:
        raise SystemExit("U9 (ESP32-C3-MINI-1U) not placed -- cannot add thermal vias")
    count = 0
    for pad in esp.Pads():
        if pad.GetNumber() == "49":
            pos = pad.GetPosition()
            make_via(board, gnd_net, pos.x, pos.y)
            count += 1
    if count == 0:
        raise SystemExit("U9 has no pad 49 -- thermal-pad array missing from the footprint")
    return count


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
    xs = [margin + i * STITCH_PITCH for i in range(int((BOARD_W - 2 * margin) // STITCH_PITCH) + 1)]
    ys = [margin + i * STITCH_PITCH for i in range(int((BOARD_H - 2 * margin) // STITCH_PITCH) + 1)]
    for x in xs + [BOARD_W - margin]:
        for y in ys + [BOARD_H - margin]:
            pt = pcbnew.VECTOR2I(mm(x), mm(y))
            if any(bb.Contains(pt) for bb in keepouts):
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
    if board.Zones():
        raise SystemExit("board already has zones -- regenerate it with build_pcb.py first")

    add_gnd_zones(board, gnd)
    stitches = add_stitching_vias(board, gnd)
    board.BuildConnectivity()
    if not pcbnew.ZONE_FILLER(board).Fill(board.Zones()):
        raise SystemExit("zone fill failed")
    board.Save(board_path)
    areas = ", ".join(
        f"{board.GetLayerName(z.GetLayer())} {z.GetFilledArea() / 1e12:.0f}mm2" for z in board.Zones()
    )
    print(f"poured GND: {areas}, {stitches} stitching vias")


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


# Manufacturing constraints. The stackup this board has always assumed --
# 1.6mm FR-4, two layers, 1oz outer copper -- was written down in this
# directory's README and nowhere else, and the IPC-2221 trace-width table
# depends on the copper weight.
#
# It was worse than undocumented. KiCad's minimums were left at their
# defaults, which are zero: m_TrackMinWidth and m_MinClearance both read back
# as 0.0mm on the finished board, so DRC was enforcing no process limit at
# all. A 0.05mm trace would have passed every check this project runs.
#
# The numbers below are what the board already uses -- 0.2mm track, 0.2mm
# clearance, 0.6mm vias on 0.3mm drills -- promoted from convention to rule.
# That is deliberately not a claim about any fab's capability: it makes DRC
# catch anything that drifts *below* what the design was drawn to, which is
# the failure that would otherwise reach fabrication unseen. Confirming these
# against the chosen manufacturer's process is a separate step, listed in the
# README.
STACKUP = {
    "thickness_mm": 1.6,
    "copper_weight_oz": 1,
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
    # --- Power tree (left column, x=2-32) ---
    # The IP5306's switching loop comes first: U2's BAT/SW/VOUT pins (6/7/8)
    # are all on its right-hand side, so L1 sits immediately to its right and
    # the snubber + VOUT cap on the row just below. An earlier revision had
    # these four parts 63-72mm away in the open band under the MCU, which
    # would have spread a 1uH boost converter's switch-node loop across the
    # whole board -- see README.md, "The IP5306 switching loop".
    "U2": (11.47, 5.78, 0, "IP5306"),      # IP5306 boost
    "L1": (20.0, 5.5, 0, "1uH"),           # boost inductor, SW(7) -> BAT(6)
    "C5": (18.0, 11.2, 0, "22uF"),         # VOUT(8) decoupling, at the IC
    "R14": (22.5, 11.2, 0, "0.5R"),        # SW-node snubber resistor
    "C4": (27.0, 11.2, 0, "22uF"),         # SW-node snubber capacitor
    "J2": (12.49, 16.6, 90, "BATT_2x18650_PARALLEL"),  # Battery connector, left edge
    "D2": (18.27, 16.6, 0, "LED (amber)"),   # BATT_LED1
    "R5": (22.78, 16.6, 0, "1k"),            # BATT_LED1 resistor
    "U1": (14.75, 22.5, 0, "MCP73831-2-OT"),  # MCP73831 charger
    "R3": (19.82, 22.5, 0, "2k"),            # CHG_PROG resistor
    "J1": (12.49, 30.6, 90, "USB-C"),        # USB-C, left edge
    # CC pull-downs, clear of the connector's fan-out band. They used to sit
    # at y=30.6, i.e. directly east of J1 between the D+ and D- pad rows, and
    # /CC1's diagonal run to R1 closed the only gap the D- pair had to cross
    # in: Freerouting could route pad A7 and not B7, and reported the net
    # finished anyway. R2 now sits above the band and R1 below it, matching
    # which side of the connector each one's pad is on.
    "R2": (20.5, 27.0, 0, "5.1k"),           # CC2 (J1 pad B5, y=28.85)
    "R1": (20.5, 34.0, 0, "5.1k"),           # CC1 (J1 pad A5, y=31.85)
    "D1": (14.75, 37.4, 0, "LED (amber)"),   # CHG_STAT LED
    "R4": (19.25, 37.4, 0, "1k"),            # CHG_STAT LED resistor
    "U3": (11.82, 43.27, 0, "AMS1117-3.3"),  # AMS1117 MCU rail
    "U4": (22.18, 43.27, 0, "AMS1117-3.3"),  # AMS1117 RF rail
    "J6": (17.0, 62.09, 0, "CR2032_HOLDER"),  # CR2032 holder (stacked above the
                               # power tree -- the only spot on the board wide
                               # enough for its real 27.46mm courtyard)

    # --- MCU cluster (center column, x=34-62) ---
    # SW1 moved here from beside U2 (its old spot is now L1's) -- it is a
    # momentary button on a static input, so distance from the IC costs
    # nothing, unlike the switching-loop parts that displaced it.
    "SW1": (34.5, 6.0, 0, "PWR_KEY"),        # PWR_KEY button
    "R7": (45.46, 5.07, 0, "10k"),           # BOOT0 pull-down
    "J3": (50.26, 5.07, 0, "BOOT0_OVERRIDE_JUMPER"),  # BOOT0 override jumper
    "R8": (45.46, 15.25, 0, "10k"),          # BOOT1 pull-down
    "J4": (50.26, 15.25, 0, "SWD_DEBUG"),    # SWD debug header
    "R6": (42.48, 26.12, 0, "10k"),          # NRST pull-up
    "SW2": (50.25, 26.12, 0, "RESET"),       # RESET button
    "Y1": (43.49, 34.28, 0, "8MHz"),         # crystal, right next to the MCU
    "C1": (53.27, 34.28, 0, "20pF"),         # crystal load cap 1
    "C2": (57.78, 34.28, 0, "20pF"),         # crystal load cap 2
    "U5": (48.0, 43.83, 0, "GD32VF103CCT6"),  # GD32VF103CCT6 MCU

    # --- Memory + wireless + audio (right column, x=64-96) ---
    "Q1": (68.42, 7.22, 0, "2N7002"),        # keyboard-backlight FET
    "U10": (75.65, 7.22, 0, "PAM8403D"),     # PAM8403D amp
    "R13": (82.43, 7.22, 0, "1k"),           # audio PWM-to-analog filter resistor
    "C3": (86.94, 7.22, 0, "100nF"),         # audio PWM-to-analog filter cap
    "J12": (91.74, 7.22, 0, "SPEAKER_1W_8OHM"),  # speaker header
    "U9": (69.14, 22.73, 0, "ESP32-C3-MINI-1U"),  # ESP32-C3-MINI-1U module
    "R11": (81.91, 22.73, 0, "10k"),         # EN pull-up
    "R12": (86.42, 22.73, 0, "10k"),         # IO9/BOOT pull-up
    # No antenna connector is placed. J7 (U.FL) and J8 (edge-mount SMA) used to
    # sit at (80, 35.53) and (94, 22.73); the ESP32-C3-MINI-1U's radio never
    # reaches board copper, so neither had anything to carry -- see README.md.
    "U6": (75.52, 42.48, 0, "W25Q64JVSSIQ"),  # W25Q64 flash
    "U7": (85.42, 42.48, 0, "23LC1024"),     # 23LC1024 SRAM
    "U8": (68.19, 53.77, 0, "DS3231M"),      # DS3231M RTC
    "R9": (77.15, 53.77, 0, "4.7k"),         # I2C pull-up SCL
    "R10": (81.66, 53.77, 0, "4.7k"),        # I2C pull-up SDA
    "J5": (91.22, 53.77, 90, "MICROSD"),     # microSD, right edge, near the RTC/memory group

    # --- Top-edge headers (display / keyboard controller / kbd backlight) ---
    "J9": (30, 76.5, 90, "RA8875_DISPLAY_MODULE"),   # display header, top edge
    "J10": (50, 76.5, 90, "CH552G_KEYBOARD_MCU"),    # keyboard-controller header
    "J11": (70, 76.5, 90, "KEYBOARD_BACKLIGHT_LEDS"),  # keyboard-backlight header
}


def main() -> None:
    comps, nets = parse_netlist(NETLIST_PATH)

    board = pcbnew.CreateEmptyBoard()
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
    thermal = add_thermal_vias(board, net_objs["GND"])

    out_path = "../main-board.kicad_pcb"
    board.Save(out_path)
    print(f"wrote {out_path} ({len(comps)} components, {len(nets)} nets, {thermal} U9 thermal vias)")
    write_project_netclasses()


if __name__ == "__main__":
    import sys

    # Two-stage by design: `build_pcb.py` places parts and writes the
    # netclasses, then the board goes out to Freerouting, then `--pour` adds
    # the ground plane on top of the finished copper. See pour_ground() for
    # why the pour cannot come first, and README.md for the full command
    # sequence.
    if "--pour" in sys.argv:
        pour_ground("../main-board.kicad_pcb")
    else:
        main()
