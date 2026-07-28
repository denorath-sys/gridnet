GRIDNET — Bill of Materials (BOM)
REV 0.6 — Prototype (Single Unit, Retail Pricing)

REV 0.5 note: several REV 0.4 part choices didn't hold up under review —
either a real spec mismatch (a display resolution the driver IC can't
produce) or a part variant that doesn't support a feature the board design
assumes (an antenna connector with nothing behind it). See "Design Notes —
REV History" at the bottom of this file for what changed and why.

REV 0.6 note: the antenna chain REV 0.5 added to fix that last item was
itself unbuildable — the wrong connector generation, a connector style that
cannot be reached by a cable, and no antenna at all. Board 2 items 13-15
and the totals are corrected here.

Board 1 — PLC / Power Board (100×80mm)
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1PLC SoCST7580CENELEC EN50065, OFDM/FSK, 9–148kHz1$5.70$5.702TVS DiodeP6KE250CABidirectional, 250V — surge protection (Layer 1)1$0.60$0.603MOVS20K275275V varistor — overvoltage protection (Layer 2)1$0.40$0.404SMPS ModuleHLK-5M05230VAC → 5VDC, 1A1$3.50$3.505Boost converterMT36085V → 12V for the ST7580's VCC/PA rail, 2A switch1$0.30$0.306Boost inductor22µH, 2A saturationMT3608 switching inductor1$0.20$0.207Schottky diodesSS34Source ORing (2), supercap discharge (1), boost rectifier (1)4$0.10$0.408SupercapacitorNAT 1F 5.5VHold-up so the ESP32 can tell the Terminal mains has gone1$1.20$1.209USB-C receptacleTYPE-C-31-M-125V inlet from the Terminal's battery during an outage1$0.40$0.4010Coupling transformerWürth Elektronik WE-PLCC seriesPLC line coupling, 1:1, CENELEC A-band — confirm exact part against ST7580 application note before ordering (REV 0.4 left this unspecified)1$2.00$2.0011Connector J1—2×8 pin, 2.54mm — this board's own interface header (Schuko-plug wiring, status LEDs); "main board" here means Board 1 is the PLC Adapter's own main/only board, not a connection to Board 2 — the two products don't connect to each other, see the top-level README's Hardware Overview1$0.30$0.3012Passive components—Resistors, capacitors, ferrite beads—$1.50$1.50Board 1 Total~$16.50

Board 2 — Main Board (100×80mm)
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1MCUGD32VF103CCT6RISC-V, 108MHz, 32KB RAM, 256KB Flash — same 48-pin package/pinout as REV 0.4's CBT6, next density step up (REV 0.4's README claimed 1MB Flash, which no GD32VF103 variant actually offers; 256KB is the real ceiling in this pin-compatible family)1$1.80$1.802Wi-Fi / BT ModuleESP32-C3-MINI-1UWi-Fi 2.4GHz mesh + Bluetooth 5.0 LE — "U" variant, has the on-module external-antenna jack REV 0.4's plain MINI-1 lacks (see items 13-14). That jack is the module's only RF output: datasheet v2.2 Table 3-1 gives the module 53 pads and none of them is an RF pad1$0.80$0.803SRAM23LC10241Mb SPI SRAM1$1.20$1.204FlashW25Q64JVSSIQ8MB SPI NOR Flash1$0.60$0.605RTCDS3231SNI2C RTC, ±2ppm accuracy1$1.80$1.806RTC BatteryCR20323V coin cell1$0.30$0.307LiPo chargerMCP73831Single-cell LiPo charge controller1$0.50$0.508Boost converterIP53065V boost + battery management1$0.60$0.609LDOAMS1117-3.33.3V LDO regulator2$0.15$0.3010AmplifierPAM84033W class-D audio amplifier1$0.40$0.4011microSD socket—SPI, push-push type1$0.50$0.5012USB-C connector—Power input, DFU firmware update1$0.40$0.4013SMA jack, bulkhead—Antenna port through the enclosure wall. Not a PCB part: an edge-mount SMA soldered to the board cannot be fed by a pigtail, because its centre pin is a board pad. REV 0.5 specified the edge-mount version and it was placed on the PCB as J8; see hardware/pcb/main-board/README.md1$0.80$0.8014Antenna pigtail, MHF III (W.FL / AMC) plug to SMA~100mm, from item 2's on-module jack to item 13. Not U.FL: datasheet section 10.2 specifies the third-generation connector (2.05×1.7×1.40mm, compatible with Hirose W.FL, I-PEX MHF III, Amphenol AMC), and a U.FL/MHF I plug does not mate with it1$0.60$0.60152.4GHz antenna—SMA male, ≤2.33 dBi, 50Ω. The gain ceiling is not a preference: 2.33 dBi is the antenna Espressif certified the module with, and exceeding it puts the product outside the module's existing test reports (datasheet section 10.2). Missing from REV 0.5 entirely — the BOM had the connector and the cable but no antenna1$1.20$1.2016Crystal8MHz HC49/SMD + 2×20pF load capsGD32VF103 HSE clock reference1$0.15$0.1517Passive components—Resistors, capacitors, inductors—$1.50$1.50Board 2 Total~$13.45

