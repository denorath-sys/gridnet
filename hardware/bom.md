# GRIDNET — Bill of Materials (BOM)

**REV 0.10 — Prototype (Single Unit, Retail Pricing)**
*(revision ten, following 0.9 — not 0.1)*

> **REV 0.10 note:** `J1` is no longer an estimate. It is Würth 691311400102,
> the part the PCB footprint has been using all along
> (`TerminalBlock_Wuerth_691311400102_P7.62mm`) — WR-TBL 3114, 2-pole, 7.62mm,
> 300V / 20A (UL), $0.42 at single quantity.
>
> Pricing it surfaced a gap the estimate had been covering: **it is a
> pluggable header, and the plug that mates with it was never in the BOM.**
> Würth 691351400002, $1.25. Without it the board can be fabricated and
> populated with no way to attach the Schuko plug's L/N wires. `J1` therefore
> goes from an estimated $0.70 to a real $1.67 across two line items, and the
> total from ~$149.25 to **~$150.22**.
>
> The one-piece alternative was considered and declined for now — see the note
> under the Board 1 table.
>
> **REV 0.9 note:** this file described a system with three PCBs and two PLC
> modems. It has one of each. Board 1's schematic
> ([`pcb/plc-board/plc-board.kicad_sch`](pcb/plc-board/plc-board.kicad_sch)) carries the ESP32-C3, the
> status LEDs, the mains input and the USB-C outage inlet, which means Board 1
> *is* the PLC Adapter — but a separate "PLC Adapter (Separate Unit)" section
> billed the ST7580, the HLK-5M05, the protection layers and the outage power
> path a second time, and the PCB table ordered a 70×60mm "Adapter Board" that
> was never designed. Both are removed.
>
> Checking the other direction found the mirror-image error: five things in
> that schematic had never been costed anywhere — the ESP32-C3-MINI-1 (`U2`),
> the AMS1117-3.3 that feeds it (`U3`), the 8MHz crystal (`Y1`), the three
> status LEDs (`D2`–`D4`), and the ESP32/ST7580 programming headers (`J2`,
> `J3`). `J1` was also still costed as a 2×8 2.54mm header after DRC forced it
> to a 7.62mm mains terminal block.
>
> Board 1's line items are now keyed to the schematic's reference designators
> so the two can be checked against each other directly. Total moves from
> ~$166.65 to **~$149.25**.
>
> **REV 0.5 note:** several REV 0.4 part choices didn't hold up under review —
> either a real spec mismatch (a display resolution the driver IC can't
> produce) or a part variant that doesn't support a feature the board design
> assumes (an antenna connector with nothing behind it). See "Design Notes —
> REV History" at the bottom of this file for what changed and why.
>
> **REV 0.6 note:** the antenna chain REV 0.5 added to fix that last item was
> itself unbuildable — the wrong connector generation, a connector style that
> cannot be reached by a cable, and no antenna at all. Board 2 items 13-15
> and the totals are corrected here.
>
> **REV 0.7 note:** AN4068 was finally obtained, so Board 1's line coupling is no
> longer a placeholder. The coupling transformer has a real part number, and
> the rest of the coupling network is costed as items 11-13. Note that its
> values are not AN4068's — that reference design is an A-band node and this
> one is not; see [`docs/plc-coupling.md`](../docs/plc-coupling.md).
>
> **REV 0.8 note:** Board 1 is a four-layer board. Not for signal density — it
> could very nearly be routed on two — but because the ST7580's nine +5V pads
> on a 48-pin 0.5mm-pitch package need a plane, and on two layers both copper
> layers are spoken for by ground and the mains barrier. See
> [`hardware/pcb/plc-board/README.md`](pcb/plc-board/README.md) for the four two-layer routing runs that
> established this. The PCB line below moves from 2 to 4 layers accordingly.

## Board 1 — PLC / Power Board (100×80mm)

