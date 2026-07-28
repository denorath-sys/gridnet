"""Assemble hardware/pcb/main-board/gridnet_parts.kicad_sym — the
project-local symbol library for the Main Board schematic.

Combines:
  (a) exact symbol blocks copied programmatically from KiCad's own bundled
      libraries (no hand-retyping -> no transcription risk) for parts that
      have a real or pin-compatible match there, and
  (b) custom-built generic-rectangle symbols (see make_symbol.py) for parts
      with no library match, each explicitly flagged for datasheet
      verification before this design is used for real layout/fab.

See README.md in this directory for the per-part confidence/rationale
writeup this file's choices are based on.
"""

from __future__ import annotations

import re

import sexp
from make_symbol import Pin, build_symbol

KICAD_SYMBOLS_DIR = "/usr/share/kicad/symbols"

HEADER = """(kicad_symbol_lib
\t(version 20241209)
\t(generator "gridnet_build_library")
\t(generator_version "9.0")
"""
FOOTER = ")\n"


def load(lib_file: str) -> str:
    return open(f"{KICAD_SYMBOLS_DIR}/{lib_file}.kicad_sym", encoding="utf-8").read()


def extract_real(lib_file: str, symbol_name: str, rename_to: str | None = None) -> str:
    text = load(lib_file)
    block = sexp.find_symbol_block(text, symbol_name)
    if rename_to and rename_to != symbol_name:
        # Only rename the top-level symbol name and its two sub-unit names
        # (name_0_1 / name_1_1), not any unrelated occurrence of the string.
        block = block.replace(f'(symbol "{symbol_name}"', f'(symbol "{rename_to}"', 1)
        block = block.replace(f'"{symbol_name}_0_1"', f'"{rename_to}_0_1"')
        block = block.replace(f'"{symbol_name}_1_1"', f'"{rename_to}_1_1"')
        # Update the Value property text (2nd property block) to match
        block = block.replace(f'(property "Value" "{symbol_name}"', f'(property "Value" "{rename_to}"', 1)
    return sexp.indent(block, 1)


def extract_flatten_extends(lib_file: str, symbol_name: str) -> str:
    """For a symbol defined via `(extends "BASE")` -- KiCad's way of
    inheriting a base symbol's graphics/pins -- build a fully self-contained
    copy instead: this symbol's own properties + the base's graphical
    sub-units, `extends` reference dropped. Simpler and more robust than
    keeping the extends relationship consistent once symbol names get
    requalified inside a schematic's lib_symbols cache (which is exactly
    where this bit us: a renamed derived symbol's `(extends "BASE")` no
    longer matched the base's own renamed cache entry)."""
    text = load(lib_file)
    derived = sexp.find_symbol_block(text, symbol_name)
    m = re.search(r'\(extends "([^"]+)"\)', derived)
    if not m:
        return sexp.indent(derived, 1)
    base_name = m.group(1)
    base = sexp.find_symbol_block(text, base_name)
    base_sub_0 = sexp.find_symbol_block(base, f"{base_name}_0_1").replace(
        f'"{base_name}_0_1"', f'"{symbol_name}_0_1"', 1
    )
    base_sub_1 = sexp.find_symbol_block(base, f"{base_name}_1_1").replace(
        f'"{base_name}_1_1"', f'"{symbol_name}_1_1"', 1
    )
    derived_no_extends = re.sub(r'\n\s*\(extends "[^"]+"\)\n', "\n", derived, count=1)
    body = derived_no_extends.rstrip()
    assert body.endswith(")")
    body = body[:-1]  # drop the final closing paren -- we'll re-add it after splicing in the base's graphics
    flattened = body + sexp.indent(base_sub_0, 2) + "\n" + sexp.indent(base_sub_1, 2) + "\n\t)\n"
    return sexp.indent(flattened, 1)


