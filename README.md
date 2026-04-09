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

When grid power fails, an onboard inverter injects 24V AC onto the wire, keeping the network alive. When the wire itself is damaged, Wi-Fi mesh takes over automatically.

```
Normal mode:    [Terminal] ←WiFi→ [PLC Adapter] ←powerline→ [neighbor's adapter] ←WiFi→ [neighbor's Terminal]
Inverter mode:  Grid is down, adapter injects 24V AC — network stays alive
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
| **Processor** | GD32VF103 — RISC-V, 108MHz, 32KB RAM, 1MB Flash |
| **Wireless** | ESP32-C3 — Wi-Fi 2.4GHz mesh + Bluetooth 5.0 LE |
| **Display** | 5.0" STN LCD, 800×480, 256 colors, amber backlight |
| **Keyboard** | 40-key mechanical (Kailh LP), amber LED backlight, red TrackPoint |
| **Right panel** | M1–M4 macro keys + 4×4 numeric keypad + speaker |
| **Speaker** | 1W / 8Ω + PAM8403 amplifier |
| **Storage** | 8MB SPI Flash (LittleFS) + microSD slot |
| **Battery** | 2× 18650, 8000mAh, ~6 days active use |
| **Charging** | USB-C, ~4 hours |
| **Antenna** | SMA connector, external |
| **Dimensions** | 260 × 160 × 28mm, ~680g |
| **OS** | Zephyr RTOS, custom RISC-V BSP |

### PLC Adapter
Separate unit. Plugs directly into any wall outlet (Schuko). Connects to terminal over Wi-Fi — no cables needed inside the home. Replaceable independently.

| Component | Details |
|---|---|
| **PLC SoC** | ST7580 — CENELEC EN50065 A-band, OFDM/FSK, 9–148kHz |
| **Wireless** | ESP32-C3 — Wi-Fi AP for terminal connection |
| **Inverter** | IRF540 × 2 — injects 24V AC when grid fails |
| **Protection** | TVS P6KE250CA + MOV S20K275 + HK19F relay + PC817 optocoupler |
| **Power** | HLK-5M05 SMPS, 230VAC → 5VDC |
| **Indicators** | 3× LED: Power / PLC / Wi-Fi |

**Prototype BOM cost: ~$112 USD** (single unit, retail component pricing)

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
│   Priority 1: PLC (grid on)   ~58mA     │
│   Priority 2: Inverter+PLC    ~260mA    │
│   Priority 3: Wi-Fi Mesh      ~138mA    │
├─────────────────────────────────────────┤
│           PHYSICAL LAYER                │
│   ST7580 OFDM/FSK, CENELEC EN50065      │
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

### Inverter Master Protocol

When grid power fails, only one device per segment injects 24V to prevent voltage conflicts:

```
Grid fails → wait 2s → listen for 24V on wire
  If 24V detected  → passive mode (another device is master)
  If no 24V        → become master, start injecting
Master broadcasts MASTER_ALIVE every 10s
If no MASTER_ALIVE for 30s → lowest-address active device takes over
```

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

Example — local market order system in ~15 lines:
```forth
: HEADER
  0 0 " ╔═══════════════╗" WRITE
  0 1 " ║  CORNER SHOP  ║" WRITE
  0 2 " ╚═══════════════╝" WRITE ;

: ORDER
  HEADER
  0 4 " 1. Bread  2. Milk" WRITE
  KEY? SEND-MSG ;

: MAIN BEGIN ORDER 1000 WAIT AGAIN ;
MAIN
```

---

## Electrical Safety

GRIDNET's 24V AC injection is **safe for all connected household equipment** and compliant with CENELEC EN50065:

- Household devices operate at 230V/50Hz. 24V is irrelevant to their power circuits.
- PLC signals operate at 9–148kHz — 180–3000× the grid frequency. Consumer electronics naturally filter this band.
- Maximum injected current: 100mA. Household circuit breakers trip at 16A.
- IEC 60479: voltages below 50V AC are classified as low-voltage and non-hazardous under normal conditions.
- Galvanic isolation is mandatory — the ST7580 and inverter always connect to the power line through a transformer. No direct connection.

This is the same principle used by HomePlug adapters deployed in millions of homes for over two decades.

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
| Inverter master protocol | ✅ Complete |
| Protection circuit design (TVS + MOV + relay) | ✅ Complete |
| PCB layout plan | ✅ Complete |
| Case design | ✅ Complete |
| Software architecture (Zephyr + Forth VM) | ✅ Complete |
| Electrical safety analysis | ✅ Complete |
| **PCB fabrication / Hardware prototype** | 🔄 Next step |
| Firmware development | 📋 Planned |
| Field testing | 📋 Planned |

---

## Repository Structure

```
gridnet/
├── README.md
├── LICENSE                    (CERN-OHL-W-2.0)
├── CONTRIBUTING.md
├── hardware/
│   ├── schematics/            (board schematics)
│   ├── pcb/                   (PCB layout plan)
│   ├── bom.md                 (bill of materials)
│   └── case/                  (enclosure design)
├── docs/
│   ├── protocol.md            (full protocol stack)
│   ├── firmware-arch.md       (Zephyr + Forth VM)
│   ├── electrical-safety.md   (CENELEC compliance)
│   └── inverter-master.md     (master selection protocol)
├── firmware/
│   └── README.md              (in development)
└── media/
    ├── logo-cyan.svg
    ├── logo-silver.svg
    └── device-render.png
```

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