**This board *is* the PLC Adapter's electronics.** Everything the Adapter does
electrically happens here: mains input and protection, the AC-DC supply, the
ST7580 modem and its line coupling, the ESP32-C3 that serves the Terminal's
Wi-Fi link, the outage power path, and the status LEDs. The Adapter's only
other parts are mechanical — see "PLC Adapter — Non-PCB Parts" below. The two
products in this project are the Terminal (Board 2 + display + keyboard +
battery + clamshell) and the Adapter (this board + plug + enclosure); they
never connect to each other electrically.

Reference designators below are the ones in
[`hardware/pcb/plc-board/plc-board.kicad_sch`](pcb/plc-board/plc-board.kicad_sch), so this table can be
checked against the schematic directly.

| # | Component | Part Number | Description | Qty | Unit Cost (USD) | Total |
|---|---|---|---|---|---|---|
| 1 | PLC SoC | ST7580 | `U4` — CENELEC EN50065, OFDM/FSK, 9–148kHz | 1 | $5.70 | $5.70 |
| 2 | Wi-Fi module | ESP32-C3-MINI-1 | `U2` — Wi-Fi AP for the Terminal's link, and UART host for the ST7580. Plain MINI-1, not the "U" variant Board 2 uses: this board has no external antenna, so the on-module PCB antenna is the right choice | 1 | $0.80 | $0.80 |
| 3 | TVS Diode | P6KE250CA | `D1` — bidirectional, 250V — surge protection (Layer 1) | 1 | $0.60 | $0.60 |
| 4 | MOV | S20K275 | `RV1` — 275V varistor — overvoltage protection (Layer 2) | 1 | $0.40 | $0.40 |
| 5 | SMPS Module | HLK-5M05 | `U1` — 230VAC → 5VDC, 1A, isolated | 1 | $3.50 | $3.50 |
| 6 | Boost converter | MT3608 | `U5` — 5V → 12V for the ST7580's VCC/PA rail, 2A switch | 1 | $0.30 | $0.30 |
| 7 | LDO | AMS1117-3.3 | `U3` — 3.3V rail for the ESP32-C3 | 1 | $0.15 | $0.15 |
| 8 | Crystal | 8MHz | `Y1` — ST7580 clock reference | 1 | $0.15 | $0.15 |
| 9 | Boost inductor | 22µH, 2A saturation | `L1` — MT3608 switching inductor | 1 | $0.20 | $0.20 |
| 10 | Schottky diodes | SS34 | `D5`–`D8` — source ORing (2), supercap discharge (1), boost rectifier (1) | 4 | $0.10 | $0.40 |
| 11 | Supercapacitor | NAT 1F 5.5V | `C7` — hold-up so the ESP32 can tell the Terminal mains has gone | 1 | $1.20 | $1.20 |
| 12 | USB-C receptacle | TYPE-C-31-M-12 | `J4` (`TERMINAL_5V_IN`) — 5V inlet from the Terminal's battery during an outage | 1 | $0.40 | $0.40 |
| 13 | Coupling transformer | Würth Elektronik 750510231 | `T1` — PLC line coupling, 1:1 ±1%, 1mH, leakage ≤1µH, 30pF interwinding — the exact part AN4068 names (alternate: TDK SRW13EP-X05H002). REV 0.5 carried "WE-PLCC series, confirm against the application note"; that note has now been read, and every AN4068 Table 4 line is met except withstanding voltage, where Würth quotes 2000VAC/1s against Table 4's ≥4kV impulse figure — confirm with Würth before ordering ([`docs/plc-coupling.md`](../docs/plc-coupling.md)) | 1 | $2.00 | $2.00 |
| 14 | Coupling inductor | 12µH, ≥2A saturation, ≤0.1Ω DCR | `L3` — series element of the line coupling resonance with item 15; the saturation and DCR figures are AN4068's own selection criteria, not preferences — insertion loss and distortion into a heavily loaded line depend on them | 1 | $0.30 | $0.30 |
| 15 | X1 safety capacitor | 150nF X1 MKP, p=15mm | `C17` — series coupling into the live conductor. X1 grade is a safety requirement, not a filter one: this part sits between the board's analog ground and 230V | 1 | $0.60 | $0.60 |
| 16 | Coupling passives | 150µH + 12nF (Rx resonance), 10µF/50V X5R (DC block), 68pF/1nF C0G + 5.1k/22k/33k/10k/1k/150R (Tx active filter) | `L2`, `C15`, `C16`, `C12`–`C14` and the Tx filter resistor network — the rest of the line coupling, values rescaled from AN4068's A-band reference design to GRIDNET's 95–140kHz band, see [`docs/plc-coupling.md`](../docs/plc-coupling.md) | 1 set | $0.80 | $0.80 |
| 17 | Mains header | Würth Elektronik 691311400102 | `J1` (`MAINS_L_N`) — WR-TBL series 3114, closed vertical PCB header, 2-pole, 7.62mm pitch, 300V / 20A (UL), 1600 VAC withstanding. The pitch is not a preference: the 5.08mm placeholder left 2.08mm between its own pads against the `Mains` netclass's standards-derived 2.5mm L-to-N rule, so it failed DRC on its own connector. The current rating is irrelevant here — the HLK-5M05 draws about 30mA at 230V — the pitch is what the clearance rule buys. This is the part the PCB footprint already uses | 1 | $0.42 | $0.42 |
| 18 | Mains header mating plug | Würth Elektronik 691351400002 | Female plug for item 17 — the Schuko plug's L/N wires terminate here, and it plugs onto `J1`. **A pluggable header is only half a connector**; this part was missing from the BOM entirely through REV 0.9, so the board could have been fabricated with no way to attach mains wiring. Kept pluggable rather than swapped for a one-piece block because being able to detach mains from the board without desoldering is worth $1.25 during prototype bring-up | 1 | $1.25 | $1.25 |
| 19 | Status LEDs | — | `D2`/`D3`/`D4` — Power (green, always-on), PLC (amber, driven by the ST7580's `PL_TX_ON`), Wi-Fi (blue, GPIO-driven so firmware can show real status). On-board and wired to the rails directly, not brought out to a separate header | 3 | $0.10 | $0.30 |
| 20 | Programming / debug headers | — | `J2` (ESP32-C3 UART0 — without this there is no way to flash the module at all) and `J3` (ST7580 JTAG) | 2 | $0.20 | $0.40 |
| 21 | Passive components | — | Remaining bulk/bypass R, C, L and ferrite beads (`C1`–`C6`, `C8`–`C11`, `FB1`–`FB2`, `R1`–`R20` less the coupling network above) | — | $1.50 | $1.50 |
| | | | | | **Board 1 Total** | **~$21.37** |

> **On the one-piece alternative.** Würth 691214410002 (WR-TBL 2144, 7.62mm
> horizontal entry, rising cage clamp) would replace both items above with a
> single part at roughly $0.83–1.07, and carries a VDE rating of 450 VAC with
> 2500 VAC withstanding — the latter lining up with IEC 60664's 2500V rated
> impulse for overvoltage category II at 230V, where the 3114's published
> cULus figure is 1600 VAC. It was not adopted here because it needs a
> footprint change, a PCB regeneration and a fresh DRC pass on a board that is
> otherwise ready to fabricate. Worth revisiting before any production run —
> note also its 1.31 mm² (16 AWG) wire ceiling, which rules out 1.5 mm²
> internal wiring.

## Board 2 — Main Board (100×80mm)

| # | Component | Part Number | Description | Qty | Unit Cost (USD) | Total |
|---|---|---|---|---|---|---|
| 1 | MCU | GD32VF103CCT6 | RISC-V, 108MHz, 32KB RAM, 256KB Flash — same 48-pin package/pinout as REV 0.4's CBT6, next density step up (REV 0.4's README claimed 1MB Flash, which no GD32VF103 variant actually offers; 256KB is the real ceiling in this pin-compatible family) | 1 | $1.80 | $1.80 |
| 2 | Wi-Fi / BT Module | ESP32-C3-MINI-1U | Wi-Fi 2.4GHz mesh + Bluetooth 5.0 LE — "U" variant, has the on-module external-antenna jack REV 0.4's plain MINI-1 lacks (see items 13-14). That jack is the module's only RF output: datasheet v2.2 Table 3-1 gives the module 53 pads and none of them is an RF pad | 1 | $0.80 | $0.80 |
| 3 | SRAM | 23LC1024 | 1Mb SPI SRAM | 1 | $1.20 | $1.20 |
| 4 | Flash | W25Q64JVSSIQ | 8MB SPI NOR Flash | 1 | $0.60 | $0.60 |
| 5 | RTC | DS3231SN | I2C RTC, ±2ppm accuracy | 1 | $1.80 | $1.80 |
| 6 | RTC Battery | CR2032 | 3V coin cell | 1 | $0.30 | $0.30 |
| 7 | LiPo charger | MCP73831 | Single-cell LiPo charge controller | 1 | $0.50 | $0.50 |
| 8 | Boost converter | IP5306 | 5V boost + battery management | 1 | $0.60 | $0.60 |
| 9 | LDO | AMS1117-3.3 | 3.3V LDO regulator | 2 | $0.15 | $0.30 |
| 10 | Amplifier | PAM8403 | 3W class-D audio amplifier | 1 | $0.40 | $0.40 |
| 11 | microSD socket | — | SPI, push-push type | 1 | $0.50 | $0.50 |
| 12 | USB-C connector | — | Power input, DFU firmware update | 1 | $0.40 | $0.40 |
| 13 | SMA jack, bulkhead | — | Antenna port through the enclosure wall. Not a PCB part: an edge-mount SMA soldered to the board cannot be fed by a pigtail, because its centre pin is a board pad. REV 0.5 specified the edge-mount version and it was placed on the PCB as J8; see [`hardware/pcb/main-board/README.md`](pcb/main-board/README.md) | 1 | $0.80 | $0.80 |
| 14 | Antenna pigtail | MHF III (W.FL / AMC) plug to SMA | ~100mm, from item 2's on-module jack to item 13. Not U.FL: datasheet section 10.2 specifies the third-generation connector (2.05×1.7×1.40mm, compatible with Hirose W.FL, I-PEX MHF III, Amphenol AMC), and a U.FL/MHF I plug does not mate with it | 1 | $0.60 | $0.60 |
| 15 | 2.4GHz antenna | — | SMA male, ≤2.33 dBi, 50Ω. The gain ceiling is not a preference: 2.33 dBi is the antenna Espressif certified the module with, and exceeding it puts the product outside the module's existing test reports (datasheet section 10.2). Missing from REV 0.5 entirely — the BOM had the connector and the cable but no antenna | 1 | $1.20 | $1.20 |
| 16 | Crystal | 8MHz HC49/SMD + 2×20pF load caps | GD32VF103 HSE clock reference | 1 | $0.15 | $0.15 |
| 17 | Passive components | — | Resistors, capacitors, inductors | — | $1.50 | $1.50 |
| | | | | | **Board 2 Total** | **~$13.45** |