Display & Input
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1LCD Display + controllerRA8875-based 800×480 TFT module (SPI, onboard SDRAM frame buffer)5.0" TFT, 800×480, 256-color (8bpp) mode, amber-tinted backlight — REV 0.4 specified ILI9488, which tops out at 480×320 and cannot drive this resolution at all; RA8875 modules ship with their own onboard SDRAM specifically so a small MCU with no LCD/LTDC peripheral (like the GD32VF103) never has to hold an 800×480 frame buffer itself (384KB — far beyond both the MCU's 32KB RAM and the board's 128KB SPI SRAM)1$32.00$32.002Keyboard controllerCH552GUSB MCU, key matrix scanning1$0.50$0.503Key switchesKailh PG1350Low-profile mechanical, 40 pcs40$0.25$10.004Keycaps—Low-profile, custom legend1 set$3.00$3.005Keyboard backlight—Amber SMD LED, 0402, 40 pcs40$0.03$1.206TrackPoint moduleGeneric analog trackpoint module (hobbyist keyboard-build market)Analog X/Y strain-gauge output, direct-ADC-compatible — REV 0.4 said "PS/2 compatible," which is a synchronous serial protocol needing bit-banged/USART decoding, not a raw ADC read; docs/firmware-arch.md's own task table already says "TrackPoint ADC," so the description (not the part class) was the mismatch1$2.50$2.507Speaker—1W, 8Ω, 28mm diameter1$1.50$1.50Display & Input Total~$50.70

Power System
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1Li-ion cellGenuine 18650, 3350mAh-class (e.g. Panasonic NCR18650B) — source from an authorized distributor, not generic marketplace listings3.7V, 3350mAh — 2 cells in parallel = ~6700mAh total. REV 0.4 spec'd 2×2500mAh cells (=5000mAh) in the BOM while the top-level README claimed "8000mAh" — no genuine 18650 chemistry reaches 4000mAh/cell (2× would need to), and 18650s advertised at 8000-9000mAh on general marketplaces are essentially always counterfeit/overrated; 6700mAh is the real ceiling for 2 genuine cells and the closest honest match to the original target2$4.20$8.402Battery holder—2× 18650 parallel holder1$1.50$1.503Protection circuit—Overcurrent + overvoltage PCM1$0.80$0.80Power Total~$10.70

Enclosure
#ComponentDescriptionQtyUnit Cost (USD)Total1Top caseMat black ABS-PC, clamshell lid1$8.00$8.002Bottom caseMat black ABS-PC, keyboard base1$8.00$8.003Hinge assemblySteel, 135° stop, ×21 set$3.00$3.004Corner bumpersTPU rubber, ×41 set$1.00$1.005Screws & insertsM2 screws + brass inserts1 set$1.50$1.50Enclosure Total~$21.50