def main() -> None:
    parts = []

    # --- Real / pin-compatible library parts, copied exactly ---------- #

    # AMS1117-3.3 extends AP1117-15 in KiCad's library -- flattened to a
    # single self-contained symbol, see extract_flatten_extends().
    parts.append(extract_flatten_extends("Regulator_Linear", "AMS1117-3.3"))

    # W25Q series shares one SOIC-8 pinout across densities (Winbond
    # datasheet family) -- reuse W25Q32JVSS's real, verified pin layout,
    # relabeled to our actual BOM part (W25Q64JVSSIQ, 8MB).
    parts.append(extract_real("Memory_Flash", "W25Q32JVSS", rename_to="W25Q64JVSSIQ"))

    # DS3231M substituted for the BOM's original DS3231SN -- see README.md:
    # same SCL/SDA/VBAT/32KHZ/INT-SQW/RST functionality, smaller/cheaper
    # package, real KiCad library part with a verified pinout.
    parts.append(extract_real("Timer_RTC", "DS3231M"))

    parts.append(extract_real("Battery_Management", "MCP73831-2-OT"))
    parts.append(extract_real("Amplifier_Audio", "PAM8403D"))

    # --- Custom generic-rectangle symbols (NEEDS DATASHEET VERIFICATION) #

    parts.append(
        build_symbol(
            name="23LC1024",
            reference="U",
            footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            description="Microchip 1Mbit SPI serial SRAM, SOIC-8 -- pinout verified against the real Microchip 23A1024/23LC1024 datasheet (DS20005142C)",
            datasheet="https://ww1.microchip.com/downloads/en/DeviceDoc/20005142C.pdf",
            verified=True,
            pins=[
                Pin("1", "~{CS}", "in", "left"),
                Pin("5", "SI/SIO0", "bidi", "left"),
                Pin("6", "SCK", "in", "left"),
                Pin("4", "VSS", "pwr", "left"),
                Pin("2", "SO/SIO1", "bidi", "right"),
                Pin("3", "~{WP}/SIO2", "bidi", "right"),
                Pin("7", "~{HOLD}/SIO3", "bidi", "right"),
                Pin("8", "VDD", "pwr", "right"),
            ],
        )
    )

    parts.append(
        build_symbol(
            name="IP5306",
            reference="U",
            footprint="Package_SO:SOP-8_3.9x4.9mm_P1.27mm",
            description="Boost converter + Li-ion charge/battery management IC (common power-bank IC) -- pinout verified against the real Injoinic IP5306 datasheet (V1.3): VIN/LED1/LED2/LED3/KEY/BAT/SW/VOUT + PowerPAD-as-GND, eSOP8",
            datasheet="https://datasheet.lcsc.com/lcsc/2304140030_INJOINIC-IP5306_C181692.pdf",
            verified=True,
            pins=[
                Pin("1", "VIN", "pwr", "left"),  # 5V charge input
                Pin("2", "LED1", "out", "left"),
                Pin("3", "LED2", "out", "left"),
                Pin("4", "LED3", "out", "left"),
                Pin("5", "KEY", "in", "right"),  # push-button control
                Pin("6", "BAT", "pwr", "right"),
                Pin("7", "SW", "pas", "right"),  # DCDC switch node -- external inductor to VOUT
                Pin("8", "VOUT", "pwr_out", "right"),  # 5V boost output
                Pin("9", "GND", "pwr", "left"),  # exposed PowerPAD, not a numbered lead -- see README.md
            ],
        )
    )

    parts.append(
        build_symbol(
            name="ESP32-C3-MINI-1U",
            reference="U",
            # Real MINI-1U footprint, vendored from Espressif's official KiCad
            # library (footprints/Espressif.pretty/ESP32-C3-MINI-1U.kicad_mod,
            # CC-BY-SA 4.0) into ../gridnet_footprints.pretty/ -- see that
            # directory's README.md for provenance. Verified: 53 distinct pad
            # numbers, pad 49 (GND) as the expected 3x3 thermal-pad array,
            # matching Table 3-1 of the datasheet used for the pin list below.
            footprint="gridnet_footprints:ESP32-C3-MINI-1U",
            description="Espressif Wi-Fi/BLE module, external-antenna variant (the antenna jack is on the module; the module exposes no RF pad) -- pin functions AND pad numbers verified against the real Espressif ESP32-C3-MINI-1/1U datasheet (v2.2) Table 3-1; every GND pad (including the pin-49 thermal-pad array) and every real signal pad is now drawn -- only the 14 true NC pads (4,7,9,10,15,17,24,25,28,29,32-35) are omitted. Footprint is the real MINI-1U footprint (see comment above), not a placeholder.",
            datasheet="https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.pdf",
            verified=True,
            pins=[
                Pin("1", "GND", "pwr", "left"),
                Pin("2", "GND", "pwr", "left"),
                Pin("3", "3V3", "pwr", "left"),
                Pin("8", "EN", "in", "left"),
                Pin("5", "IO2", "bidi", "left"),
                Pin("6", "IO3", "bidi", "left"),
                Pin("12", "IO0/BOOT_SEL", "bidi", "left"),
                Pin("13", "IO1", "bidi", "left"),
                Pin("16", "IO10", "bidi", "left"),
                Pin("18", "IO4", "bidi", "right"),
                Pin("19", "IO5", "bidi", "right"),
                Pin("20", "IO6", "bidi", "right"),
                Pin("21", "IO7", "bidi", "right"),
                Pin("22", "IO8", "bidi", "right"),
                Pin("23", "IO9/BOOT", "bidi", "right"),
                Pin("26", "IO18/USB_D-", "bidi", "right"),
                Pin("27", "IO19/USB_D+", "bidi", "right"),
                Pin("30", "U0RXD", "in", "right"),
                Pin("31", "U0TXD", "out", "right"),
                # There is deliberately no ANT pin here. An earlier revision
                # invented one (pin *number* "ANT", which matches no pad in the
                # footprint) so the schematic could wire the radio to a
                # board-mounted connector. Table 3-1 lists 53 pads and no RF
                # pad among them: 1, 2, 11, 14 and 36-53 are GND, the rest are
                # 3V3, EN and IO. The radio only leaves through the antenna
                # jack on the module -- see hardware/pcb/main-board/README.md's
                # "The antenna path never touched the board".
                # Remaining GND pads (Table 3-1: "1, 2, 11, 14, 36-53"), added
                # so every real ground pad gets grounded, not just 1/2 -- see
                # hardware/pcb/main-board/README.md's "Real ESP32-C3-MINI-1U
                # footprint" for why this was previously left half-done.
                Pin("11", "GND", "pwr", "left"),
                Pin("14", "GND", "pwr", "left"),
                Pin("36", "GND", "pwr", "left"),
                Pin("37", "GND", "pwr", "left"),
                Pin("38", "GND", "pwr", "left"),
                Pin("39", "GND", "pwr", "left"),
                Pin("40", "GND", "pwr", "left"),
                Pin("41", "GND", "pwr", "left"),
                Pin("42", "GND", "pwr", "left"),
                Pin("43", "GND", "pwr", "left"),
                Pin("44", "GND", "pwr", "right"),
                Pin("45", "GND", "pwr", "right"),
                Pin("46", "GND", "pwr", "right"),
                Pin("47", "GND", "pwr", "right"),
                Pin("48", "GND", "pwr", "right"),
                # Pin 49 is the exposed thermal pad -- physically 9 separate
                # SMD copper islands in the real footprint (a 3x3 array under
                # the module), all sharing pad number "49", so wiring this
                # one symbol pin to GND grounds all 9 automatically.
                Pin("49", "GND", "pwr", "right"),
                Pin("50", "GND", "pwr", "right"),
                Pin("51", "GND", "pwr", "right"),
                Pin("52", "GND", "pwr", "right"),
                Pin("53", "GND", "pwr", "right"),
            ],
        )
    )

    parts.append(
        build_symbol(
            name="GD32VF103CCT6",
            reference="U",
            footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",
            description="GigaDevice RISC-V MCU, LQFP48, 256KB Flash/32KB RAM -- pinout verified against the real GD32VF103 datasheet (Rev1.6) Figure 2-4 'GD32VF103Cx LQFP48 pinouts', which matches the STM32F103C8/CB-compatible arrangement pin-for-pin",
            datasheet="https://www.gd32mcu.com/data/documents/datasheet/GD32VF103_Datasheet_Rev1.6.pdf",
            verified=True,
            pins=[
                Pin("1", "VBAT", "pwr", "left"),
                Pin("2", "PC13", "bidi", "left"),
                Pin("3", "PC14/OSC32_IN", "bidi", "left"),
                Pin("4", "PC15/OSC32_OUT", "bidi", "left"),
                Pin("5", "PD0/OSC_IN", "bidi", "left"),
                Pin("6", "PD1/OSC_OUT", "bidi", "left"),
                Pin("7", "NRST", "in", "left"),
                Pin("8", "VSSA", "pwr", "left"),
                Pin("9", "VDDA", "pwr", "left"),
                Pin("10", "PA0", "bidi", "left"),
                Pin("11", "PA1", "bidi", "left"),
                Pin("12", "PA2", "bidi", "left"),
                Pin("13", "PA3", "bidi", "left"),
                Pin("14", "PA4", "bidi", "left"),
                Pin("15", "PA5", "bidi", "left"),
                Pin("16", "PA6", "bidi", "left"),
                Pin("17", "PA7", "bidi", "left"),
                Pin("18", "PB0", "bidi", "left"),
                Pin("19", "PB1", "bidi", "left"),
                Pin("20", "PB2/BOOT1", "bidi", "left"),
                Pin("21", "PB10", "bidi", "left"),
                Pin("22", "PB11", "bidi", "left"),
                Pin("23", "VSS_1", "pwr", "left"),
                Pin("24", "VDD_1", "pwr", "left"),
                Pin("25", "PB12", "bidi", "right"),
                Pin("26", "PB13", "bidi", "right"),
                Pin("27", "PB14", "bidi", "right"),
                Pin("28", "PB15", "bidi", "right"),
                Pin("29", "PA8", "bidi", "right"),
                Pin("30", "PA9", "bidi", "right"),
                Pin("31", "PA10", "bidi", "right"),
                Pin("32", "PA11", "bidi", "right"),
                Pin("33", "PA12", "bidi", "right"),
                Pin("34", "PA13/SWDIO", "bidi", "right"),
                Pin("35", "VSS_2", "pwr", "right"),
                Pin("36", "VDD_2", "pwr", "right"),
                Pin("37", "PA14/SWCLK", "bidi", "right"),
                Pin("38", "PA15", "bidi", "right"),
                Pin("39", "PB3", "bidi", "right"),
                Pin("40", "PB4", "bidi", "right"),
                Pin("41", "PB5", "bidi", "right"),
                Pin("42", "PB6", "bidi", "right"),
                Pin("43", "PB7", "bidi", "right"),
                Pin("44", "BOOT0", "in", "right"),
                Pin("45", "PB8", "bidi", "right"),
                Pin("46", "PB9", "bidi", "right"),
                Pin("47", "VSS_3", "pwr", "right"),
                Pin("48", "VDD_3", "pwr", "right"),
            ],
        )
    )

    out_path = "../gridnet_parts.kicad_sym"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        for p in parts:
            f.write(p)
            f.write("\n")
        f.write(FOOTER)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