## Display & Input

| # | Component | Part Number | Description | Qty | Unit Cost (USD) | Total |
|---|---|---|---|---|---|---|
| 1 | LCD Display + controller | RA8875-based 800×480 TFT module (SPI, onboard SDRAM frame buffer) | 5.0" TFT, 800×480, 256-color (8bpp) mode, amber-tinted backlight — REV 0.4 specified ILI9488, which tops out at 480×320 and cannot drive this resolution at all; RA8875 modules ship with their own onboard SDRAM specifically so a small MCU with no LCD/LTDC peripheral (like the GD32VF103) never has to hold an 800×480 frame buffer itself (384KB — far beyond both the MCU's 32KB RAM and the board's 128KB SPI SRAM) | 1 | $32.00 | $32.00 |
| 2 | Keyboard controller | CH552G | USB MCU, key matrix scanning | 1 | $0.50 | $0.50 |
| 3 | Key switches | Kailh PG1350 | Low-profile mechanical, 40 pcs | 40 | $0.25 | $10.00 |
| 4 | Keycaps | — | Low-profile, custom legend | 1 set | $3.00 | $3.00 |
| 5 | Keyboard backlight | — | Amber SMD LED, 0402, 40 pcs | 40 | $0.03 | $1.20 |
| 6 | TrackPoint module | Generic analog trackpoint module (hobbyist keyboard-build market) | Analog X/Y strain-gauge output, direct-ADC-compatible — REV 0.4 said "PS/2 compatible," which is a synchronous serial protocol needing bit-banged/USART decoding, not a raw ADC read; [`docs/firmware-arch.md`](../docs/firmware-arch.md)'s own task table already says "TrackPoint ADC," so the description (not the part class) was the mismatch | 1 | $2.50 | $2.50 |
| 7 | Speaker | — | 1W, 8Ω, 28mm diameter | 1 | $1.50 | $1.50 |
| | | | | | **Display & Input Total** | **~$50.70** |

