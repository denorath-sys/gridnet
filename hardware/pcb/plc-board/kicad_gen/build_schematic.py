"""Build hardware/pcb/plc-board/plc-board.kicad_sch -- the PLC/Power Board
(BOM's "Board 1", the PLC Adapter's PCB) schematic, wired per the net plan
in this directory's README.md.

Scope of this pass (see README.md's "What this covers, and what it
deliberately doesn't" for the reasoning): mains protection (TVS + MOV),
the AC-DC supply (HLK-5M05), the ST7580's fully-datasheet-specified
digital/control/clock/ground pins, the ESP32-C3-MINI-1 host, and the
status LEDs + connectors. The ST7580's power-amplifier/line-coupling
section (needs an 8-18V VCC rail and a coupling transformer this design
doesn't have yet) and the inverter (needs a gate driver this design
doesn't have yet) are explicitly left unconnected with prominent flags,
not guessed at.
"""

from __future__ import annotations

import schematic
from schematic import Schematic

PROJECT = "plc-board"


def build() -> Schematic:
    lib_text = open("../gridnet_parts.kicad_sym", encoding="utf-8").read()
    sch = Schematic("GRIDNET PLC/Power Board", lib_text, project_name=PROJECT)

    # ------------------------------------------------------------------ #
    # Mains input + protection (Layers 1-2 of docs/electrical-safety.md's
    # three-layer protection circuit -- Layer 3, the relay + optocoupler
    # that isolates the *inverter* from the line, is deferred along with
    # the inverter itself; see README.md)
    # ------------------------------------------------------------------ #

    mains = sch.place(
        "Connector_Generic:Conn_01x02", "J", "MAINS_L_N", 30, 30,
        footprint_override="TerminalBlock:TerminalBlock_bornier-2_P5.08mm",
    )
    sch.pwr_flag(mains, "1", "AC_L")  # externally sourced from the wall outlet
    sch.pwr_flag(mains, "2", "AC_N")

    tvs = sch.place("Device:D_TVS", "D", "P6KE250CA", 55, 25, footprint_override="Diode_THT:D_5W_P10.16mm_Horizontal")
    sch.net(tvs, "1", "AC_L")
    sch.net(tvs, "2", "AC_N")

    # S20K275: "S20" = 20mm disc; closest real KiCad footprint is the
    # 21.5mm/10mm-pitch one (no exact-20mm option in the bundled library).
    mov = sch.place("Device:Varistor", "RV", "S20K275", 55, 40, footprint_override="Varistor:RV_Disc_D21.5mm_W7.5mm_P10mm")
    sch.net(mov, "1", "AC_L")
    sch.net(mov, "2", "AC_N")

    # ------------------------------------------------------------------ #
    # AC-DC supply: HLK-5M05, isolated 230VAC -> 5VDC. -Vout becomes this
    # board's logic ground (GND) -- galvanically separate from AC_L/AC_N,
    # per docs/electrical-safety.md's "no direct electrical connection"
    # requirement (isolation is inside the HLK module itself).
    # ------------------------------------------------------------------ #

    psu = sch.place(
        "Converter_ACDC:HLK-5M05", "U", "HLK-5M05", 90, 30,
        footprint_override="Converter_ACDC:Converter_ACDC_Hi-Link_HLK-5Mxx",
    )
    sch.net(psu, "1", "AC_L")
    sch.net(psu, "2", "AC_N")
    sch.net(psu, "4", "+5V")
    sch.power_pin(psu, "3", "GND")
    psu_cout = sch.place("Device:C", "C", "220uF", 90, 45, footprint_override="Capacitor_THT:CP_Radial_D8.0mm_P3.50mm")
    sch.net(psu_cout, "1", "+5V")
    sch.power_pin(psu_cout, "2", "GND")

    # ------------------------------------------------------------------ #
    # Status LEDs (Power / PLC / Wi-Fi, per hardware/bom.md's PLC Adapter
    # line items)
    # ------------------------------------------------------------------ #

    pwr_led = sch.place("Device:LED", "D", "LED (green)", 120, 25, footprint_override="LED_THT:LED_D5.0mm")
    pwr_led_r = sch.place("Device:R", "R", "1k", 120, 35, footprint_override="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal")
    sch.power_pin(pwr_led, "1", "+5V")
    sch.net(pwr_led, "2", "PWR_LED_R")
    sch.net(pwr_led_r, "1", "PWR_LED_R")
    sch.power_pin(pwr_led_r, "2", "GND")

    plc_led = sch.place("Device:LED", "D", "LED (amber)", 140, 25, footprint_override="LED_THT:LED_D5.0mm")
    plc_led_r = sch.place("Device:R", "R", "1k", 140, 35, footprint_override="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal")
    sch.net(plc_led_r, "1", "PLC_LED")
    sch.net(plc_led, "2", "PLC_LED")
    sch.power_pin(plc_led, "1", "+5V")
    sch.power_pin(plc_led_r, "2", "GND")

    # Wi-Fi LED is GPIO-driven (ESP32 IO8), not hardwired, so firmware can
    # blink it for real Wi-Fi status -- unlike Power (always-on) and PLC
    # (driven directly by the ST7580's own activity pin).
    wifi_led = sch.place("Device:LED", "D", "LED (blue)", 160, 25, footprint_override="LED_THT:LED_D5.0mm")
    wifi_led_r = sch.place("Device:R", "R", "330R", 160, 35, footprint_override="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal")
    sch.net(wifi_led_r, "1", "WIFI_LED_CTRL")
    sch.net(wifi_led, "2", "WIFI_LED_CTRL")
    sch.power_pin(wifi_led, "1", "+5V")
    sch.net(wifi_led_r, "2", "WIFI_LED_GPIO")

    # ------------------------------------------------------------------ #
    # ESP32-C3-MINI-1 -- Wi-Fi AP for the Terminal connection, UART host
    # for the ST7580, and GPIO control for the status LEDs
    # ------------------------------------------------------------------ #

    esp = sch.place("gridnet_parts:ESP32-C3-MINI-1", "U", "ESP32-C3-MINI-1", 200, 55)
    sch.net(esp, "3", "+3V3")
    for p in ("1", "2", "11", "14", "36", "37", "38", "39", "40", "41", "42",
              "43", "44", "45", "46", "47", "48", "49", "50", "51", "52", "53"):
        sch.power_pin(esp, p, "GND")
    en_r = sch.place("Device:R", "R", "10k", 185, 40, footprint_override="Resistor_SMD:R_0603_1608Metric")
    sch.net(esp, "8", "ESP_EN")
    sch.net(en_r, "1", "ESP_EN")
    sch.net(en_r, "2", "+3V3")
    boot_r = sch.place("Device:R", "R", "10k", 215, 40, footprint_override="Resistor_SMD:R_0603_1608Metric")
    sch.net(esp, "23", "ESP_IO9")
    sch.net(boot_r, "1", "ESP_IO9")
    sch.net(boot_r, "2", "+3V3")

    ldo = sch.place("Regulator_Linear:AMS1117-3.3", "U", "AMS1117-3.3", 175, 55)
    sch.power_pin(ldo, "3", "+5V")
    sch.power_pin(ldo, "1", "GND")
    sch.net(ldo, "2", "+3V3")

    # ESP32 <-> ST7580 UART (host side)
    sch.net(esp, "18", "ST_TXD")   # IO4, ESP RX <- ST7580 TXD
    sch.net(esp, "19", "ST_RXD")   # IO5, ESP TX -> ST7580 RXD
    sch.net(esp, "20", "ST_RESETN")  # IO6
    sch.net(esp, "21", "ST_T_REQ")   # IO7

    sch.net(esp, "22", "WIFI_LED_GPIO")  # IO8, sinks current to light WIFI_LED (active-low)
    for p in ("12", "13", "16", "5", "6"):
        sch.no_connect(esp, p)  # IO0/BOOT_SEL, IO1, IO10, IO2, IO3 -- spare GPIOs
    for p in ("26", "27"):
        sch.no_connect(esp, p)  # IO18/USB_D-, IO19/USB_D+ -- no USB connector on this board

    # UART0 (U0RXD/U0TXD) flashing header -- without this or a USB
    # connector, there would be no way to program the ESP32 at all. Minimal
    # 4-pin header (TX/RX/GND/3V3); putting IO9 (BOOT) into download mode
    # for a first flash is done externally (jumper to GND during power-up),
    # same as most bare ESP32 module carrier boards.
    prog = sch.place(
        "Connector_Generic:Conn_01x04", "J", "ESP32_UART0_PROGRAMMING", 200, 20,
        footprint_override="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    )
    sch.net(esp, "31", "ESP_U0TXD")
    sch.net(prog, "1", "ESP_U0TXD")
    sch.net(esp, "30", "ESP_U0RXD")
    sch.net(prog, "2", "ESP_U0RXD")
    sch.power_pin(prog, "3", "GND")
    sch.net(prog, "4", "+3V3")

    # ------------------------------------------------------------------ #
    # ST7580 -- well-specified pins only (digital control, clock, all
    # power/ground rails per the datasheet's own Figure 8/9 scheme). The
    # PA/AFE/line-coupling section (PA_OUT, PA_IN+/-, TX_OUT, RX_IN, CL,
    # CL_SEL, ZC_IN) and VCC itself are deliberately left unconnected --
    # see README.md's "What this covers, and what it deliberately doesn't".
    # ------------------------------------------------------------------ #

    st = sch.place("gridnet_parts:ST7580", "U", "ST7580", 300, 90)

    # UART to ESP32
    sch.net(st, "1", "ST_TXD")
    sch.net(st, "2", "ST_RXD")
    sch.net(st, "10", "ST_RESETN")
    sch.net(st, "38", "ST_T_REQ")
    reset_r = sch.place("Device:R", "R", "10k", 270, 60, footprint_override="Resistor_SMD:R_0603_1608Metric")
    sch.net(reset_r, "1", "ST_RESETN")
    sch.net(reset_r, "2", "+5V")  # VDDIO-referenced pull-up; VDDIO == +5V on this board

    # UART baud rate select: BR1=1, BR0=1 -> 57600 (Table 3 of the datasheet)
    br1_r = sch.place("Device:R", "R", "10k", 330, 60, footprint_override="Resistor_SMD:R_0603_1608Metric")
    sch.net(st, "39", "ST_BR1")
    sch.net(br1_r, "1", "ST_BR1")
    sch.net(br1_r, "2", "+5V")
    br0_r = sch.place("Device:R", "R", "10k", 345, 60, footprint_override="Resistor_SMD:R_0603_1608Metric")
    sch.net(st, "40", "ST_BR0")
    sch.net(br0_r, "1", "ST_BR0")
    sch.net(br0_r, "2", "+5V")

    # PL_TX_ON drives the PLC status LED directly (High-Z reset state,
    # digital output, matches the LED's forward current at 5V through 1k)
    sch.net(st, "41", "PLC_LED")
    sch.no_connect(st, "37")  # PL_RX_ON -- one PLC activity signal (TX) is enough, see README.md

    # JTAG debug header, mirroring the Main Board's SWD header pattern
    jtag = sch.place(
        "Connector_Generic:Conn_01x05", "J", "ST7580_JTAG_DEBUG", 300, 140,
        footprint_override="Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
    )
    sch.net(jtag, "1", "+5V")
    sch.net(st, "4", "ST_TRSTN")
    sch.net(jtag, "2", "ST_TRSTN")
    sch.net(st, "5", "ST_TMS")
    sch.net(jtag, "3", "ST_TMS")
    sch.net(st, "7", "ST_TCK")
    sch.net(jtag, "4", "ST_TCK")
    sch.net(st, "9", "ST_TDI")
    sch.net(jtag, "5", "ST_TDI")
    sch.net(st, "8", "ST_TDO")
    sch.no_connect(st, "8")  # TDO left off the 5-pin header (debug-in only); see README.md

    # Reserved pins, per the datasheet's own pin table
    for p in ("31", "42", "43", "44", "48"):
        sch.net(st, p, "+5V")  # "pull up to VDDIO" -- tied directly, same net either way
    sch.net(st, "47", "+5V")  # "connect to VDDIO"
    for p in ("29", "30", "32"):
        sch.no_connect(st, p)  # NC

    # Power/ground scheme -- Figure 8 (supply structure) + Figure 9
    # (ground scheme) of the datasheet, reproduced exactly.
    for p in ("3", "28", "34"):
        sch.net(st, p, "+5V")  # VDDIO x3
    for p in ("6", "14", "33", "45"):
        sch.power_pin(st, p, "GND")  # GND x4 (digital ground)

    # VSSA/VSS/exposed-pad analog-ground island, bridged to digital GND
    # through a ferrite bead (Figure 9) rather than tied directly.
    sch.net(st, "15", "ST_VSSA")
    sch.net(st, "35", "ST_VSSA")
    sch.net(st, "25", "ST_VSSA")  # VSS
    sch.net(st, "49", "ST_VSSA")  # exposed pad
    fb1 = sch.place("Device:FerriteBead", "FB", "FB", 340, 100, footprint_override="Inductor_SMD:L_0805_2012Metric")
    sch.net(fb1, "1", "ST_VSSA")
    sch.power_pin(fb1, "2", "GND")
    # ST_VSSA is a real ground (bridged to GND above), just not via a power
    # symbol ERC recognizes on this net directly -- flagged so ERC doesn't
    # read ST7580's own analog-ground pins as "undriven".
    sch.bare_pwr_flag(350, 95, "ST_VSSA")

    # VDD / VDD_REG_1V8 -- internally generated from VDDIO, each pin is a
    # local filter tap only ("external connections between all VDD pins
    # are not required" -- datasheet Section 6). Three independent nets,
    # each with its own decoupling cap, exactly per that section.
    vdd_a_c = sch.place("Device:C", "C", "100nF", 280, 110, footprint_override="Capacitor_SMD:C_0603_1608Metric")
    sch.net(st, "11", "ST_VDD_A")
    sch.net(vdd_a_c, "1", "ST_VDD_A")
    sch.power_pin(vdd_a_c, "2", "GND")
    vdd_b_c = sch.place("Device:C", "C", "100nF", 320, 110, footprint_override="Capacitor_SMD:C_0603_1608Metric")
    sch.net(st, "46", "ST_VDD_B")
    sch.net(vdd_b_c, "1", "ST_VDD_B")
    sch.power_pin(vdd_b_c, "2", "GND")
    vdd_reg_c = sch.place("Device:C", "C", "100nF", 300, 115, footprint_override="Capacitor_SMD:C_0603_1608Metric")
    sch.net(st, "27", "ST_VDD_REG_1V8")
    sch.net(vdd_reg_c, "1", "ST_VDD_REG_1V8")
    sch.power_pin(vdd_reg_c, "2", "GND")
    # ST_VDD_A/B/REG_1V8 are all fed by ST7580's own internal 1.8V LDO (from
    # VDDIO) -- "not designed to supply external circuitry... accessible
    # for filtering purposes only" (datasheet Section 6). Flagged so ERC
    # doesn't read these internally-generated rails as undriven.
    sch.bare_pwr_flag(280, 105, "ST_VDD_A")
    sch.bare_pwr_flag(320, 105, "ST_VDD_B")
    sch.bare_pwr_flag(300, 105, "ST_VDD_REG_1V8")

    # VDD_PLL: ferrite bead from VDD (pin 11's local rail) + its own
    # decoupling cap referenced to VSSA (both per Figure 8).
    fb2 = sch.place("Device:FerriteBead", "FB", "FB", 280, 120, footprint_override="Inductor_SMD:L_0805_2012Metric")
    sch.net(fb2, "1", "ST_VDD_A")
    sch.net(st, "16", "ST_VDD_PLL")
    sch.net(fb2, "2", "ST_VDD_PLL")
    vdd_pll_c = sch.place("Device:C", "C", "100nF", 290, 125, footprint_override="Capacitor_SMD:C_0603_1608Metric")
    sch.net(vdd_pll_c, "1", "ST_VDD_PLL")
    sch.net(vdd_pll_c, "2", "ST_VSSA")
    sch.bare_pwr_flag(290, 130, "ST_VDD_PLL")  # fed from ST_VDD_A through FB2, same reasoning

    # VCCA: local decoupling to VSSA only, no external drive (internally
    # generated from VCC, which this design doesn't supply -- see below).
    vcca_c = sch.place("Device:C", "C", "1uF", 320, 120, footprint_override="Capacitor_SMD:C_0805_2012Metric")
    sch.net(st, "17", "ST_VCCA")
    sch.net(vcca_c, "1", "ST_VCCA")
    sch.net(vcca_c, "2", "ST_VSSA")
    sch.bare_pwr_flag(320, 125, "ST_VCCA")  # internally generated from VCC, same reasoning

    # 8MHz crystal, XIN/XOUT -- no external load caps needed, both pins
    # have 32pF integrated on-chip (datasheet Section 7).
    xtal = sch.place("Device:Crystal", "Y", "8MHz", 300, 60, footprint_override="Crystal:Crystal_SMD_HC49-SD")
    sch.net(st, "12", "ST_XIN")
    sch.net(xtal, "1", "ST_XIN")
    sch.net(st, "13", "ST_XOUT")
    sch.net(xtal, "2", "ST_XOUT")

    # VCC (8-18V, powers the PA and generates VCCA internally) has no
    # source on this board yet -- flagged, not guessed at. See README.md.
    sch.pwr_flag(st, "24", "VCC_8-18V_NOT_SUPPLIED")

    # PA/AFE/line-coupling section: deliberately out of scope this pass
    # (needs VCC above, plus the coupling transformer hardware/bom.md
    # already flags as unconfirmed). Marked no_connect, not wired to
    # anything, so ERC's pin_not_connected check reflects "deferred by
    # design" rather than "might be a wiring bug".
    for p in ("18", "19", "20", "21", "22", "23", "26", "36"):
        sch.no_connect(st, p)  # ZC_IN, RX_IN, TX_OUT, PA_IN+/-, CL, PA_OUT, CL_SEL

    return sch


if __name__ == "__main__":
    s = build()
    xml = s.render()
    out_path = f"../{PROJECT}.kicad_sch"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"wrote {out_path}")
