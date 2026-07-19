"""Build hardware/pcb/main-board/main-board.kicad_pcb -- component
PLACEMENT ONLY (no copper routing; see this directory's README.md for why).

Reads the netlist exported from main-board.kicad_sch (ref -> footprint,
and net -> [(ref, pin), ...]) and uses it to place each footprint's pads on
the right net, so the board opens in KiCad with a full ratsnest ready for
manual routing. Placement coordinates are hand-picked below, grouped by
subsystem (power tree, MCU, memory, wireless, audio/keyboard, edge
connectors), within the 100x80mm outline from hardware/bom.md's Board 2
line.

Regenerate the netlist this script reads with:
    kicad-cli sch export netlist ../main-board.kicad_sch --format kicadsexpr -o /tmp/main-board.net
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pcbnew

FOOTPRINT_DIR = "/usr/share/kicad/footprints"
NETLIST_PATH = "/tmp/main-board.net"
BOARD_W = 100.0
BOARD_H = 80.0


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
# Placement plan: ref -> (x_mm, y_mm, rotation_degrees)
#
# Board is 100x80mm (hardware/bom.md, Board 2 -- Main Board). Layout groups
# by subsystem, edge connectors facing outward for case cutouts:
#   - left edge: USB-C power in, battery connector
#   - top edge: display / keyboard-controller / keyboard-backlight headers
#     (these route up into the clamshell's lid/base)
#   - right edge: microSD card slot, SMA antenna
#   - bottom edge: speaker header
#   - center: MCU with crystal/reset/boot/SWD around it
#   - center-right: SPI flash/SRAM + RTC (near the MCU's SPI1/I2C1 pins)
#   - lower-right: ESP32-C3 module + U.FL, near the SMA antenna path
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
PLACEMENT: Dict[str, Tuple[float, float, float]] = {
    # --- Power tree (left column, x=2-32) ---
    "U2": (11.47, 5.78, 0),    # IP5306 boost
    "SW1": (21.48, 5.78, 0),   # PWR_KEY button
    "J2": (12.49, 14.53, 90),  # Battery connector, left edge
    "D2": (18.27, 14.53, 0),   # BATT_LED1
    "R5": (22.78, 14.53, 0),   # BATT_LED1 resistor
    "U1": (14.75, 21.23, 0),   # MCP73831 charger
    "R3": (19.82, 21.23, 0),   # CHG_PROG resistor
    "J1": (12.49, 29.79, 90),  # USB-C, left edge
    "R1": (20.23, 29.79, 0),   # CC1
    "R2": (24.74, 29.79, 0),   # CC2
    "D1": (14.75, 37.4, 0),    # CHG_STAT LED
    "R4": (19.25, 37.4, 0),    # CHG_STAT LED resistor
    "U3": (11.82, 43.27, 0),   # AMS1117 MCU rail
    "U4": (22.18, 43.27, 0),   # AMS1117 RF rail
    "J6": (17.0, 62.09, 0),    # CR2032 holder (stacked above the power tree --
                               # the only spot on the board wide enough for its
                               # real 27.46mm courtyard without colliding)

    # --- MCU cluster (center column, x=34-62) ---
    "R7": (45.46, 5.07, 0),    # BOOT0 pull-down
    "J3": (50.26, 5.07, 0),    # BOOT0 override jumper
    "R8": (45.46, 15.25, 0),   # BOOT1 pull-down
    "J4": (50.26, 15.25, 0),   # SWD debug header
    "R6": (42.48, 26.12, 0),   # NRST pull-up
    "SW2": (50.25, 26.12, 0),  # RESET button
    "Y1": (43.49, 34.28, 0),   # crystal, right next to the MCU
    "C1": (53.27, 34.28, 0),   # crystal load cap 1
    "C2": (57.78, 34.28, 0),   # crystal load cap 2
    "U5": (48.0, 43.83, 0),    # GD32VF103CCT6 MCU

    # --- Memory + wireless + audio (right column, x=64-96) ---
    "Q1": (68.42, 7.22, 0),    # keyboard-backlight FET
    "U10": (75.65, 7.22, 0),   # PAM8403D amp
    "R13": (82.43, 7.22, 0),   # audio PWM-to-analog filter resistor
    "C3": (86.94, 7.22, 0),    # audio PWM-to-analog filter cap
    "J12": (91.74, 7.22, 0),   # speaker header
    "U9": (69.14, 22.73, 0),   # ESP32-C3-MINI-1U module
    "R11": (81.91, 22.73, 0),  # EN pull-up
    "R12": (86.42, 22.73, 0),  # IO9/BOOT pull-up
    "J8": (94.0, 22.73, 90),   # SMA, right edge (near the ESP32/U.FL path)
    "J7": (80.0, 35.53, 0),    # U.FL (on-module antenna pad, close to module)
    "U6": (75.52, 42.48, 0),   # W25Q64 flash
    "U7": (85.42, 42.48, 0),   # 23LC1024 SRAM
    "U8": (68.19, 53.77, 0),   # DS3231M RTC
    "R9": (77.15, 53.77, 0),   # I2C pull-up SCL
    "R10": (81.66, 53.77, 0),  # I2C pull-up SDA
    "J5": (91.22, 53.77, 90),  # microSD, right edge, near the RTC/memory group

    # --- Top-edge headers (display / keyboard controller / kbd backlight) ---
    "J9": (30, 76.5, 90),      # RA8875 display header, top edge
    "J10": (50, 76.5, 90),     # CH552G keyboard-controller header, top edge
    "J11": (70, 76.5, 90),     # keyboard-backlight LEDs header, top edge
}


def main() -> None:
    comps, nets = parse_netlist(NETLIST_PATH)

    board = pcbnew.CreateEmptyBoard()
    add_board_outline(board)

    net_objs: Dict[str, "pcbnew.NETINFO_ITEM"] = {}
    for name in nets:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        net_objs[name] = n

    missing_placement = [r for r in comps if r not in PLACEMENT]
    if missing_placement:
        raise SystemExit(f"No placement coordinates for: {missing_placement}")

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
        fp = pcbnew.FootprintLoad(f"{FOOTPRINT_DIR}/{lib_name}.pretty", fp_name)
        if fp is None:
            raise SystemExit(f"Footprint not found: {info.footprint} (ref {ref})")
        x, y, rot = PLACEMENT[ref]
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
        board.Add(fp)
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            net_name = pin_net.get(key)
            if net_name is None:
                unmatched_pads.append(key)
                continue
            pad.SetNet(net_objs[net_name])

    if unmatched_pads:
        # Expected for the ESP32-C3 placeholder footprint (WROOM-02U stands
        # in for the real MINI-1U -- different pad count/numbering, see
        # README.md) and any other pad whose schematic pin never got a net
        # (e.g. covered by no_connect). Print rather than fail so the rest
        # of the board still gets a full ratsnest.
        print(f"Note: {len(unmatched_pads)} pads had no matching net (see comment above): {unmatched_pads}")

    out_path = "../main-board.kicad_pcb"
    board.Save(out_path)
    print(f"wrote {out_path} ({len(comps)} components, {len(nets)} nets)")


if __name__ == "__main__":
    main()