## Power System

| # | Component | Part Number | Description | Qty | Unit Cost (USD) | Total |
|---|---|---|---|---|---|---|
| 1 | Li-ion cell | Genuine 18650, 3350mAh-class (e.g. Panasonic NCR18650B) — source from an authorized distributor, not generic marketplace listings | 3.7V, 3350mAh — 2 cells in parallel = ~6700mAh total. REV 0.4 spec'd 2×2500mAh cells (=5000mAh) in the BOM while the top-level README claimed "8000mAh" — no genuine 18650 chemistry reaches 4000mAh/cell (2× would need to), and 18650s advertised at 8000-9000mAh on general marketplaces are essentially always counterfeit/overrated; 6700mAh is the real ceiling for 2 genuine cells and the closest honest match to the original target | 2 | $4.20 | $8.40 |
| 2 | Battery holder | — | 2× 18650 parallel holder | 1 | $1.50 | $1.50 |
| 3 | Protection circuit | — | Overcurrent + overvoltage PCM | 1 | $0.80 | $0.80 |
| | | | | | **Power Total** | **~$10.70** |

## Enclosure

| # | Component | Description | Qty | Unit Cost (USD) | Total |
|---|---|---|---|---|---|
| 1 | Top case | Mat black ABS-PC, clamshell lid | 1 | $8.00 | $8.00 |
| 2 | Bottom case | Mat black ABS-PC, keyboard base | 1 | $8.00 | $8.00 |
| 3 | Hinge assembly | Steel, 135° stop, ×2 | 1 set | $3.00 | $3.00 |
| 4 | Corner bumpers | TPU rubber, ×4 | 1 set | $1.00 | $1.00 |
| 5 | Screws & inserts | M2 screws + brass inserts | 1 set | $1.50 | $1.50 |
| | | | | **Enclosure Total** | **~$21.50** |

