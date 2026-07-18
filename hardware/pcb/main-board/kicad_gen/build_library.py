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
            description="Microchip 1Mbit SPI serial SRAM, SOIC-8",
            datasheet="https://ww1.microchip.com/downloads/en/DeviceDoc/20005142C.pdf",
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
            description="Boost converter + Li-ion charge/battery management IC (common power-bank IC) -- LOW CONFIDENCE pinout, functional pin names only, cross-check every pin against a real IP5306 datasheet before layout",
            pins=[
                Pin("1", "VIN", "pwr", "left"),  # 5V charge input
                Pin("2", "BAT", "pwr", "left"),
                Pin("3", "GND", "pwr", "left"),
                Pin("4", "KEY", "in", "left"),  # push-button control
                Pin("5", "VOUT", "pwr_out", "right"),  # 5V boost output
                Pin("6", "GND", "pwr", "right"),
                Pin("7", "LED1", "out", "right"),
                Pin("8", "LED2", "out", "right"),
            ],
        )
    )

    parts.append(
        build_symbol(
            name="ESP32-C3-MINI-1U",
            reference="U",
            footprint="RF_Module:ESP32-C3-MINI-1",
            description="Espressif Wi-Fi/BLE module, U.FL antenna variant -- MODERATE CONFIDENCE: pin functions are right, exact castellated-pad NUMBERS need verification against Espressif's ESP32-C3-MINI-1(U) datasheet before layout",
            datasheet="https://www.espressif.com/sites/default/files/documentation/esp32-c3-mini-1_datasheet_en.pdf",
            pins=[
                Pin("1", "GND", "pwr", "left"),
                Pin("2", "3V3", "pwr", "left"),
                Pin("3", "EN", "in", "left"),
                Pin("4", "IO0/BOOT_SEL", "bidi", "left"),
                Pin("5", "IO1", "bidi", "left"),
                Pin("6", "IO2", "bidi", "left"),
                Pin("7", "IO3", "bidi", "left"),
                Pin("8", "IO4", "bidi", "left"),
                Pin("9", "IO5", "bidi", "left"),
                Pin("10", "IO6", "bidi", "left"),
                Pin("11", "IO7", "bidi", "left"),
                Pin("12", "IO8", "bidi", "right"),
                Pin("13", "IO9/BOOT", "bidi", "right"),
                Pin("14", "IO10", "bidi", "right"),
                Pin("15", "IO18/USB_D-", "bidi", "right"),
                Pin("16", "IO19/USB_D+", "bidi", "right"),
                Pin("17", "U0RXD", "in", "right"),
                Pin("18", "U0TXD", "out", "right"),
                Pin("19", "GND", "pwr", "right"),
                Pin("ANT", "ANT", "pas", "right"),  # U.FL connector -- not a numbered castellated pad
            ],
        )
    )

    parts.append(
        build_symbol(
            name="GD32VF103CCT6",
            reference="U",
            footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",
            description="GigaDevice RISC-V MCU, LQFP48, 256KB Flash/32KB RAM -- MODERATE CONFIDENCE: pin arrangement follows the STM32F103C8/CB-compatible LQFP48 pinout GD32VF103 is documented to mirror; verify against the real GD32VF103xx datasheet before layout, especially around BOOT0/BOOT1 and the VDD/VSS pin groups",
            datasheet="https://www.gigadevice.com/microcontroller/gd32vf103cbt6/",
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
                Pin("14", "VSS_1", "pwr", "left"),
                Pin("15", "VDD_1", "pwr", "left"),
                Pin("16", "PA4", "bidi", "left"),
                Pin("17", "PA5", "bidi", "left"),
                Pin("18", "PA6", "bidi", "left"),
                Pin("19", "PA7", "bidi", "left"),
                Pin("20", "PB0", "bidi", "left"),
                Pin("21", "PB1", "bidi", "left"),
                Pin("22", "PB2/BOOT1", "bidi", "left"),
                Pin("23", "PB10", "bidi", "left"),
                Pin("24", "PB11", "bidi", "left"),
                Pin("25", "VSS_2", "pwr", "right"),
                Pin("26", "VDD_2", "pwr", "right"),
                Pin("27", "PB12", "bidi", "right"),
                Pin("28", "PB13", "bidi", "right"),
                Pin("29", "PB14", "bidi", "right"),
                Pin("30", "PB15", "bidi", "right"),
                Pin("31", "PA8", "bidi", "right"),
                Pin("32", "PA9", "bidi", "right"),
                Pin("33", "PA10", "bidi", "right"),
                Pin("34", "PA11", "bidi", "right"),
                Pin("35", "PA12", "bidi", "right"),
                Pin("36", "PA13/SWDIO", "bidi", "right"),
                Pin("37", "VSS_3", "pwr", "right"),
                Pin("38", "VDD_3", "pwr", "right"),
                Pin("39", "PA14/SWCLK", "bidi", "right"),
                Pin("40", "PA15", "bidi", "right"),
                Pin("41", "PB3", "bidi", "right"),
                Pin("42", "PB4", "bidi", "right"),
                Pin("43", "PB5", "bidi", "right"),
                Pin("44", "PB6", "bidi", "right"),
                Pin("45", "PB7", "bidi", "right"),
                Pin("46", "BOOT0", "in", "right"),
                Pin("47", "PB8", "bidi", "right"),
                Pin("48", "PB9", "bidi", "right"),
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
