<p align="center">
  <img src="media/logo-cyan.svg" width="480">
</p>

# GRIDNET — Powerline Mesh Terminal

> *Communicate over the power grid. No internet. No GSM. No servers.*

[![License: CERN-OHL-W-2.0](https://img.shields.io/badge/Hardware_License-CERN--OHL--W--2.0-blue)](https://ohwr.org/cern_ohl_w_v2.txt)
[![Status: Concept / Design Stage](https://img.shields.io/badge/Status-Design_Stage-yellow)]()
[![Platform: RISC-V](https://img.shields.io/badge/CPU-RISC--V%20GD32VF103-orange)]()
[![OS: Zephyr RTOS](https://img.shields.io/badge/OS-Zephyr_RTOS-green)]()
[![PLC: ST7580](https://img.shields.io/badge/PLC-ST7580_CENELEC-red)]()

---

## What Is GRIDNET?

GRIDNET is an open hardware mesh communication terminal that uses **existing power line infrastructure** as its transmission medium. Plug the adapter into any wall outlet — the terminal connects to your neighborhood network instantly.

No internet required. No cell towers. No central servers. No accounts.

When grid power fails, the adapter runs from the Terminal's battery over a cable you plug in — the wire is still a conductor whether or not it's energised, so the network keeps working. When the wire itself is damaged, Wi-Fi mesh takes over automatically.

```
Normal mode:    [Terminal] ←WiFi→ [PLC Adapter] ←powerline→ [neighbor's adapter] ←WiFi→ [neighbor's Terminal]
Outage mode:    Grid is down — plug the Terminal into the adapter, network stays alive on battery
WiFi fallback:  Wire is damaged — ESP32-C3 mesh activates automatically
```

---

## Why Does This Exist?

Every year, earthquakes, floods, and infrastructure failures cut millions of people off from communication. The internet fails. Cell towers fail. But in most of these scenarios, one thing survives: **the physical power line wiring**.

GRIDNET turns that infrastructure into a resilient local network — inspired by Minitel (France's pre-web national terminal network), FidoNet (a global decentralized BBS built by hobbyists), and the ThinkPad design philosophy (tools built to last).

---

## Hardware Overview

The system consists of two units:

### Terminal
The user-facing device. ThinkPad-inspired clamshell form factor.

| Component | Details |
|---|---|
| **Processor** | GD32VF103CCT6 — RISC-V, 108MHz, 32KB RAM, 256KB Flash |
| **Wireless** | ESP32-C3-MINI-1U — Wi-Fi 2.4GHz mesh + Bluetooth 5.0 LE |
| **Display** | 5.0" TFT LCD, 800×480, RA8875 controller (onboard SDRAM frame buffer), 256 colors, amber-tinted backlight |
| **Keyboard** | 40-key mechanical (Kailh LP), amber LED backlight, red TrackPoint |
| **Right panel** | M1–M4 macro keys + 4×4 numeric keypad + speaker |
| **Speaker** | 1W / 8Ω + PAM8403 amplifier |
| **Storage** | 8MB SPI Flash (LittleFS) + microSD slot |
| **Battery** | 2× 18650, 3350mAh-class genuine cells (~6700mAh total), ~17h active use (screen on) / ~17.5 days standby (screen off, mesh-listen only) — see [`docs/firmware-arch.md`](docs/firmware-arch.md) Power Budget for the full breakdown |
| **Charging** | USB-C, ~4 hours |
| **Antenna** | External, ≤2.33 dBi, on a bulkhead SMA in the case wall — reached by an MHF III / W.FL pigtail from the module's own antenna jack, not by board copper (the module has no RF pad; see [`hardware/pcb/main-board`](hardware/pcb/main-board)) |
| **Dimensions** | 260 × 160 × 28mm, ~680g |
| **OS** | Zephyr RTOS, custom RISC-V BSP |

### PLC Adapter
Separate unit. Plugs directly into any wall outlet (Schuko). Connects to terminal over Wi-Fi — no cables in normal use; during a grid outage the user plugs a USB-C cable in to power it from the Terminal's battery. Replaceable independently.

| Component | Details |
|---|---|
| **PLC SoC** | ST7580 — CENELEC EN50065, OFDM/FSK (band selection under review, see [`docs/electrical-safety.md`](docs/electrical-safety.md)) |
| **Wireless** | ESP32-C3 — Wi-Fi AP for terminal connection |
| **Outage power** | USB-C inlet from the Terminal's battery + 1F supercapacitor hold-up |
| **PLC supply** | MT3608 boost, 5V → 12V for the ST7580's power amplifier |
| **Protection** | TVS P6KE250CA + MOV S20K275 (2 layers; the relay/optocoupler layer went with the inverter) |
| **Power** | HLK-5M05 SMPS, 230VAC → 5VDC |
| **Indicators** | 3× LED: Power / PLC / Wi-Fi |

**Prototype BOM cost: ~$152 USD** (single unit, retail component pricing — see [`hardware/bom.md`](hardware/bom.md) REV 0.5 for the full breakdown and why this went up from the original ~$112 estimate)

---

## Architecture

### Communication Stack

```
┌─────────────────────────────────────────┐
│           APPLICATION LAYER             │
│   Messaging / Games / Forth Apps        │
├─────────────────────────────────────────┤
│           ROUTING LAYER                 │
│   Store-and-forward, 7-day retention    │
│   Mesh routing, automatic repeating     │
├─────────────────────────────────────────┤
│           CHANNEL LAYER                 │
│   Priority 1: Powerline (PLC)           │
│   Priority 2: Wi-Fi Mesh (wire damaged) │
├─────────────────────────────────────────┤
│           PHYSICAL LAYER                │
│   ST7580 OFDM/FSK, EN 50065-1 limited   │
│   ESP32-C3 Wi-Fi 2.4GHz                 │
└─────────────────────────────────────────┘
```

### Packet Format

```
[AA AA AA][55][LEN 2B][SRC 4B][DST 4B][SEQ 2B][TYPE 1B][PAYLOAD][CRC16 2B]
 preamble  sync  len    source   dest    seq     type     data      checksum
```

### Addressing

Hierarchical 4-byte address — no central registry required:

```
[CITY 1B][DISTRICT 1B][BUILDING 1B][UNIT 1B]
  01         03           07          12       →  01.03.07.12
```

### Outage Operation

The wire is a conductor whether or not the grid is energising it, so PLC
signalling works during an outage. What stops is the adapter's own power:
it runs from mains, and there is no battery inside it.

So during an outage the adapter runs from the Terminal's battery over a
USB-C cable the user connects. A supercapacitor in the adapter holds it up
long enough to tell the Terminal that mains has gone, so the Terminal can
prompt for the cable. Roughly 5–6 hours of operation with the screen on,
~9 hours with it off.

Nothing is injected onto the wire, and there is no arbitration between
adapters — every node transmits normally under CSMA/CA, exactly as it does
when the grid is up.

Earlier revisions specified a 24V "inverter mode" here instead. It was
removed: it could never have run (the adapter had no power source during
an outage) and it sat 5–24× outside EN 50065-1's signal limits. See
[`docs/plc-adapter-power.md`](docs/plc-adapter-power.md) for the full
analysis, and [`docs/electrical-safety.md`](docs/electrical-safety.md) for
the compliance correction.

### Software Architecture

- **RTOS:** Zephyr (RISC-V support, tickless idle, LittleFS)
- **Boot time:** < 500ms target
- **Tasks:** CHANNEL_MONITOR (0) → PLC_RX (1) → MESH_RX (2) → ROUTER (3) → KEYBOARD (4) → UI (5) → BACKGROUND (6)
- **Filesystem:** LittleFS on 8MB Flash + microSD

Boot screen (Commodore 64 homage):
```
**** GRIDNET OS V1.0 ****
64K RAM SYSTEM  8192K FLASH  BLUETOOTH 5.0
PLC CHANNEL: ACTIVE [3 NODES FOUND]
WIFI BRIDGE: STANDBY  MICROSD: 32GB

READY.
█
```

### Forth VM — Application Platform

Users write and share applications in a sandboxed Forth interpreter (~2KB RAM). Apps are distributed peer-to-peer over the network — like the BBS era.

Security constraints: source address lock, rate limit (5 packets/sec), max 256 bytes/message, filesystem isolation per app.

Example — local market order system in ~15 lines (verified against the
reference VM in [`tools/forth-vm`](tools/forth-vm) — see that directory's
README for why `S"` and `KEY? IF KEY ...` are used instead of the shorter
but non-functional `"` / `KEY? SEND-MSG` you might expect):
```forth
: HEADER
  0 0 S" ╔═══════════════╗" WRITE
  0 1 S" ║  CORNER SHOP  ║" WRITE
  0 2 S" ╚═══════════════╝" WRITE ;

: ORDER
  HEADER
  0 4 S" 1. Bread  2. Milk" WRITE
  KEY? IF KEY S" 01.03.07.99" SEND-MSG THEN ;

: MAIN BEGIN ORDER 1000 WAIT AGAIN ;
MAIN
```

---

## Electrical Safety

GRIDNET puts a low-voltage signal on the mains through a transformer. It does not energise the wire.

- **Signal level is bounded by EN 50065-1**: 5 Vrms at 9 kHz falling to 1 Vrms at 95 kHz. The ST7580's power amplifier delivers 14 V p-p (4.95 Vrms) — ST sized the part to land on that limit — and the adapter adds a hardware current limit as a backstop.
- **PLC signals sit at 95–148.5 kHz**, roughly 2000–3000× the grid frequency. Every household power supply filters that band out; the signal is invisible to their power circuits. Same principle as HomePlug and smart metering, deployed in millions of homes for two decades.
- **Galvanic isolation is mandatory and load-bearing.** The ST7580 reaches the line only through the coupling transformer, and the HLK-5M05 is an isolated supply. The USB-C cable to the Terminal sits on that isolated secondary — the user handles it while the adapter is in a wall socket, so this barrier is what stands between them and the mains.
- **Two protection layers**: TVS (P6KE250CA) for transients, MOV (S20K275) for sustained overvoltage.

⚠️ **One open compliance item**: the A-band (9–95 kHz) is allocated to electricity suppliers, and a project like this belongs in 95–148.5 kHz. `docs/protocol.md` still specifies A-band throughout and needs updating. See [`docs/electrical-safety.md`](docs/electrical-safety.md) REV 0.6, which corrects an earlier claim in this project that a 24V injection was within EN 50065 limits. It was not.

---

## Use Cases

| Scenario | Description |
|---|---|
| 🏚 Disaster response | Coordinate with neighbors when grid, internet, and cell are all down |
| 🏘 Neighborhood messaging | Hyperlocal communication without internet subscriptions |
| 🛒 Local commerce | Shops write their own order systems in Forth — no cloud, no monthly fee |
| 🎮 Games | Turn-based strategy and text adventures played over the power grid |
| 🔒 Privacy | No accounts, no logs, no cloud. Messages exist only in the devices they pass through |
| 👾 Retro / Hacker | Amber display, mechanical keyboard, Forth VM, RISC-V. It boots to READY. |

---

## Project Status

| Component | Status |
|---|---|
| Hardware architecture (dual-board design) | ✅ Complete |
| Communication protocol stack | ✅ Complete |
| PLC Adapter power architecture ([`docs/plc-adapter-power.md`](docs/plc-adapter-power.md)) | ✅ Complete — adapter runs off the Terminal's battery during an outage; the 24V inverter and its master-election protocol were removed (never able to run, and outside EN 50065-1) |
| Protection circuit topology (TVS + MOV + relay) | ✅ Complete — topology and parts selected ([`hardware/bom.md`](hardware/bom.md)); not yet a drawn schematic |
| Main Board schematic + PCB layout ([`hardware/pcb/main-board`](hardware/pcb/main-board)) | ✅ Complete — custom parts datasheet-verified, PCB placed, routed, ground-poured on both layers, DRC clean (0 violations, 0 unconnected). REV 0.7 was a pre-fab design review that caught a refdes-drift bug placing parts in each other's positions (crystal load caps 51mm from the crystal), a boost-converter switching loop spread across 63mm, and every trace at 0.2mm including a 2.4A path. REV 0.8 found the antenna path was fiction — a phantom U.FL duplicating the module's own jack, a trace nothing could drive, and an invented `ANT` symbol pin — and that the "grid of stitching vias" was nine vias in one column, because `BOX2I.Inflate()` mutates in place (now 167, worst-case return path 55mm → 16.8mm) — see that directory's README |
| PLC/Power Board (BOM's Board 1, the PLC Adapter's PCB — see [`hardware/pcb/plc-board`](hardware/pcb/plc-board)) | 🔄 REV 0.2, ERC-clean. Power architecture now complete: Terminal USB-C inlet, Schottky ORing, supercapacitor hold-up, 5V→12V boost feeding the ST7580's `VCC`, and its hardware transmit-current limit. One gap left — the PA output network and coupling transformer, which need ST's AN4068 reference circuit rather than a guess. No PCB layout yet. |
| Case design (CAD) | 📋 Planned — only target external dimensions exist (see Hardware Overview); no CAD model |
| Software architecture (Zephyr + Forth VM) | ✅ Complete |
| Electrical safety analysis | ✅ Complete |
| Protocol & Forth VM reference prototypes ([`tools/`](tools/), Python, pre-hardware validation) | ✅ Complete |
| **PCB fabrication / Hardware prototype** | 🔄 Next step — Main Board has been through two design-review passes and is DRC-clean. RF layout is no longer on its list: there is no RF net on the board (the antenna is a cable assembly from the module's own jack). What is left before fab is a stackup decision, a return-path review of the SPI/I2C buses, and a human eye on the autorouted copper (see [`hardware/pcb/main-board`](hardware/pcb/main-board) "What's not done yet"). Board 1 needs its PA output network and coupling transformer (blocked on ST's AN4068) before its own layout can start meaningfully |
| Embedded firmware (Zephyr, on real hardware) | 📋 Planned — starts after PCB prototype |
| Field testing | 📋 Planned |

---

## Repository Structure

```
gridnet/
├── README.md
├── LICENSE                    (CERN-OHL-W-2.0)
├── CONTRIBUTING.md
├── hardware/
│   ├── pcb/
│   │   ├── main-board/         (Board 2 — KiCad schematic + routed, ground-poured PCB, see its README)
│   │   └── plc-board/          (Board 1 — KiCad schematic, no PCB layout yet, see its README)
│   └── bom.md                 (bill of materials)
├── docs/
│   ├── protocol.md            (full protocol stack)
│   ├── firmware-arch.md       (Zephyr + Forth VM)
│   ├── electrical-safety.md   (CENELEC compliance)
│   └── plc-adapter-power.md   (adapter power architecture + EN 50065 analysis)
├── firmware/
│   └── README.md              (planned structure — embedded firmware not started)
├── tools/
│   ├── protocol-sim/          (Python reference implementation of docs/protocol.md)
│   └── forth-vm/              (Python prototype of the sandboxed Forth VM)
└── media/
    ├── logo-cyan.svg
    └── logo-silver.svg
```

Note: `hardware/case/` and `hardware/schematics/` (now just a pointer to
`hardware/pcb/`) aren't in the tree above because there's nothing under
either yet worth listing — see the Project Status table above.

---

## Looking For

- Hardware engineer with embedded systems / PCB experience
- Anyone with real-world ST7580 / PLC field experience
- Zephyr RTOS developers (RISC-V BSP, driver development)
- Forth enthusiasts — help design the VM standard library
- Beta testers willing to run a node in their building

Open an Issue or email directly if you're interested in collaborating.

---

## Inspiration

**Minitel** — France's pre-web national terminal network. A whole country connected, locally, before the internet existed.

**FidoNet** — A global decentralized BBS network built by hobbyists. Store-and-forward over phone lines. No servers. No company.

**ThinkPad** — A design philosophy: every detail intentional, built to last, keyboard first.

---

## License

Hardware designs and documentation: [CERN Open Hardware Licence v2 — Weakly Reciprocal (CERN-OHL-W-2.0)](https://ohwr.org/cern_ohl_w_v2.txt)

Firmware (when released): GPL-3.0

© 2026 Yasar — Open Hardware Project
