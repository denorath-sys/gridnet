"""Build a simple rectangular-body custom KiCad symbol (body + pins on the
left/right edges) as valid KiCad 9 S-expression text, for parts that don't
exist in KiCad's bundled libraries.

This is deliberately the simplest possible symbol shape (one rectangle, pins
evenly spaced top-to-bottom on each side) — enough for schematic capture and
ERC, not a claim about the real IC's physical pinout being verified. Every
custom symbol built this way is flagged NEEDS DATASHEET VERIFICATION in the
generated content and in hardware/pcb/main-board/README.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

GRID = 2.54  # 0.1" KiCad schematic grid

ELECTRICAL_TYPES = {
    "in": "input",
    "out": "output",
    "bidi": "bidirectional",
    "pwr": "power_in",
    "pwr_out": "power_out",
    "pas": "passive",
    "oc": "open_collector",
    "nc": "no_connect",
}


@dataclass
class Pin:
    number: str
    name: str
    etype: str  # key into ELECTRICAL_TYPES
    side: str  # "left" or "right"


def _pin_sexp(pin: Pin, x: float, y: float, rotation: int) -> str:
    etype = ELECTRICAL_TYPES[pin.etype]
    return (
        f'\t\t\t(pin {etype} line\n'
        f'\t\t\t\t(at {x} {y} {rotation})\n'
        f'\t\t\t\t(length 2.54)\n'
        f'\t\t\t\t(name "{pin.name}"\n'
        f'\t\t\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t\t\t)\n'
        f'\t\t\t\t(number "{pin.number}"\n'
        f'\t\t\t\t\t(effects (font (size 1.27 1.27)))\n'
        f'\t\t\t\t)\n'
        f'\t\t\t)\n'
    )


def build_symbol(
    name: str,
    reference: str,
    footprint: str,
    pins: List[Pin],
    description: str,
    datasheet: str = "~",
) -> str:
    left = [p for p in pins if p.side == "left"]
    right = [p for p in pins if p.side == "right"]
    height = max(len(left), len(right)) * GRID + GRID * 2
    half_h = round(height / 2 / GRID) * GRID

    # Width scales with the longest pin name on each side, so long names
    # (e.g. "PC15/OSC32_OUT") don't collide with the opposite side's text.
    def name_len(pins_side: List[Pin]) -> int:
        return max((len(p.name) for p in pins_side), default=0)

    char_width = 1.2  # mm, rough glyph width at 1.27mm font size
    min_width = 20.32
    width = max(min_width, GRID * 2 + (name_len(left) + name_len(right)) * char_width)
    width = round(width / GRID) * GRID

    body_top = half_h
    body_bottom = -half_h
    body_left = -width / 2
    body_right = width / 2

    def positions(count: int) -> List[float]:
        # evenly spaced, centered, top to bottom
        span = (count - 1) * GRID
        start = span / 2
        return [start - i * GRID for i in range(count)]

    pin_sexps = []
    for pin, y in zip(left, positions(len(left))):
        pin_sexps.append(_pin_sexp(pin, body_left - GRID, y, 0))
    for pin, y in zip(right, positions(len(right))):
        pin_sexps.append(_pin_sexp(pin, body_right + GRID, y, 180))

    props = f"""\t\t(property "Reference" "{reference}"
\t\t\t(at {body_left} {body_top + GRID} 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Value" "{name}"
\t\t\t(at {body_left} {body_top + GRID * 2} 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Footprint" "{footprint}"
\t\t\t(at 0 0 0)
\t\t\t(effects (font (size 1.27 1.27)) (hide yes))
\t\t)
\t\t(property "Datasheet" "{datasheet}"
\t\t\t(at 0 0 0)
\t\t\t(effects (font (size 1.27 1.27)) (hide yes))
\t\t)
\t\t(property "Description" "{description} — CUSTOM SYMBOL, generic rectangle body, needs datasheet pin-number verification before use"
\t\t\t(at 0 0 0)
\t\t\t(effects (font (size 1.27 1.27)) (hide yes))
\t\t)
"""

    body = (
        f'\t\t(rectangle\n'
        f'\t\t\t(start {body_left} {body_top})\n'
        f'\t\t\t(end {body_right} {body_bottom})\n'
        f'\t\t\t(stroke (width 0.254) (type default))\n'
        f'\t\t\t(fill (type background))\n'
        f'\t\t)\n'
    )

    return (
        f'\t(symbol "{name}"\n'
        f'\t\t(exclude_from_sim no)\n'
        f'\t\t(in_bom yes)\n'
        f'\t\t(on_board yes)\n'
        f"{props}"
        f'\t\t(symbol "{name}_0_1"\n'
        f"{body}"
        f'\t\t)\n'
        f'\t\t(symbol "{name}_1_1"\n'
        f"{''.join(pin_sexps)}"
        f'\t\t)\n'
        f'\t)\n'
    )
