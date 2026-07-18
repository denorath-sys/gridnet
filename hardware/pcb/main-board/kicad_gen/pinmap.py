"""Extract (number -> local x,y) pin position maps from a symbol's raw
S-expression text, for any symbol (ours or copied from KiCad's libraries).
Needed so the schematic generator can compute where a wire stub should
land when connecting to a given pin of a placed component.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

PIN_RE = re.compile(
    r"\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)\s*\(length ([-\d.]+)\)"
    r".*?\(number \"([^\"]+)\"",
    re.S,
)

# rotation (KiCad pin "at" angle) -> unit vector pointing OUTWARD from the
# body (away from it, where a wire stub should extend). KiCad's pin angle
# is the direction from the connection point back toward the body, so
# outward is that angle + 180.
_OUTWARD = {0: (-1, 0), 180: (1, 0), 90: (0, -1), 270: (0, 1)}


def pin_positions(symbol_block: str) -> Dict[str, Tuple[float, float]]:
    """Returns {pin_number: (x, y)} in the symbol's own local coordinate
    space (i.e. the position of the pin's outer/connection end, exactly as
    given in its `(at x y rot)`), by scanning every `(pin ...)` in the
    block (across all sub-units)."""
    out = {}
    for m in PIN_RE.finditer(symbol_block):
        x, y, rot, length, number = m.groups()
        out[number] = (float(x), float(y))
    return out


def pin_outward_dirs(symbol_block: str) -> Dict[str, Tuple[int, int]]:
    """Returns {pin_number: (dx, dy)} unit vector pointing away from the
    symbol body, in the same local coordinate space as pin_positions()."""
    out = {}
    for m in PIN_RE.finditer(symbol_block):
        x, y, rot, length, number = m.groups()
        out[number] = _OUTWARD[int(rot)]
    return out
