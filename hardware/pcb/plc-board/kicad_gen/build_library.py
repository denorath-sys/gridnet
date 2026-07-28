"""Assemble hardware/pcb/plc-board/gridnet_parts.kicad_sym -- the
project-local symbol library for the PLC/Power Board (BOM's "Board 1",
which is the PLC Adapter's own PCB -- see README.md for why those are the
same board).

Same two-part strategy as the Main Board library (see that directory's
build_library.py): real symbol blocks copied programmatically from KiCad's
own bundled libraries where a real or pin-compatible match exists, and
custom-built generic-rectangle symbols only for the three parts that don't:
ST7580, ESP32-C3-MINI-1 and the Wuerth 750510231 coupling transformer. All
three were checked pin-by-pin against their primary-source datasheets before
being written here -- see README.md. The transformer is custom for a
different reason than the other two: KiCad has a perfectly good 1P_1S
transformer symbol, but it numbers its pins 1/2 and 3/4 and the real part's
terminals are 1/4 and 10/7.
"""

from __future__ import annotations

from make_symbol import Pin, build_symbol

HEADER = """(kicad_symbol_lib
\t(version 20241209)
\t(generator "gridnet_build_library")
\t(generator_version "9.0")
"""
FOOTER = ")\n"


def main() -> None:
    parts = []

    # --- Custom-built symbols (verified against primary-source datasheets) #

    parts.append(
        build_symbol(
            name="ST7580",
            reference="U",
            footprint="Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.1x5.1mm",
            description="STMicroelectronics power line networking system-on-chip (CENELEC 9-148 kHz, FSK/PSK; this design runs it in B+C, see docs/plc-coupling.md), VFQFPN48 -- pinout verified pin-by-pin against the real ST7580 datasheet (DocID022644 Rev 2): Figure 2 pinout diagram + Table 2 pin description for pins 1-48, Figure 8/9 for the power/ground scheme, Section 7 for the crystal spec",
            datasheet="https://www.st.com/resource/en/datasheet/st7580.pdf",
            verified=True,
            pins=[
                Pin("1", "TXD", "out", "left"),
                Pin("2", "RXD", "in", "left"),
                Pin("3", "VDDIO", "pwr", "left"),
                Pin("4", "TRSTN", "in", "left"),
                Pin("5", "TMS", "in", "left"),
                Pin("6", "GND", "pwr", "left"),
                Pin("7", "TCK", "in", "left"),
                Pin("8", "TDO", "out", "left"),
                Pin("9", "TDI", "in", "left"),
                Pin("10", "RESETN", "in", "left"),
                Pin("11", "VDD", "pwr", "left"),
                Pin("12", "XIN", "bidi", "left"),
                Pin("13", "XOUT", "bidi", "left"),
                Pin("14", "GND", "pwr", "left"),
                Pin("15", "VSSA", "pwr", "left"),
                Pin("16", "VDD_PLL", "pwr", "left"),
                Pin("17", "VCCA", "pwr", "left"),
                Pin("18", "ZC_IN", "in", "left"),
                Pin("19", "RX_IN", "in", "left"),
                Pin("20", "TX_OUT", "out", "left"),
                Pin("21", "PA_IN+", "in", "left"),
                Pin("22", "PA_IN-", "in", "left"),
                Pin("23", "CL", "in", "left"),
                Pin("24", "VCC", "pwr", "left"),
                Pin("25", "VSS", "pwr", "right"),
                Pin("26", "PA_OUT", "out", "right"),
                Pin("27", "VDD_REG_1V8", "pwr", "right"),
                Pin("28", "VDDIO", "pwr", "right"),
                Pin("29", "NC", "nc", "right"),
                Pin("30", "NC", "nc", "right"),
                Pin("31", "RESERVED0", "pwr", "right"),  # pull-up to VDDIO
                Pin("32", "NC", "nc", "right"),
                Pin("33", "GND", "pwr", "right"),
                Pin("34", "VDDIO", "pwr", "right"),
                Pin("35", "VSSA", "pwr", "right"),
                Pin("36", "CL_SEL", "out", "right"),
                Pin("37", "PL_RX_ON", "out", "right"),
                Pin("38", "T_REQ", "in", "right"),
                Pin("39", "BR1", "in", "right"),
                Pin("40", "BR0", "in", "right"),
                Pin("41", "PL_TX_ON", "out", "right"),
                Pin("42", "RESERVED1", "in", "right"),  # pull-up to VDDIO
                Pin("43", "RESERVED2", "in", "right"),  # pull-up to VDDIO
                Pin("44", "RESERVED3", "in", "right"),  # pull-up to VDDIO
                Pin("45", "GND", "pwr", "right"),
                Pin("46", "VDD", "pwr", "right"),
                Pin("47", "RESERVED4", "in", "right"),  # connect to VDDIO
                Pin("48", "RESERVED5", "in", "right"),  # pull-up to VDDIO
                # Exposed pad, footprint pad "49" -- electrically VSSA
                # (Figure 9: exposed pad tied to VSSA and VSS).
                Pin("49", "EPAD", "pwr", "right"),
            ],
        )
    )

    parts.append(
        build_symbol(
            name="ESP32-C3-MINI-1",
            reference="U",
            # Real footprint, vendored from Espressif's official KiCad
            # library into ../gridnet_footprints.pretty/ -- see that
            # directory's README.md. Same 53-pad numbering as the Main
            # Board's ESP32-C3-MINI-1U (same datasheet, Table 3-1). Neither
            # variant has an RF pad; this one's antenna is on the module,
            # the -1U's is an on-module W.FL/MHF III jack.
            footprint="gridnet_footprints:ESP32-C3-MINI-1",
            description="Espressif Wi-Fi/BLE module, on-module PCB antenna variant (no external antenna needed) -- pin functions AND pad numbers verified against the real Espressif ESP32-C3-MINI-1/1U datasheet (v2.2) Table 3-1, same pin list as the Main Board's MINI-1U symbol -- neither module brings its radio out to a pad",
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
                Pin("49", "GND", "pwr", "right"),  # 3x3 thermal-pad array, see Main Board's symbol
                Pin("50", "GND", "pwr", "right"),
                Pin("51", "GND", "pwr", "right"),
                Pin("52", "GND", "pwr", "right"),
                Pin("53", "GND", "pwr", "right"),
            ],
        )
    )

    # The PLC line coupling transformer. A custom symbol rather than KiCad's
    # Device:Transformer_1P_1S because that symbol numbers its pins 1/2
    # (primary) and 3/4 (secondary), and the real part's terminals are 1/4
    # and 10/7 -- exactly the kind of pin-number mismatch this project keeps
    # finding on the PCB rather than in the schematic. Verified against
    # Wuerth's own specification sheet for 750510231 (rev 6E, 8/22).
    parts.append(
        build_symbol(
            name="PLC_COUPLING_TRANSFORMER",
            reference="T",
            footprint="gridnet_footprints:Transformer_Wuerth_750510231",
            description=(
                "PLC line coupling transformer, 1:1 +/-1%, Wuerth 750510231 (AN4068's own part, "
                "alternate TDK SRW13EP-X05H002) -- terminals and electrical parameters verified against "
                "Wuerth's specification sheet: primary 1-4, secondary 10-7, inductance 1-4 = 1.00 mH "
                "+35/-25% at 100 kHz, leakage <=1.0 uH, DC resistance <=0.20 ohm per winding, "
                "interwinding capacitance <=30 pF, dielectric 1-10 = 2000 VAC for 1 s. "
                "Meets every line of AN4068 Table 4 except that the 2000 VAC dielectric figure is not "
                "the same test as Table 4's >=4 kV withstanding voltage -- see README.md."
            ),
            datasheet="https://www.we-online.com/components/products/datasheet/750510231.pdf",
            verified=True,
            pins=[
                Pin("1", "PRI_A", "pas", "left"),
                Pin("4", "PRI_B", "pas", "left"),
                Pin("10", "SEC_A", "pas", "right"),
                Pin("7", "SEC_B", "pas", "right"),
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