PLC Adapter (Separate Unit)
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1PLC SoCST7580CENELEC EN50065, OFDM/FSK1$5.70$5.702Wi-Fi ModuleESP32-C3-MINI-1Wi-Fi AP for terminal connection1$0.80$0.803SMPSHLK-5M05230VAC → 5VDC1$3.50$3.504Outage power pathUSB-C + supercap + boostRuns from the Terminal's battery when mains is gone1 set$2.30$2.305Protection circuitTVS + MOVLayers 1-2, same as Board 1 (Layer 3 went with the inverter)1 set$1.00$1.006Schuko plug—Direct wall mount, 230V1$1.50$1.507EnclosureMat black ABSCompact square, ~110×90×30mm — sized for Board 1's 100×80mm PCB plus the Schuko plug and wall clearance; REV 0.4's ~80×80×40mm estimate predates that PCB size and never got reconciled against it, unlike the other REV 0.4 numbers listed in "Design Notes — REV History" below1$3.00$3.008LEDs—3× status LED (Power/PLC/WiFi)3$0.10$0.309Passive components—Resistors, capacitors—$1.00$1.00Adapter Total~$19.10

PCB Manufacturing (JLCPCB, 5 units each)
BoardSizeLayersQtyCostPLC / Power Board100×80mm25 pcs~$8.00Main Board100×80mm25 pcs~$8.00Adapter Board70×60mm25 pcs~$5.00PCB Total~$21.00

Cost Summary
ModuleCost (USD)Board 1 — PLC / Power~$16.50Board 2 — Main Board~$13.45Display & Input~$50.70Power System~$10.70Enclosure~$21.50PLC Adapter~$19.10PCB Manufacturing~$21.00TOTAL (single prototype)~$152.95

REV 0.4 totaled ~$135.80 (and the top-level README separately claimed
~$112). Neither figure survives this revision — the corrected total is
~$152.95, about $17.15 higher, almost entirely from the display module
(+$14.00: REV 0.4's number was for a bare ILI9488 panel that couldn't
actually produce the specced resolution, not a real like-for-like part).

Three of these numbers are arithmetic fixes rather than part changes.
REV 0.5's Board 1 line read ~$18.90 against items summing to $16.50, its
PLC Adapter line read ~$19.10 while the Cost Summary used ~$19.40, and the
Summary used ~$16.70 for Board 1 — a third figure again. Every subtotal in
this file now equals the sum of its own line items, and the total equals
the sum of the subtotals.