## PLC Adapter — Non-PCB Parts

Only what Board 1 does not already carry. Through REV 0.8 this section was a
second, parallel bill for the whole Adapter — see the REV 0.9 note at the top
of this file.

| # | Component | Part Number | Description | Qty | Unit Cost (USD) | Total |
|---|---|---|---|---|---|---|
| 1 | Schuko plug | — | Direct wall mount, 230V. Wires to Board 1's `J1` | 1 | $1.50 | $1.50 |
| 2 | Enclosure | Mat black ABS | Compact square, ~110×90×30mm — sized for Board 1's 100×80mm PCB plus the Schuko plug and wall clearance; REV 0.4's ~80×80×40mm estimate predates that PCB size and never got reconciled against it, unlike the other REV 0.4 numbers listed in "Design Notes — REV History" below | 1 | $3.00 | $3.00 |
| | | | | | **Adapter Non-PCB Total** | **~$4.50** |

## PCB Manufacturing (JLCPCB, 5 units each)

Two boards, not three. This project has exactly two PCBs — Board 1 (the
Adapter) and Board 2 (the Terminal). Through REV 0.8 this table also carried a
70×60mm "Adapter Board", which was the same double-count as the section above:
there is no such board and none is designed.

| Board | Size | Layers | Qty | Cost |
|---|---|---|---|---|
| Board 1 — PLC / Power Board | 100×80mm | 4 — see [`hardware/pcb/plc-board/README.md`](pcb/plc-board/README.md) | 5 pcs | ~$20.00 |
| Board 2 — Main Board | 100×80mm | 2 — 1.6mm FR-4, 1oz copper, per `STACKUP` in `build_pcb.py` | 5 pcs | ~$8.00 |
| | | | **PCB Total** | **~$28.00** |

