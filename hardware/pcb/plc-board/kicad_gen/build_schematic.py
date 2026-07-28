"""Build hardware/pcb/plc-board/plc-board.kicad_sch -- the PLC/Power Board
(BOM's "Board 1", the PLC Adapter's PCB) schematic, wired per the net plan
in this directory's README.md.

Scope (see README.md's "What this covers, and what it deliberately
doesn't" for the reasoning): mains protection (TVS + MOV), the AC-DC
supply (HLK-5M05), the Terminal power inlet and source ORing, the
supercapacitor hold-up, the 5V->12V boost feeding the ST7580's VCC, the
ST7580's fully-datasheet-specified digital/control/clock/ground pins and
its output current limit, the ESP32-C3-MINI-1 host, and the status LEDs
+ connectors.

The inverter that earlier revisions deferred is not deferred any more --
it is gone. docs/plc-adapter-power.md has the reasoning: the 24V
injection sits well outside EN 50065-1's limits, and its other job
(powering neighbouring adapters) is now done by the Terminal over a
cable. What is left of it is a properly-supplied ST7580 power amplifier.

Still deliberately unbuilt: the PA output network and line coupling.
That now waits on one specific document (ST's AN4068 reference coupling
circuit) rather than on open design questions.
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
        ref="J1",
    )
    sch.pwr_flag(mains, "1", "AC_L")  # externally sourced from the wall outlet
    sch.pwr_flag(mains, "2", "AC_N")

    tvs = sch.place("Device:D_TVS", "D", "P6KE250CA", 55, 25, footprint_override="Diode_THT:D_5W_P10.16mm_Horizontal", ref="D1")
    sch.net(tvs, "1", "AC_L")
    sch.net(tvs, "2", "AC_N")

    # S20K275: "S20" = 20mm disc; closest real KiCad footprint is the
    # 21.5mm/10mm-pitch one (no exact-20mm option in the bundled library).
    mov = sch.place("Device:Varistor", "RV", "S20K275", 55, 40, footprint_override="Varistor:RV_Disc_D21.5mm_W7.5mm_P10mm", ref="RV1")
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
        ref="U1",
    )
    sch.net(psu, "1", "AC_L")
    sch.net(psu, "2", "AC_N")
    sch.net(psu, "4", "PSU_5V")
    sch.power_pin(psu, "3", "GND")
    psu_cout = sch.place("Device:C", "C", "220uF", 90, 45, footprint_override="Capacitor_THT:CP_Radial_D8.0mm_P3.50mm", ref="C1")
    sch.net(psu_cout, "1", "PSU_5V")
    sch.power_pin(psu_cout, "2", "GND")

    # ------------------------------------------------------------------ #
    # Terminal power inlet + source ORing (see docs/plc-adapter-power.md)
    #
    # This adapter has no battery. When the grid fails the HLK-5M05 stops,
    # so the Terminal supplies 5V over a detachable USB-C cable instead --
    # see that document for why the energy store lives in the Terminal
    # rather than here, and what that costs.
    #
    # The two sources are ORed with Schottky diodes rather than an
    # ideal-diode controller, consistent with this BOM's price point. The
    # ~0.3V drop leaves ~4.7V, above the boost's input minimum and still
    # enough headroom for the AMS1117 at the ~100mA it supplies.
    #
    # Safety note: this connector sits on the HLK-5M05's isolated secondary,
    # which is also this board's GND. The user handles this cable, so the
    # isolation barrier docs/electrical-safety.md calls non-negotiable is
    # what stands between them and the mains side.
    # ------------------------------------------------------------------ #

    usb = sch.place(
        "Connector:USB_C_Receptacle_USB2.0_14P", "J", "TERMINAL_5V_IN", 30, 60,
        footprint_override="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        ref="J4",
    )
    sch.pwr_flag(usb, "A4", "USB_5V")  # externally sourced -- the Terminal's +5V rail
    for p in ("B4", "A9", "B9"):
        sch.net(usb, p, "USB_5V")
    for p in ("A1", "B1", "A12", "B12", "S1"):
        sch.power_pin(usb, p, "GND")
    # Fixed 5.1k "UFP sink" strapping, same as the Terminal's own inlet.
    # This port only ever takes power; there is no USB data on this board.
    cc1 = sch.place("Device:R", "R", "5.1k", 20, 75, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R9")
    sch.net(usb, "A5", "USB_CC1")
    sch.net(cc1, "1", "USB_CC1")
    sch.power_pin(cc1, "2", "GND")
    cc2 = sch.place("Device:R", "R", "5.1k", 40, 75, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R10")
    sch.net(usb, "B5", "USB_CC2")
    sch.net(cc2, "1", "USB_CC2")
    sch.power_pin(cc2, "2", "GND")
    for p in ("A6", "B6", "A7", "B7"):
        sch.no_connect(usb, p)  # D+/D- -- power-only inlet, no USB data on this board

    or_psu = sch.place("Device:D_Schottky", "D", "SS34", 70, 60, footprint_override="Diode_SMD:D_SMA", ref="D5")
    sch.net(or_psu, "1", "PSU_5V")
    sch.net(or_psu, "2", "+5V")
    or_usb = sch.place("Device:D_Schottky", "D", "SS34", 70, 70, footprint_override="Diode_SMD:D_SMA", ref="D6")
    sch.net(or_usb, "1", "USB_5V")
    sch.net(or_usb, "2", "+5V")
    # +5V used to be driven straight off the HLK-5M05's output pin. Now both
    # sources reach it through the ORing diodes, which are passive, so no
    # power-output pin sits on the net any more even though it is genuinely
    # driven from two directions. Flagged rather than left as a false error.
    sch.bare_pwr_flag(85, 80, "+5V")

    # ------------------------------------------------------------------ #
    # Supercapacitor hold-up
    #
    # Its job is not to keep the adapter running -- it is to keep the
    # ESP32-C3 alive long enough to tell the Terminal over Wi-Fi that mains
    # has gone, so the Terminal can put "connect the adapter cable" on
    # screen. Usable energy between the 5V rail and the boost's ~3.5V input
    # minimum is 1/2*C*(5^2 - 3.5^2) = 6.4J per farad; a couple of seconds
    # of Wi-Fi activity is well under 1J.
    #
    # It charges through R11 (~500mA inrush limit at 5V) and discharges into
    # the rail through D7, so the resistor is not in the discharge path.
    # ------------------------------------------------------------------ #

    sc_r = sch.place("Device:R", "R", "10R", 100, 60, footprint_override="Resistor_SMD:R_1206_3216Metric", ref="R11")
    sch.net(sc_r, "1", "+5V")
    sch.net(sc_r, "2", "SUPERCAP")
    supercap = sch.place(
        "Device:C_Polarized", "C", "1F 5.5V", 100, 72,
        footprint_override="Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
        ref="C7",
    )
    sch.net(supercap, "1", "SUPERCAP")
    sch.power_pin(supercap, "2", "GND")
    sc_d = sch.place("Device:D_Schottky", "D", "SS34", 115, 60, footprint_override="Diode_SMD:D_SMA", ref="D7")
    sch.net(sc_d, "1", "SUPERCAP")
    sch.net(sc_d, "2", "+5V")

    # ------------------------------------------------------------------ #
    # 5V -> 12V boost for the ST7580's VCC rail
    #
    # The ST7580 needs 8-18V on VCC for its power amplifier and internal
    # analog regulator (datasheet DocID022644 Rev 2: 8/13/18 V min/typ/max,
    # UVLO 6.1-7.5V). 12V sits mid-window and well clear of the lockout.
    #
    # MT3608 is a real KiCad library part, not a custom symbol. Values come
    # from its own datasheet: VREF = 0.6V and VOUT = VREF*(1 + R1/R2), so 12V
    # needs R1/R2 = 19 -- 19.1k/1k gives 12.06V. Recommended inductor is
    # 4.7-22uH with 22uF ceramic in and out. It is an asynchronous boost, so
    # the rectifier (D8) is external.
    # ------------------------------------------------------------------ #

    boost = sch.place("Regulator_Switching:MT3608", "U", "MT3608", 140, 60, ref="U5")
    sch.power_pin(boost, "5", "+5V")   # IN
    sch.power_pin(boost, "2", "GND")   # GND
    sch.net(boost, "4", "+5V")         # EN -- tied to VIN for automatic startup, per the datasheet pin table
    sch.net(boost, "1", "BOOST_SW")
    boost_l = sch.place("Device:L", "L", "22uH", 130, 50, footprint_override="Inductor_SMD:L_6.3x6.3_H3", ref="L1")
    sch.net(boost_l, "1", "+5V")
    sch.net(boost_l, "2", "BOOST_SW")
    boost_d = sch.place("Device:D_Schottky", "D", "SS34", 155, 50, footprint_override="Diode_SMD:D_SMA", ref="D8")
    sch.net(boost_d, "1", "BOOST_SW")
    sch.net(boost_d, "2", "+12V")
    # +12V reaches the rail through D8, a passive part, so nothing on this
    # sheet looks like a power *output* to ERC even though the rail is
    # genuinely driven. Flagged rather than left as a false error.
    sch.bare_pwr_flag(160, 40, "+12V")
    boost_cin = sch.place("Device:C", "C", "22uF", 125, 70, footprint_override="Capacitor_SMD:C_1206_3216Metric", ref="C8")
    sch.net(boost_cin, "1", "+5V")
    sch.power_pin(boost_cin, "2", "GND")
    boost_cout = sch.place("Device:C", "C", "22uF", 170, 65, footprint_override="Capacitor_SMD:C_1206_3216Metric", ref="C9")
    sch.net(boost_cout, "1", "+12V")
    sch.power_pin(boost_cout, "2", "GND")
    # Bulk on the 12V rail rides transmit bursts so the supply is sized for
    # average draw rather than the PA's peak -- see docs/plc-adapter-power.md.
    boost_bulk = sch.place(
        "Device:C", "C", "100uF", 180, 65,
        footprint_override="Capacitor_THT:CP_Radial_D6.3mm_P2.50mm", ref="C10",
    )
    sch.net(boost_bulk, "1", "+12V")
    sch.power_pin(boost_bulk, "2", "GND")
    fb_top = sch.place("Device:R", "R", "19.1k", 165, 75, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R12")
    sch.net(fb_top, "1", "+12V")
    sch.net(fb_top, "2", "BOOST_FB")
    fb_bot = sch.place("Device:R", "R", "1k", 165, 85, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R13")
    sch.net(fb_bot, "1", "BOOST_FB")
    sch.power_pin(fb_bot, "2", "GND")
    sch.net(boost, "3", "BOOST_FB")   # FB

    # ------------------------------------------------------------------ #
    # Status LEDs (Power / PLC / Wi-Fi, per hardware/bom.md's PLC Adapter
    # line items)
    # ------------------------------------------------------------------ #

    pwr_led = sch.place("Device:LED", "D", "LED (green)", 120, 25, footprint_override="LED_THT:LED_D5.0mm", ref="D2")
    pwr_led_r = sch.place("Device:R", "R", "1k", 120, 35, footprint_override="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", ref="R1")
    sch.power_pin(pwr_led, "1", "+5V")
    sch.net(pwr_led, "2", "PWR_LED_R")
    sch.net(pwr_led_r, "1", "PWR_LED_R")
    sch.power_pin(pwr_led_r, "2", "GND")

    plc_led = sch.place("Device:LED", "D", "LED (amber)", 140, 25, footprint_override="LED_THT:LED_D5.0mm", ref="D3")
    plc_led_r = sch.place("Device:R", "R", "1k", 140, 35, footprint_override="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", ref="R2")
    sch.net(plc_led_r, "1", "PLC_LED")
    sch.net(plc_led, "2", "PLC_LED")
    sch.power_pin(plc_led, "1", "+5V")
    sch.power_pin(plc_led_r, "2", "GND")

    # Wi-Fi LED is GPIO-driven (ESP32 IO8), not hardwired, so firmware can
    # blink it for real Wi-Fi status -- unlike Power (always-on) and PLC
    # (driven directly by the ST7580's own activity pin).
    wifi_led = sch.place("Device:LED", "D", "LED (blue)", 160, 25, footprint_override="LED_THT:LED_D5.0mm", ref="D4")
    wifi_led_r = sch.place("Device:R", "R", "330R", 160, 35, footprint_override="Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", ref="R3")
    sch.net(wifi_led_r, "1", "WIFI_LED_CTRL")
    sch.net(wifi_led, "2", "WIFI_LED_CTRL")
    sch.power_pin(wifi_led, "1", "+5V")
    sch.net(wifi_led_r, "2", "WIFI_LED_GPIO")

    # ------------------------------------------------------------------ #
    # ESP32-C3-MINI-1 -- Wi-Fi AP for the Terminal connection, UART host
    # for the ST7580, and GPIO control for the status LEDs
    # ------------------------------------------------------------------ #

    esp = sch.place("gridnet_parts:ESP32-C3-MINI-1", "U", "ESP32-C3-MINI-1", 200, 55, ref="U2")
    sch.net(esp, "3", "+3V3")
    for p in ("1", "2", "11", "14", "36", "37", "38", "39", "40", "41", "42",
              "43", "44", "45", "46", "47", "48", "49", "50", "51", "52", "53"):
        sch.power_pin(esp, p, "GND")
    en_r = sch.place("Device:R", "R", "10k", 185, 40, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R4")
    sch.net(esp, "8", "ESP_EN")
    sch.net(en_r, "1", "ESP_EN")
    sch.net(en_r, "2", "+3V3")
    boot_r = sch.place("Device:R", "R", "10k", 215, 40, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R5")
    sch.net(esp, "23", "ESP_IO9")
    sch.net(boot_r, "1", "ESP_IO9")
    sch.net(boot_r, "2", "+3V3")

    ldo = sch.place("Regulator_Linear:AMS1117-3.3", "U", "AMS1117-3.3", 175, 55, ref="U3")
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
        ref="J2",
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

    st = sch.place("gridnet_parts:ST7580", "U", "ST7580", 300, 90, ref="U4")

    # UART to ESP32
    sch.net(st, "1", "ST_TXD")
    sch.net(st, "2", "ST_RXD")
    sch.net(st, "10", "ST_RESETN")
    sch.net(st, "38", "ST_T_REQ")
    reset_r = sch.place("Device:R", "R", "10k", 270, 60, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R6")
    sch.net(reset_r, "1", "ST_RESETN")
    sch.net(reset_r, "2", "+5V")  # VDDIO-referenced pull-up; VDDIO == +5V on this board

    # UART baud rate select: BR1=1, BR0=1 -> 57600 (Table 3 of the datasheet)
    br1_r = sch.place("Device:R", "R", "10k", 330, 60, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R7")
    sch.net(st, "39", "ST_BR1")
    sch.net(br1_r, "1", "ST_BR1")
    sch.net(br1_r, "2", "+5V")
    br0_r = sch.place("Device:R", "R", "10k", 345, 60, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R8")
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
        ref="J3",
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
    fb1 = sch.place("Device:FerriteBead", "FB", "FB", 340, 100, footprint_override="Inductor_SMD:L_0805_2012Metric", ref="FB1")
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
    vdd_a_c = sch.place("Device:C", "C", "100nF", 280, 110, footprint_override="Capacitor_SMD:C_0603_1608Metric", ref="C2")
    sch.net(st, "11", "ST_VDD_A")
    sch.net(vdd_a_c, "1", "ST_VDD_A")
    sch.power_pin(vdd_a_c, "2", "GND")
    vdd_b_c = sch.place("Device:C", "C", "100nF", 320, 110, footprint_override="Capacitor_SMD:C_0603_1608Metric", ref="C3")
    sch.net(st, "46", "ST_VDD_B")
    sch.net(vdd_b_c, "1", "ST_VDD_B")
    sch.power_pin(vdd_b_c, "2", "GND")
    vdd_reg_c = sch.place("Device:C", "C", "100nF", 300, 115, footprint_override="Capacitor_SMD:C_0603_1608Metric", ref="C4")
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
    fb2 = sch.place("Device:FerriteBead", "FB", "FB", 280, 120, footprint_override="Inductor_SMD:L_0805_2012Metric", ref="FB2")
    sch.net(fb2, "1", "ST_VDD_A")
    sch.net(st, "16", "ST_VDD_PLL")
    sch.net(fb2, "2", "ST_VDD_PLL")
    vdd_pll_c = sch.place("Device:C", "C", "100nF", 290, 125, footprint_override="Capacitor_SMD:C_0603_1608Metric", ref="C5")
    sch.net(vdd_pll_c, "1", "ST_VDD_PLL")
    sch.net(vdd_pll_c, "2", "ST_VSSA")
    sch.bare_pwr_flag(290, 130, "ST_VDD_PLL")  # fed from ST_VDD_A through FB2, same reasoning

    # VCCA: local decoupling to VSSA only, no external drive (internally
    # generated from VCC, which this design doesn't supply -- see below).
    vcca_c = sch.place("Device:C", "C", "1uF", 320, 120, footprint_override="Capacitor_SMD:C_0805_2012Metric", ref="C6")
    sch.net(st, "17", "ST_VCCA")
    sch.net(vcca_c, "1", "ST_VCCA")
    sch.net(vcca_c, "2", "ST_VSSA")
    sch.bare_pwr_flag(320, 125, "ST_VCCA")  # internally generated from VCC, same reasoning

    # 8MHz crystal, XIN/XOUT -- no external load caps needed, both pins
    # have 32pF integrated on-chip (datasheet Section 7).
    xtal = sch.place("Device:Crystal", "Y", "8MHz", 300, 60, footprint_override="Crystal:Crystal_SMD_HC49-SD", ref="Y1")
    sch.net(st, "12", "ST_XIN")
    sch.net(xtal, "1", "ST_XIN")
    sch.net(st, "13", "ST_XOUT")
    sch.net(xtal, "2", "ST_XOUT")

    # VCC (8-18V) now comes from the MT3608 boost above. It powers the power
    # amplifier and generates VCCA internally. Decoupled locally at the pin.
    sch.net(st, "24", "+12V")
    vcc_c = sch.place("Device:C", "C", "100nF", 360, 90, footprint_override="Capacitor_SMD:C_0603_1608Metric", ref="C11")
    sch.net(vcc_c, "1", "+12V")
    sch.power_pin(vcc_c, "2", "GND")

    # Output current limit. The ST7580 mirrors 1/CL_RATIO of the PA output
    # current through RCL to VSS and, once the resulting voltage passes
    # CL_TH, walks TX_GAIN down a step at a time until it is back under
    # (datasheet Section 5.4):
    #
    #     RCL = CL_TH * CL_RATIO / I(PA_OUT) peak     CL_TH = 2.35V, CL_RATIO = 80
    #
    # Checked against the datasheet's own Table 8: 1 A RMS FSK is 1.41 A peak
    # -> 2.35*80/1.41 = 133 ohm, exactly the tabulated value.
    #
    # This design targets a 500 mA RMS ceiling (705 mA peak in FSK) to bound
    # what the Terminal's battery has to supply: 2.35*80/0.705 = 267 -> 270R
    # (E24). It is a hardware backstop, not the operating point -- firmware
    # sets TX_GAIN lower still when running on battery. See
    # docs/plc-adapter-power.md for the energy budget behind that number.
    rcl = sch.place("Device:R", "R", "270R", 360, 140, footprint_override="Resistor_SMD:R_0603_1608Metric", ref="R14")
    sch.net(st, "23", "ST_CL")
    sch.net(rcl, "1", "ST_CL")
    sch.net(rcl, "2", "ST_VSSA")

    # PA output network and line coupling: still deliberately out of scope.
    # What used to block this was four open questions (no VCC rail, no gate
    # driver, no inverter topology, no transformer). Three are now answered
    # -- VCC exists and the inverter is gone, see docs/plc-adapter-power.md.
    # What remains is one specific missing document: ST's AN4068 has the
    # reference coupling circuit and the datasheet does not reproduce it, so
    # the PA output network, the series coupling capacitor and the RX_IN path
    # are still unspecified by any primary source available here. Marked
    # no_connect rather than guessed at, same standard as before.
    #
    # CL_SEL would switch RCL between FSK and PSK, whose crest factors
    # differ. Not used here -- one fixed resistor means the effective RMS
    # ceiling differs slightly between modulations, acceptable for a
    # backstop. It is a digital output, so leaving it open is safe.
    for p in ("18", "19", "20", "21", "22", "26", "36"):
        sch.no_connect(st, p)  # ZC_IN, RX_IN, TX_OUT, PA_IN+/-, PA_OUT, CL_SEL

    return sch


if __name__ == "__main__":
    s = build()
    xml = s.render()
    out_path = f"../{PROJECT}.kicad_sch"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"wrote {out_path}")