Note: Costs are single-unit retail estimates. Volume pricing significantly reduces cost (ratios carried over from REV 0.4's estimate):
10 units → ~$107/unit · 100 units → ~$70/unit · 1000 units → ~$43/unit


Where To Source
SupplierWhat To BuyLCSCAll ICs, passives, connectors (China, fast shipping)JLCPCBPCB fabrication + optional SMT assemblyAliExpressEnclosure parts, mechanical parts — not battery cells (see note)18650 cells18650BatteryStore, Illumn, or another dedicated protected-cell reseller — avoid generic marketplace listings specifically for cells; "8000mAh 18650" listings are essentially always counterfeit/overrated, real cells top out around 3500mAh per cellMouserST7580 (official distributor), DS3231, protection ICs, RA8875 display modulesDigiKeyAlternative for all major ICs

Design Notes — REV History

REV 0.5 replaces five REV 0.4 choices that didn't survive a component-level
review — each one reproducible from the datasheet/module spec, not a
judgment call:

1. Display driver couldn't produce the specified resolution. ILI9488 tops
   out at 480×320; the spec called for 800×480. Even a corrected driver IC
   needed a second property the GD32VF103 doesn't have: an LTDC/RGB display
   peripheral, or enough RAM (800×480 at 8bpp is 384KB — more than the 32KB
   on-chip RAM and the 128KB external SPI SRAM combined) to hold a frame
   buffer itself. Fix: an RA8875-based module, which ships with its own
   onboard SDRAM and talks to the host MCU over SPI a command/pixel stream
   at a time — the standard way small MCUs drive displays too large to
   buffer themselves.
2. Wi-Fi module variant had no connector for the antenna next to it in the
   BOM. ESP32-C3-MINI-1 has an onboard PCB antenna and no external-antenna
   connector at all; ESP32-C3-MINI-1U (same pinout/footprint) has the
   antenna jack the SMA connector needs something to plug into. Fix: swap
   the module, add the missing pigtail. (REV 0.5 called that jack "U.FL"
   and specified a U.FL pigtail and an edge-mount SMA to go with it. All
   three were wrong — see the REV 0.6 note below.)
3. MCU flash size in the top-level README (1MB) doesn't exist in this chip
   family — GD32VF103's real ceiling is 256KB, still in a pin-compatible
   part (CCT6 vs. the original CBT6's 128KB). Fixed the BOM to the real part
   and the README to the real number, rather than chasing a spec no variant
   of this MCU can meet.
4. Battery capacity claim (8000mAh) doesn't match either the BOM's actual
   2×2500mAh cells (5000mAh) or physical reality for 2 cells of any genuine
   18650 chemistry (would need 4000mAh/cell; real cells top out ~3500mAh).
   Fixed to genuine 3350mAh-class cells (~6700mAh total) — the honest
   ceiling for 2 real cells, and flagged the "8000mAh 18650" claims common
   on general marketplaces as effectively always counterfeit. (The "~5 days
   active use" runtime derived from this capacity was also wrong for
   unrelated reasons — see docs/firmware-arch.md's Power Budget section.)
5. TrackPoint description said "PS/2 compatible" (a synchronous serial
   protocol) while docs/firmware-arch.md's own task table already said
   "TrackPoint ADC" (raw analog reads) — these need different firmware and
   different wiring. The part class that's actually sourced for DIY
   keyboard builds is analog/ADC-compatible, matching the firmware doc; only
   the BOM's description was wrong, not the part.
6. PLC Adapter enclosure sized for a different PCB than the one in its own
   BOM. Board 1 (the PLC Adapter's PCB) is spec'd at 100×80mm, but the
   Adapter's enclosure line said "~80×80×40mm" — physically too small to
   hold that PCB. Unlike items 1-5 above, this one wasn't part of the
   original REV 0.5 pass; caught later, once Board 1's schematic work
   started. Fixed to ~110×90×30mm (fits the PCB plus the Schuko plug and
   wall clearance). Also clarified Board 1's `J1` connector description —
   "main board interface" read as if it connected to Board 2 (the Terminal's
   Main Board), but Board 1 and Board 2 are different products that never
   connect to each other (see the top-level README's Hardware Overview);
   `J1` is this board's own interface to the Adapter's Schuko-plug wiring
   and status LEDs.

REV 0.6 corrects the antenna chain, all of it from the ESP32-C3-MINI-1/1U
datasheet v2.2 while laying out Board 2 (see
hardware/pcb/main-board/README.md's "The antenna path never touched the
board"):

7. The pigtail was the wrong connector generation. Section 10.2 specifies
   the module's jack as the third-generation connector — 2.05×1.7×1.40mm,
   compatible with Hirose W.FL, I-PEX MHF III and Amphenol AMC. U.FL /
   MHF I is the first generation, ~2.6mm across, and does not mate with it.
   Every "U.FL" in REV 0.5's Board 2 items and design notes was wrong about
   the part on the module.
8. The SMA was specified edge-mount, which the pigtail cannot reach. An
   edge-mount SMA's centre pin is a pad on the PCB, so it has to be fed by
   board copper — and the module has no RF pad to feed it from (Table 3-1:
   53 pads, all GND, 3V3, EN or IO). It is now a bulkhead jack in the
   enclosure wall, which is what a pigtail actually terminates in, and it
   is no longer a PCB part.
9. There was no antenna in the BOM. Items 13 and 14 bought a connector and
   a cable to nowhere. Added, with the gain ceiling the module's
   certification depends on (≤2.33 dBi).

Also added two REV 0.4 omissions that would have blocked fabrication
regardless: an explicit crystal for the GD32VF103's clock (was silently
folded into a generic "passives" line with no frequency specified), and a
named component family for the PLC coupling transformer (was a bare "—"
with no part reference at all — still needs confirming against ST7580's
application note before ordering, this isn't a fully closed item).

Last updated: 2026 — REV 0.6