## Cost Summary

Grouped by the two products this project actually builds.

| Module | Cost (USD) |
|---|---|
| **Terminal** | |
| Board 2 — Main Board | ~$13.45 |
| Display & Input | ~$50.70 |
| Power System | ~$10.70 |
| Enclosure (clamshell) | ~$21.50 |
| Board 2 fabrication | ~$8.00 |
| *Terminal subtotal* | *~$104.35* |
| **PLC Adapter** | |
| Board 1 — PLC / Power | ~$21.37 |
| Non-PCB parts (plug, enclosure) | ~$4.50 |
| Board 1 fabrication | ~$20.00 |
| *Adapter subtotal* | *~$45.87* |
| **TOTAL (single prototype, one of each)** | **~$150.22** |

REV 0.4 totaled ~$135.80 and the top-level README separately claimed ~$112;
REV 0.8 corrected those to ~$166.65. That figure did not survive either — it
counted the PLC Adapter twice, once as Board 1's line items and again as a
parallel "PLC Adapter" bill, plus a 70×60mm PCB that does not exist. Removing
the duplicate takes $14.60 of parts and $5.00 of fabrication off; adding the
five components Board 1's schematic has but its BOM never listed (ESP32-C3,
AMS1117-3.3, 8MHz crystal, 3 status LEDs, 2 programming headers) puts $1.80
back, and pricing `J1` as the real part plus the mating plug it needs adds
another $1.37 over the header it replaced. Net: **~$150.22**.

The display module remains the single largest line at $32.00 — more than
either PCB and its parts.

Every subtotal in this file equals the sum of its own line items, and the
total equals the sum of the subtotals.

