"""Programmatic KiCad 9 schematic builder.

Places components (from our project library or real KiCad system
libraries) at grid coordinates, and connects pins via short wire stubs
terminating in net labels -- the normal, idiomatic way to wire a large
schematic without drawing long point-to-point wires across the sheet.
Everything is emitted as plain S-expression text and validated with
`kicad-cli sch erc` / rendered to PDF, not visually laid out by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pinmap
import sexp

SYSTEM_LIB_DIR = "/usr/share/kicad/symbols"
GRID = 2.54


def load_lib_text(lib_file: str) -> str:
    return open(f"{SYSTEM_LIB_DIR}/{lib_file}.kicad_sym", encoding="utf-8").read()


@dataclass
class SymbolSource:
    """Where a lib_id's block text comes from, cached after first read."""

    lib_file: Optional[str]  # None => our own project library text (passed in directly)
    text_cache: Dict[str, str] = field(default_factory=dict)


class Schematic:
    def __init__(self, title: str, project_lib_text: str, project_name: str = "main-board") -> None:
        self.title = title
        self.project_name = project_name
        self.project_lib_text = project_lib_text
        self.components: List["Component"] = []
        self.wires: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        self.labels: List[Tuple[Tuple[float, float], str, str]] = []  # pos, text, kind(local/global)
        self.power_symbols: List["Component"] = []
        self.no_connects: List[Tuple[float, float]] = []
        self._used_symbol_blocks: Dict[str, str] = {}  # lib_id -> block text
        self._ref_counters: Dict[str, int] = {}
        self._sheet_uuid = sexp.new_uuid()

    # ------------------------------------------------------------------ #
    # Symbol block lookup / caching
    # ------------------------------------------------------------------ #

    def _get_block(self, lib_id: str) -> str:
        if lib_id in self._used_symbol_blocks:
            return self._used_symbol_blocks[lib_id]
        lib_name, symbol_name = lib_id.split(":", 1)
        if lib_name == "gridnet_parts":
            block = sexp.find_symbol_block(self.project_lib_text, symbol_name)
        else:
            text = load_lib_text(lib_name)
            block = sexp.find_symbol_block(text, symbol_name)
            m = re.search(r'\(extends "([^"]+)"\)', block)
            if m:
                # Some KiCad library symbols inherit graphics/pins from a
                # base symbol (e.g. AMS1117-3.3 extends AP1117-15). Flatten
                # into a self-contained copy rather than keeping the
                # `extends` reference, which would need renaming in lockstep
                # with the base's own cache key -- fragile once names get
                # requalified below.
                base_name = m.group(1)
                base = sexp.find_symbol_block(text, base_name)
                sub0 = sexp.find_symbol_block(base, f"{base_name}_0_1").replace(
                    f'"{base_name}_0_1"', f'"{symbol_name}_0_1"', 1
                )
                sub1 = sexp.find_symbol_block(base, f"{base_name}_1_1").replace(
                    f'"{base_name}_1_1"', f'"{symbol_name}_1_1"', 1
                )
                no_extends = re.sub(r'\n\s*\(extends "[^"]+"\)\n', "\n", block, count=1).rstrip()
                assert no_extends.endswith(")")
                block = no_extends[:-1] + sub0 + "\n" + sub1 + "\n\t)\n"
        # A schematic's lib_symbols cache keys each *top-level* entry by the
        # full "LibName:SymbolName" (confirmed against a real KiCad-generated
        # .kicad_sch) -- not the bare symbol name used inside an actual
        # .kicad_sym library file. Without this, the instance's lib_id can't
        # resolve to its cached graphics: properties still render (they live
        # on the instance itself) but the body/pins silently don't. The
        # nested sub-unit names (_0_1 / _1_1) stay BARE, unprefixed -- only
        # the top-level name gets qualified (also confirmed against the real
        # file; qualifying the sub-units too breaks parsing outright).
        block = block.replace(f'(symbol "{symbol_name}"', f'(symbol "{lib_id}"', 1)
        self._used_symbol_blocks[lib_id] = block
        return block

    # ------------------------------------------------------------------ #
    # Placement
    # ------------------------------------------------------------------ #

    def place(
        self,
        lib_id: str,
        ref_prefix: str,
        value: str,
        x: float,
        y: float,
        footprint_override: Optional[str] = None,
        extra_props: Optional[Dict[str, str]] = None,
    ) -> "Component":
        block = self._get_block(lib_id)
        n = self._ref_counters.get(ref_prefix, 0) + 1
        self._ref_counters[ref_prefix] = n
        ref = f"{ref_prefix}{n}"
        comp = Component(
            lib_id=lib_id,
            ref=ref,
            value=value,
            x=x,
            y=y,
            pins=pinmap.pin_positions(block),
            outward=pinmap.pin_outward_dirs(block),
            footprint_override=footprint_override,
            extra_props=extra_props or {},
        )
        self.components.append(comp)
        return comp

    def place_power(self, symbol: str, x: float, y: float) -> "Component":
        """Power symbols (e.g. power:GND, power:+3V3) are single-pin, and
        their pin IS the net -- placing one at a point connects that point
        to the named net."""
        return self.place(f"power:{symbol}", "#PWR", symbol, x, y)

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #

    def wire(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> None:
        self.wires.append((p1, p2))

    def label_at(self, pos: Tuple[float, float], text: str, kind: str = "local", justify: str = "left") -> None:
        self.labels.append((pos, text, kind, justify))

    @staticmethod
    def _justify_for_dir(dx: float, dy: float) -> str:
        # Label text is anchored at the stub tip and grows in the justify
        # direction. For a pin whose stub points further LEFT (dx<0, e.g. a
        # left-side MCU pin), growing text rightward (the KiCad default,
        # "left" justify) runs it straight back through the pin number and
        # into the body where the pin's own name is drawn. Growing it
        # leftward instead ("right" justify) keeps it in the open area
        # outside the symbol, matching what "left" justify already does
        # correctly for right-side/downward pins.
        if dx < 0:
            return "right"
        return "left"

    def net(self, comp: "Component", pin: str, label: str, kind: str = "local", stub: float = 5.08) -> None:
        """Connect a component pin to a net label via a short wire stub
        drawn outward from the pin (the standard label-based connection
        pattern for busy schematics)."""
        p0 = comp.pin_sheet_pos(pin)
        dx, dy = comp.pin_outward_sheet_dir(pin)
        p1 = (p0[0] + dx * stub, p0[1] + dy * stub)
        self.wire(p0, p1)
        self.label_at(p1, label, kind, justify=self._justify_for_dir(dx, dy))

    def power_pin(self, comp: "Component", pin: str, symbol: str, stub: float = 2.54) -> None:
        """Connect a pin directly to a power symbol (GND, +3V3, ...),
        placed just beyond the pin."""
        p0 = comp.pin_sheet_pos(pin)
        dx, dy = comp.pin_outward_sheet_dir(pin)
        p1 = (p0[0] + dx * stub, p0[1] + dy * stub)
        self.wire(p0, p1)
        self.place_power(symbol, p1[0], p1[1])

    def no_connect(self, comp: "Component", pin: str) -> None:
        """Explicitly mark a pin as intentionally unconnected (e.g. an
        MCU GPIO this design doesn't use yet) so ERC's `pin_not_connected`
        check doesn't flag it -- the correct way to say "yes, really" rather
        than just leaving it silently dangling."""
        self.no_connects.append(comp.pin_sheet_pos(pin))

    def pwr_flag(self, comp: "Component", pin: str, net_label: str, stub: float = 5.08) -> None:
        """Mark a pin's net as externally driven (e.g. a battery connector's
        output) using KiCad's standard PWR_FLAG mechanism, so ERC's
        `power_pin_not_driven` check doesn't treat it as unpowered just
        because no *symbol* pin of type power_out happens to be on that net."""
        self.net(comp, pin, net_label, stub=stub)
        p0 = comp.pin_sheet_pos(pin)
        dx, dy = comp.pin_outward_sheet_dir(pin)
        flag_pos = (p0[0] + dx * (stub + 5.08), p0[1] + dy * (stub + 5.08))
        flag = self.place("power:PWR_FLAG", "#FLG", "PWR_FLAG", flag_pos[0], flag_pos[1])
        self.label_at(flag.pin_sheet_pos("1"), net_label, "local", justify=self._justify_for_dir(dx, dy))

    def bare_pwr_flag(self, x: float, y: float, net_label: str) -> None:
        """A PWR_FLAG not anchored to any component pin -- for a net like
        GND that doesn't have one obvious "source" pin to hang it off of."""
        flag = self.place("power:PWR_FLAG", "#FLG", "PWR_FLAG", x, y)
        self.label_at(flag.pin_sheet_pos("1"), net_label, "local")

    # ------------------------------------------------------------------ #
    # Emission
    # ------------------------------------------------------------------ #

    def _emit_lib_symbols(self) -> str:
        # Power symbols need their block fetched too, from power.kicad_sym.
        parts = []
        seen_names = set()
        for lib_id, block in self._used_symbol_blocks.items():
            lib_name, symbol_name = lib_id.split(":", 1)
            if symbol_name in seen_names:
                continue
            seen_names.add(symbol_name)
            parts.append(sexp.indent(block, 2))
        return "\t(lib_symbols\n" + "\n".join(parts) + "\n\t)\n"

    def _emit_component(self, comp: "Component") -> str:
        lib_name, symbol_name = comp.lib_id.split(":", 1)
        fp = comp.footprint_override or ""
        uid = sexp.new_uuid()
        extra_props = "".join(
            f'\t\t(property "{k}" "{v}"\n\t\t\t(at {comp.x} {comp.y} 0)\n'
            f"\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t\t)\n"
            for k, v in comp.extra_props.items()
        )
        # Every symbol instance needs an `instances` block tying its
        # reference designator to this project/sheet -- without it the
        # body/pins silently fail to render (found by comparing against a
        # real KiCad-generated .kicad_sch). Per-pin uuid overrides are NOT
        # needed for ordinary parts -- adding them crashed kicad-cli outright
        # (confirmed by bisection); they're apparently only for cases KiCad
        # itself writes when a user does per-pin alternate-assignment, not
        # something a generator should synthesize.
        instances = (
            f'\t\t(instances\n'
            f'\t\t\t(project "{self.project_name}"\n'
            f'\t\t\t\t(path "/{self._sheet_uuid}"\n'
            f'\t\t\t\t\t(reference "{comp.ref}")\n'
            f'\t\t\t\t\t(unit 1)\n'
            f'\t\t\t\t)\n'
            f'\t\t\t)\n'
            f'\t\t)\n'
        )
        return (
            f'\t(symbol\n'
            f'\t\t(lib_id "{comp.lib_id}")\n'
            f'\t\t(at {comp.x} {comp.y} 0)\n'
            f'\t\t(unit 1)\n'
            f'\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
            f'\t\t(uuid "{uid}")\n'
            f'\t\t(property "Reference" "{comp.ref}"\n'
            f'\t\t\t(at {comp.x} {comp.y - 7.62} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)))\n'
            f'\t\t)\n'
            f'\t\t(property "Value" "{comp.value}"\n'
            f'\t\t\t(at {comp.x} {comp.y - 10.16} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)))\n'
            f'\t\t)\n'
            f'\t\t(property "Footprint" "{fp}"\n'
            f'\t\t\t(at {comp.x} {comp.y} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n'
            f'\t\t)\n'
            f"{extra_props}"
            f"{instances}"
            f'\t)\n'
        )

    def _emit_wire(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> str:
        uid = sexp.new_uuid()
        return (
            f'\t(wire\n'
            f'\t\t(pts (xy {p1[0]:.2f} {p1[1]:.2f}) (xy {p2[0]:.2f} {p2[1]:.2f}))\n'
            f'\t\t(stroke (width 0) (type default))\n'
            f'\t\t(uuid "{uid}")\n'
            f'\t)\n'
        )

    def _emit_label(self, pos: Tuple[float, float], text: str, kind: str, justify: str = "left") -> str:
        uid = sexp.new_uuid()
        tag = "label" if kind == "local" else "global_label"
        shape = "" if kind == "local" else "\n\t\t(shape input)"
        return (
            f'\t({tag} "{text}"\n'
            f'\t\t(at {pos[0]:.2f} {pos[1]:.2f} 0)'
            f'{shape}\n'
            f'\t\t(effects (font (size 1.27 1.27)) (justify {justify}))\n'
            f'\t\t(uuid "{uid}")\n'
            f'\t)\n'
        )

    def _emit_no_connect(self, pos: Tuple[float, float]) -> str:
        uid = sexp.new_uuid()
        return f'\t(no_connect\n\t\t(at {pos[0]:.2f} {pos[1]:.2f})\n\t\t(uuid "{uid}")\n\t)\n'

    def render(self) -> str:
        header = (
            "(kicad_sch\n"
            "\t(version 20250114)\n"
            '\t(generator "gridnet_build_schematic")\n'
            '\t(generator_version "9.0")\n'
            f'\t(uuid "{self._sheet_uuid}")\n'
            '\t(paper "A2")\n'
            f'\t(title_block\n\t\t(title "{self.title}")\n\t\t(company "GRIDNET")\n\t)\n'
        )
        body = []
        for c in self.components:
            body.append(self._emit_component(c))
        for p1, p2 in self.wires:
            body.append(self._emit_wire(p1, p2))
        for pos, text, kind, justify in self.labels:
            body.append(self._emit_label(pos, text, kind, justify))
        for pos in self.no_connects:
            body.append(self._emit_no_connect(pos))
        footer = (
            '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n'
            "\t(embedded_fonts no)\n"
        )
        return header + self._emit_lib_symbols() + "".join(body) + footer + ")\n"


class Component:
    def __init__(
        self,
        lib_id: str,
        ref: str,
        value: str,
        x: float,
        y: float,
        pins: Dict[str, Tuple[float, float]],
        outward: Dict[str, Tuple[int, int]],
        footprint_override: Optional[str],
        extra_props: Dict[str, str],
    ) -> None:
        self.lib_id = lib_id
        self.ref = ref
        self.value = value
        self.x = x
        self.y = y
        self._pins = pins
        self._outward = outward
        self.footprint_override = footprint_override
        self.extra_props = extra_props

    def pin_sheet_pos(self, number: str) -> Tuple[float, float]:
        lx, ly = self._pins[number]
        # Local symbol space is Y-up; sheet space is Y-down -- flip.
        return (self.x + lx, self.y - ly)

    def pin_outward_sheet_dir(self, number: str) -> Tuple[int, int]:
        dx, dy = self._outward[number]
        return (dx, -dy)
