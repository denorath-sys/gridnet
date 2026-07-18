"""Build hardware/pcb/main-board/main-board.kicad_sch -- the Main Board
schematic, wired per the net plan in this directory's README.md.

Layout (left to right across an A3 sheet): power tree, MCU + clock/reset,
memory + RTC + microSD, wireless module, then a column of off-board
connectors (display, keyboard, speaker, SWD, battery).
"""

from __future__ import annotations

import schematic
from schematic import Schematic

PROJECT = "main-board"


def build() -> Schematic:
    lib_text = open("../gridnet_parts.kicad_sym", encoding="utf-8").read()
    sch = Schematic("GRIDNET Main Board", lib_text, project_name=PROJECT)

    # ------------------------------------------------------------------ #
    # Power tree: USB-C -> MCP73831 charger -> battery -> IP5306 boost
    # -> two AMS1117-3.3 rails (MCU/logic, RF)
    # ------------------------------------------------------------------ #

    usb = sch.place(
        "Connector:USB_C_Receptacle_USB2.0_14P", "J", "USB-C",
        30, 40, footprint_override="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    )
    sch.pwr_flag(usb, "A4", "VBUS")  # externally-sourced net (whatever's on the other end of the cable)
    sch.bare_pwr_flag(15, 40, "GND")  # GND has no power_out-type pin anywhere in this design; see README.md
    sch.power_pin(usb, "B4", "VBUS")
    sch.power_pin(usb, "A9", "VBUS")
    sch.power_pin(usb, "B9", "VBUS")
    sch.power_pin(usb, "A1", "GND")
    sch.power_pin(usb, "B1", "GND")
    sch.power_pin(usb, "A12", "GND")
    sch.power_pin(usb, "B12", "GND")
    sch.power_pin(usb, "S1", "GND")
    # D+/D- routed to the ESP32-C3 module's native USB (IO18/IO19) for the
    # DFU-over-USB path described in docs/firmware-arch.md -- an assumption,
    # see README.md. Both A- and B-side pins tied together (standard for a
    # USB2.0-only, non-SuperSpeed design): the connector is reversible, so
    # whichever orientation gets plugged in, D+/D- still land on the same net.
    sch.net(usb, "A6", "USB_DP")
    sch.net(usb, "B6", "USB_DP")
    sch.net(usb, "A7", "USB_DN")
    sch.net(usb, "B7", "USB_DN")
    # CC1/CC2: fixed 5.1k to GND each, the standard "this is a UFP sink"
    # strapping so a USB-C charger/host offers 5V.
    cc1 = sch.place("Device:R", "R", "5.1k", 30, 95)
    sch.net(usb, "A5", "CC1")
    sch.net(cc1, "1", "CC1")
    sch.power_pin(cc1, "2", "GND")
    cc2 = sch.place("Device:R", "R", "5.1k", 50, 95)
    sch.net(usb, "B5", "CC2")
    sch.net(cc2, "1", "CC2")
    sch.power_pin(cc2, "2", "GND")

    charger = sch.place("gridnet_parts:MCP73831-2-OT", "U", "MCP73831-2-OT", 70, 45)
    sch.power_pin(charger, "4", "VBUS")
    sch.power_pin(charger, "2", "GND")
    sch.net(charger, "3", "VBATT")
    # 2k sets ~450mA charge current -- confirm against target cell C-rate (see README.md)
    prog_r = sch.place("Device:R", "R", "2k", 70, 65)
    sch.net(charger, "5", "CHG_PROG")
    sch.net(prog_r, "1", "CHG_PROG")
    sch.power_pin(prog_r, "2", "GND")
    chg_led = sch.place("Device:LED", "D", "LED (amber)", 90, 45)
    chg_led_r = sch.place("Device:R", "R", "1k", 90, 55)
    sch.net(charger, "1", "CHG_STAT")
    sch.net(chg_led, "2", "CHG_STAT")
    sch.net(chg_led, "1", "CHG_LED_R")
    sch.net(chg_led_r, "2", "CHG_LED_R")
    sch.power_pin(chg_led_r, "1", "VBUS")

    battery = sch.place(
        "Connector_Generic:Conn_01x02", "J", "BATT_2x18650_PARALLEL", 30, 90,
        footprint_override="Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
    )
    sch.net(battery, "1", "VBATT")  # driven by U1 (MCP73831) pin 3, VBAT (power_out) -- no flag needed
    sch.power_pin(battery, "2", "GND")

    boost = sch.place("gridnet_parts:IP5306", "U", "IP5306", 70, 90)
    sch.net(boost, "2", "VBATT")  # BAT pin -- pin 1 (VIN) unused, see README.md
    sch.power_pin(boost, "3", "GND")
    sch.power_pin(boost, "6", "GND")
    sch.power_pin(boost, "5", "+5V")
    key_sw = sch.place("Switch:SW_Push", "SW", "PWR_KEY", 90, 90)
    sch.net(boost, "4", "PWR_KEY")
    sch.net(key_sw, "1", "PWR_KEY")
    sch.power_pin(key_sw, "2", "GND")
    batt_led1 = sch.place("Device:LED", "D", "LED (amber)", 95, 100)
    sch.net(boost, "7", "BATT_LED1")
    sch.net(batt_led1, "2", "BATT_LED1")
    batt_led1_r = sch.place("Device:R", "R", "1k", 95, 110)
    sch.net(batt_led1, "1", "BATT_LED1_R")
    sch.net(batt_led1_r, "2", "BATT_LED1_R")
    sch.power_pin(batt_led1_r, "1", "+5V")

    ldo_mcu = sch.place("gridnet_parts:AMS1117-3.3", "U", "AMS1117-3.3", 120, 55)
    sch.power_pin(ldo_mcu, "3", "+5V")
    sch.power_pin(ldo_mcu, "1", "GND")
    sch.net(ldo_mcu, "2", "+3V3_MCU")

    ldo_rf = sch.place("gridnet_parts:AMS1117-3.3", "U", "AMS1117-3.3", 120, 90)
    sch.power_pin(ldo_rf, "3", "+5V")
    sch.power_pin(ldo_rf, "1", "GND")
    sch.net(ldo_rf, "2", "+3V3_RF")

    # ------------------------------------------------------------------ #
    # MCU: crystal, reset, boot straps, SWD header
    # ------------------------------------------------------------------ #

    mcu = sch.place("gridnet_parts:GD32VF103CCT6", "U", "GD32VF103CCT6", 190, 90)
    sch.net(mcu, "15", "+3V3_MCU")
    sch.net(mcu, "26", "+3V3_MCU")
    sch.net(mcu, "38", "+3V3_MCU")
    sch.net(mcu, "9", "+3V3_MCU")  # VDDA
    sch.power_pin(mcu, "14", "GND")
    sch.power_pin(mcu, "25", "GND")
    sch.power_pin(mcu, "37", "GND")
    sch.power_pin(mcu, "8", "GND")  # VSSA
    sch.power_pin(mcu, "1", "GND")  # VBAT -- no separate RTC coin cell on the MCU itself; tied to main rail

    xtal = sch.place("Device:Crystal", "Y", "8MHz", 165, 115)
    sch.net(mcu, "5", "OSC_IN")
    sch.net(mcu, "6", "OSC_OUT")
    sch.net(xtal, "1", "OSC_IN")
    sch.net(xtal, "2", "OSC_OUT")
    xtal_c1 = sch.place("Device:C", "C", "20pF", 155, 115)
    xtal_c2 = sch.place("Device:C", "C", "20pF", 175, 115)
    sch.net(xtal_c1, "1", "OSC_IN")
    sch.power_pin(xtal_c1, "2", "GND")
    sch.net(xtal_c2, "1", "OSC_OUT")
    sch.power_pin(xtal_c2, "2", "GND")

    nrst_r = sch.place("Device:R", "R", "10k", 165, 60)
    sch.net(mcu, "7", "NRST")
    sch.net(nrst_r, "1", "NRST")
    sch.net(nrst_r, "2", "+3V3_MCU")
    nrst_sw = sch.place("Switch:SW_Push", "SW", "RESET", 175, 60)
    sch.net(nrst_sw, "1", "NRST")
    sch.power_pin(nrst_sw, "2", "GND")

    boot0_r = sch.place("Device:R", "R", "10k", 222, 55)
    sch.net(mcu, "46", "BOOT0")
    sch.net(boot0_r, "1", "BOOT0")
    sch.power_pin(boot0_r, "2", "GND")
    boot0_jp = sch.place(
        "Connector_Generic:Conn_01x02", "J", "BOOT0_OVERRIDE_JUMPER", 237, 55,
        footprint_override="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    )
    sch.net(boot0_jp, "1", "BOOT0")
    sch.net(boot0_jp, "2", "+3V3_MCU")

    boot1_r = sch.place("Device:R", "R", "10k", 222, 80)
    sch.net(mcu, "22", "BOOT1")  # PB2/BOOT1
    sch.net(boot1_r, "1", "BOOT1")
    sch.power_pin(boot1_r, "2", "GND")

    swd = sch.place(
        "Connector_Generic:Conn_01x04", "J", "SWD_DEBUG", 222, 105,
        footprint_override="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    )
    sch.net(swd, "1", "+3V3_MCU")
    sch.net(swd, "2", "SWDIO")
    sch.net(swd, "3", "SWCLK")
    sch.power_pin(swd, "4", "GND")
    sch.net(mcu, "36", "SWDIO")  # PA13
    sch.net(mcu, "39", "SWCLK")  # PA14

    # ------------------------------------------------------------------ #
    # Memory (SPI1: PA5=SCK, PA6=MISO, PA7=MOSI) + RTC (I2C1: PB6=SCL, PB7=SDA)
    # ------------------------------------------------------------------ #

    sch.net(mcu, "17", "SPI1_SCK")   # PA5
    sch.net(mcu, "18", "SPI1_MISO")  # PA6
    sch.net(mcu, "19", "SPI1_MOSI")  # PA7
    sch.net(mcu, "10", "FLASH_CS")   # PA0
    sch.net(mcu, "11", "SRAM_CS")    # PA1
    sch.net(mcu, "12", "SD_CS")      # PA2

    flash = sch.place("gridnet_parts:W25Q64JVSSIQ", "U", "W25Q64JVSSIQ", 260, 60)
    sch.net(flash, "8", "+3V3_MCU")
    sch.power_pin(flash, "4", "GND", stub=7.62)
    sch.net(flash, "1", "FLASH_CS")
    sch.net(flash, "6", "SPI1_SCK")
    sch.net(flash, "5", "SPI1_MOSI")
    sch.net(flash, "2", "SPI1_MISO")
    sch.net(flash, "3", "+3V3_MCU")  # ~WP -- tied inactive (not used)
    sch.net(flash, "7", "+3V3_MCU")  # ~HOLD -- tied inactive (not used)

    sram = sch.place("gridnet_parts:23LC1024", "U", "23LC1024", 260, 90)
    sch.net(sram, "8", "+3V3_MCU")
    sch.power_pin(sram, "4", "GND", stub=7.62)
    sch.net(sram, "1", "SRAM_CS")
    sch.net(sram, "6", "SPI1_SCK")
    sch.net(sram, "5", "SPI1_MOSI")
    sch.net(sram, "2", "SPI1_MISO")
    sch.net(sram, "3", "+3V3_MCU")  # ~WP
    sch.net(sram, "7", "+3V3_MCU")  # ~HOLD

    sdcard = sch.place(
        "Connector:Micro_SD_Card", "J", "MICROSD", 260, 120,
        footprint_override="Connector_Card:Molex_502031-0810_MicroSD",
    )
    sch.net(sdcard, "4", "+3V3_MCU")
    sch.power_pin(sdcard, "6", "GND")
    sch.net(sdcard, "1", "SD_CS")
    sch.net(sdcard, "5", "SPI1_SCK")
    sch.net(sdcard, "3", "SPI1_MOSI")
    sch.net(sdcard, "7", "SPI1_MISO")

    # Substituted for REV 0.4's DS3231SN -- same SCL/SDA/VBAT/32KHZ/INT-SQW
    # functionality, real verified KiCad library part; see README.md.
    rtc = sch.place("gridnet_parts:DS3231M", "U", "DS3231M", 300, 60)
    sch.net(rtc, "2", "+3V3_MCU")
    for gnd_pin in ("5", "6", "7", "8", "9", "10", "11", "12", "13"):
        sch.power_pin(rtc, gnd_pin, "GND")
    sch.net(mcu, "44", "I2C1_SCL")  # PB6
    sch.net(mcu, "45", "I2C1_SDA")  # PB7
    sch.net(rtc, "16", "I2C1_SCL")
    sch.net(rtc, "15", "I2C1_SDA")
    i2c_pu1 = sch.place("Device:R", "R", "4.7k", 300, 45)
    sch.net(i2c_pu1, "1", "I2C1_SCL")
    sch.net(i2c_pu1, "2", "+3V3_MCU")
    i2c_pu2 = sch.place("Device:R", "R", "4.7k", 310, 45)
    sch.net(i2c_pu2, "1", "I2C1_SDA")
    sch.net(i2c_pu2, "2", "+3V3_MCU")

    rtc_batt = sch.place(
        "Connector_Generic:Conn_01x02", "J", "CR2032_HOLDER", 300, 90,
        footprint_override="Battery:BatteryHolder_MPD_BA9V-1_1x20mm",
    )
    sch.pwr_flag(rtc_batt, "1", "VBAT_RTC")  # externally-sourced net (the coin cell) -- see README.md
    sch.power_pin(rtc_batt, "2", "GND")
    sch.net(rtc, "14", "VBAT_RTC")

    # ------------------------------------------------------------------ #
    # Wireless: ESP32-C3-MINI-1U (USART1: PA9=TX, PA10=RX), U.FL -> SMA
    # ------------------------------------------------------------------ #

    esp = sch.place("gridnet_parts:ESP32-C3-MINI-1U", "U", "ESP32-C3-MINI-1U", 350, 60)
    sch.net(esp, "2", "+3V3_RF")
    sch.power_pin(esp, "1", "GND")
    sch.power_pin(esp, "19", "GND")
    en_r = sch.place("Device:R", "R", "10k", 335, 45)
    sch.net(esp, "3", "ESP_EN")
    sch.net(en_r, "1", "ESP_EN")
    sch.net(en_r, "2", "+3V3_RF")
    boot_r = sch.place("Device:R", "R", "10k", 365, 45)
    sch.net(esp, "13", "ESP_IO9")
    sch.net(boot_r, "1", "ESP_IO9")
    sch.net(boot_r, "2", "+3V3_RF")

    sch.net(mcu, "32", "USART1_TX")  # PA9
    sch.net(mcu, "33", "USART1_RX")  # PA10
    sch.net(esp, "17", "USART1_TX")  # ESP U0RXD <- MCU TX
    sch.net(esp, "18", "USART1_RX")  # ESP U0TXD -> MCU RX

    sch.net(esp, "15", "USB_DN")  # IO18/USB_D-
    sch.net(esp, "16", "USB_DP")  # IO19/USB_D+

    # U.FL pad on the ESP32-C3-MINI-1U module itself
    ufl = sch.place(
        "Connector:Conn_Coaxial_Small", "J", "U.FL", 350, 90,
        footprint_override="RF_Connector:U.FL_Molex_MCRF_73412-0110",
    )
    sch.net(esp, "ANT", "ANT_RF")
    sch.net(ufl, "1", "ANT_RF")
    sch.power_pin(ufl, "2", "GND")
    # Board-edge SMA, reached via a U.FL-to-SMA pigtail from the module's U.FL pad
    pigtail_sma = sch.place(
        "Connector:Conn_Coaxial", "J", "SMA_EDGE", 350, 105,
        footprint_override="Connector_Coaxial:SMA_Amphenol_132289_EdgeMount",
    )
    sch.net(pigtail_sma, "1", "ANT_RF")
    sch.power_pin(pigtail_sma, "2", "GND")

    # ------------------------------------------------------------------ #
    # Off-board connectors: display (SPI2), keyboard controller (USART2),
    # speaker (PAM8403), keyboard backlight
    # ------------------------------------------------------------------ #

    sch.net(mcu, "28", "SPI2_SCK")   # PB13
    sch.net(mcu, "29", "SPI2_MISO")  # PB14
    sch.net(mcu, "30", "SPI2_MOSI")  # PB15
    sch.net(mcu, "27", "DISP_CS")    # PB12
    sch.net(mcu, "40", "DISP_RESET")  # PA15
    sch.net(mcu, "2", "DISP_INT")    # PC13

    disp_conn = sch.place(
        "Connector_Generic:Conn_01x08", "J", "RA8875_DISPLAY_MODULE", 415, 45,
        footprint_override="Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
    )
    sch.net(disp_conn, "1", "+3V3_MCU")
    sch.power_pin(disp_conn, "2", "GND")
    sch.net(disp_conn, "3", "SPI2_SCK")
    sch.net(disp_conn, "4", "SPI2_MISO")
    sch.net(disp_conn, "5", "SPI2_MOSI")
    sch.net(disp_conn, "6", "DISP_CS")
    sch.net(disp_conn, "7", "DISP_RESET")
    sch.net(disp_conn, "8", "DISP_INT")

    sch.net(mcu, "41", "USART2_TX")  # PB3
    sch.net(mcu, "42", "USART2_RX")  # PB4
    kbd_conn = sch.place(
        "Connector_Generic:Conn_01x04", "J", "CH552G_KEYBOARD_MCU", 415, 75,
        footprint_override="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    )
    sch.net(kbd_conn, "1", "+3V3_MCU")
    sch.power_pin(kbd_conn, "2", "GND")
    sch.net(kbd_conn, "3", "USART2_TX")
    sch.net(kbd_conn, "4", "USART2_RX")

    sch.net(mcu, "43", "KBD_BACKLIGHT_PWM")  # PB5
    # Keyboard-backlight LED-array low-side switch
    kbl_fet = sch.place("Transistor_FET:2N7002", "Q", "2N7002", 445, 90)
    sch.net(kbl_fet, "1", "KBD_BACKLIGHT_PWM")  # gate
    sch.power_pin(kbl_fet, "2", "GND")  # source
    kbl_conn = sch.place(
        "Connector_Generic:Conn_01x02", "J", "KEYBOARD_BACKLIGHT_LEDS", 445, 110,
        footprint_override="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    )
    sch.net(kbl_conn, "1", "+3V3_MCU")
    sch.net(kbl_conn, "2", "KBL_DRAIN")
    sch.net(kbl_fet, "3", "KBL_DRAIN")  # drain

    sch.net(mcu, "31", "AUDIO_SHDN")  # PA8
    amp = sch.place("gridnet_parts:PAM8403D", "U", "PAM8403D", 410, 135)
    sch.power_pin(amp, "6", "+5V")
    sch.power_pin(amp, "4", "+5V")
    sch.power_pin(amp, "11", "GND")
    sch.power_pin(amp, "2", "GND")
    sch.net(amp, "12", "AUDIO_SHDN")
    sch.power_pin(amp, "5", "GND")  # ~MUTE tied active-low-disabled (always unmuted)
    # Mono source: INL, INR, and VREF are all tied to the same filtered node
    # -- a single PWM-to-analog RC filter drives both channels together,
    # since there's only one speaker (see hardware/bom.md's Speaker line).
    sch.net(amp, "7", "AUDIO_IN")   # INL
    sch.net(amp, "10", "AUDIO_IN")  # INR
    sch.net(amp, "8", "AUDIO_IN")   # VREF
    # 1k + C below: PWM-to-analog RC filter for the mono audio source
    audio_dac_r = sch.place("Device:R", "R", "1k", 385, 155)
    sch.net(mcu, "16", "AUDIO_PWM")  # PA4
    sch.net(audio_dac_r, "1", "AUDIO_PWM")
    sch.net(audio_dac_r, "2", "AUDIO_IN")
    audio_dac_c = sch.place("Device:C", "C", "100nF", 400, 155)
    sch.net(audio_dac_c, "1", "AUDIO_IN")
    sch.power_pin(audio_dac_c, "2", "GND")

    speaker_conn = sch.place(
        "Connector_Generic:Conn_01x02", "J", "SPEAKER_1W_8OHM", 445, 155,
        footprint_override="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    )
    sch.net(amp, "1", "SPK_L+")
    sch.net(amp, "3", "SPK_L-")
    sch.net(speaker_conn, "1", "SPK_L+")
    sch.net(speaker_conn, "2", "SPK_L-")

    # ------------------------------------------------------------------ #
    # Explicitly-unused pins -- extra MCU GPIOs and peripheral features this
    # design doesn't wire up (yet). Marked no_connect rather than left
    # dangling, so ERC's pin_not_connected check reflects "intentionally
    # unused" instead of "might be a wiring bug".
    # ------------------------------------------------------------------ #

    for p in ("3", "4", "13", "20", "21", "23", "24", "34", "35", "47", "48"):
        sch.no_connect(mcu, p)  # PC14/PC15/PA3/PB0/PB1/PB10/PB11/PA11/PA12/PB8/PB9
    for p in ("2", "8", "9"):
        sch.no_connect(sdcard, p)  # DAT3/CD, DAT1, SHIELD -- 1-bit SPI mode only
    for p in ("1", "3", "4"):
        sch.no_connect(rtc, p)  # 32KHZ, ~INT/SQW, ~RST -- not used by firmware yet
    for p in ("4", "5", "6", "7", "8", "9", "10", "11", "12", "14"):
        sch.no_connect(esp, p)  # IO0/BOOT_SEL through IO8, IO10 -- spare GPIOs
    for p in ("14", "16"):
        sch.no_connect(amp, p)  # ROUT-/ROUT+ -- mono design, right channel unused
    sch.no_connect(boost, "1")  # IP5306 VIN -- unused, charging handled separately by U1 (MCP73831)
    sch.no_connect(boost, "8")  # IP5306 LED2 -- one battery-level LED (pin 7) is enough

    return sch


if __name__ == "__main__":
    sch = build()
    out = "../main-board.kicad_sch"
    with open(out, "w", encoding="utf-8") as f:
        f.write(sch.render())
    print(f"wrote {out}")