**Note:** Costs are single-unit retail estimates. Volume pricing significantly reduces cost (per-unit ratios carried over from REV 0.4's estimate, rescaled to this total):

- 10 units → ~$118/unit
- 100 units → ~$77/unit
- 1000 units → ~$47/unit

## Where To Source

| Supplier | What To Buy |
|---|---|
| LCSC | All ICs, passives, connectors (China, fast shipping) |
| JLCPCB | PCB fabrication + optional SMT assembly |
| AliExpress | Enclosure parts, mechanical parts — **not** battery cells (see note) |
| 18650 cells | 18650BatteryStore, Illumn, or another dedicated protected-cell reseller — avoid generic marketplace listings specifically for cells; "8000mAh 18650" listings are essentially always counterfeit/overrated, real cells top out around 3500mAh per cell |
| Mouser | ST7580 (official distributor), DS3231, protection ICs, RA8875 display modules |
| DigiKey | Alternative for all major ICs |

## Design Notes — REV History

REV 0.5 replaces five REV 0.4 choices that didn't survive a component-level
review — each one reproducible from the datasheet/module spec, not a
judgment call:

1. **Display driver couldn't produce the specified resolution.** ILI9488 tops
   out at 480×320; the spec called for 800×480. Even a corrected driver IC
   needed a second property the GD32VF103 doesn't have: an LTDC/RGB display
   peripheral, or enough RAM (800×480 at 8bpp is 384KB — more than the 32KB
   on-chip RAM and the 128KB external SPI SRAM combined) to hold a frame
   buffer itself. Fix: an RA8875-based module, which ships with its own
   onboard SDRAM and talks to the host MCU over SPI a command/pixel stream
   at a time — the standard way small MCUs drive displays too large to
   buffer themselves.
2. **Wi-Fi module variant had no connector for the antenna next to it in the
   BOM.** ESP32-C3-MINI-1 has an onboard PCB antenna and no external-antenna
   connector at all; ESP32-C3-MINI-1U (same pinout/footprint) has the
   antenna jack the SMA connector needs something to plug into. Fix: swap
   the module, add the missing pigtail. (REV 0.5 called that jack "U.FL"
   and specified a U.FL pigtail and an edge-mount SMA to go with it. All
   three were wrong — see the REV 0.6 note below.)
3. **MCU flash size in the top-level README (1MB) doesn't exist in this chip
   family** — GD32VF103's real ceiling is 256KB, still in a pin-compatible
   part (CCT6 vs. the original CBT6's 128KB). Fixed the BOM to the real part
   and the README to the real number, rather than chasing a spec no variant
   of this MCU can meet.
4. **Battery capacity claim (8000mAh) doesn't match** either the BOM's actual
   2×2500mAh cells (5000mAh) or physical reality for 2 cells of any genuine
   18650 chemistry (would need 4000mAh/cell; real cells top out ~3500mAh).
   Fixed to genuine 3350mAh-class cells (~6700mAh total) — the honest
   ceiling for 2 real cells, and flagged the "8000mAh 18650" claims common
   on general marketplaces as effectively always counterfeit. (The "~5 days
   active use" runtime derived from this capacity was also wrong for
   unrelated reasons — see [`docs/firmware-arch.md`](../docs/firmware-arch.md)'s Power Budget section.)
5. **TrackPoint description said "PS/2 compatible"** (a synchronous serial
   protocol) while [`docs/firmware-arch.md`](../docs/firmware-arch.md)'s own task table already said
   "TrackPoint ADC" (raw analog reads) — these need different firmware and
   different wiring. The part class that's actually sourced for DIY
   keyboard builds is analog/ADC-compatible, matching the firmware doc; only
   the BOM's description was wrong, not the part.
6. **PLC Adapter enclosure sized for a different PCB than the one in its own
   BOM.** Board 1 (the PLC Adapter's PCB) is spec'd at 100×80mm, but the
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
[`hardware/pcb/main-board/README.md`](pcb/main-board/README.md)'s "The antenna path never touched the
board"):

7. **The pigtail was the wrong connector generation.** Section 10.2 specifies
   the module's jack as the third-generation connector — 2.05×1.7×1.40mm,
   compatible with Hirose W.FL, I-PEX MHF III and Amphenol AMC. U.FL /
   MHF I is the first generation, ~2.6mm across, and does not mate with it.
   Every "U.FL" in REV 0.5's Board 2 items and design notes was wrong about
   the part on the module.
8. **The SMA was specified edge-mount, which the pigtail cannot reach.** An
   edge-mount SMA's centre pin is a pad on the PCB, so it has to be fed by
   board copper — and the module has no RF pad to feed it from (Table 3-1:
   53 pads, all GND, 3V3, EN or IO). It is now a bulkhead jack in the
   enclosure wall, which is what a pigtail actually terminates in, and it
   is no longer a PCB part.
9. **There was no antenna in the BOM.** Items 13 and 14 bought a connector and
   a cable to nowhere. Added, with the gain ceiling the module's
   certification depends on (≤2.33 dBi).

Also added two REV 0.4 omissions that would have blocked fabrication
regardless: an explicit crystal for the GD32VF103's clock (was silently
folded into a generic "passives" line with no frequency specified), and a
named component family for the PLC coupling transformer (was a bare "—"
with no part reference at all — still needs confirming against ST7580's
application note before ordering, this isn't a fully closed item).

---

Last updated: 2026 — REV 0.10
