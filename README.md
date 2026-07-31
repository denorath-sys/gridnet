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

**Prototype BOM cost: ~$149.25 USD** for one Terminal plus one Adapter — ~$104.35 and ~$44.90 respectively (single unit, retail component pricing). See [`hardware/bom.md`](hardware/bom.md) REV 0.9 for the full breakdown, including why the earlier ~$112 and ~$166.65 figures were both wrong.

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

⚠️ **One open compliance item**: no EN 50065-1 conformance claim is justified until a conducted-emission sweep is run on a prototype. The band allocation itself is settled — the A-band (9–95 kHz) is reserved for electricity suppliers, so GRIDNET uses B (95–125 kHz) and C (125–140 kHz), and the hardware commits to that choice through Board 1's coupling network ([`docs/plc-coupling.md`](docs/plc-coupling.md), [`docs/protocol.md`](docs/protocol.md)). What remains is the measurement, which needs hardware that does not exist yet. See [`docs/electrical-safety.md`](docs/electrical-safety.md) REV 0.6, which also corrects an earlier claim in this project that a 24V injection was within EN 50065 limits. It was not.

---

## Use Cases

| Scenario | Description |
|---|---|
| 🏚 Disaster response | Coordinate with neighbors when grid, internet, and cell are all down |
| 🏘 Neighborhood messaging | Hyperlocal communication without internet subscriptions |
| 🛒 Local commerce | Shops write their own order systems in Forth — no cloud, no monthly fee |
| 🎮 Games | Turn-based strategy and text adventures played over the power grid |
| 🔒 No cloud | No accounts, no logs, no servers — nothing leaves the neighbourhood. Note that this is *not* the same as confidentiality: the protocol has no encryption yet, and store-and-forward means a message can sit in a relaying neighbour's device for up to 7 days in plaintext. See "Known Gaps" below |
| 👾 Retro / Hacker | Amber display, mechanical keyboard, Forth VM, RISC-V. It boots to READY. |

---

## Project Status

| Component | Status |
|---|---|
| Hardware architecture (dual-board design) | ✅ Complete |
| Communication protocol stack | ✅ Complete |
| PLC Adapter power architecture ([`docs/plc-adapter-power.md`](docs/plc-adapter-power.md)) | ✅ Complete — adapter runs off the Terminal's battery during an outage; the 24V inverter and its master-election protocol were removed (never able to run, and outside EN 50065-1) |
| Protection circuit (TVS + MOV) | ✅ Complete — two layers, not three: the relay/optocoupler layer went with the inverter. Parts selected ([`hardware/bom.md`](hardware/bom.md)) and now drawn — `P6KE250CA` and `S20K275` are in Board 1's schematic and placed on its PCB |
| Main Board schematic + PCB layout ([`hardware/pcb/main-board`](hardware/pcb/main-board)) | ✅ Complete — custom parts datasheet-verified, PCB placed, routed, ground-poured on both layers, DRC clean (0 violations, 0 unconnected). REV 0.7 was a pre-fab design review that caught a refdes-drift bug placing parts in each other's positions (crystal load caps 51mm from the crystal), a boost-converter switching loop spread across 63mm, and every trace at 0.2mm including a 2.4A path. REV 0.8 found the antenna path was fiction — a phantom U.FL duplicating the module's own jack, a trace nothing could drive, and an invented `ANT` symbol pin — and that the "grid of stitching vias" was nine vias in one column, because `BOX2I.Inflate()` mutates in place (now 167, worst-case return path 55mm → 16.8mm) — see that directory's README |
| PLC/Power Board (BOM's Board 1, the PLC Adapter's PCB — see [`hardware/pcb/plc-board`](hardware/pcb/plc-board)) | ✅ REV 0.3 schematic complete, ERC-clean (350 warnings, 0 errors). Power architecture: Terminal USB-C inlet, Schottky ORing, supercapacitor hold-up, 5V→12V boost feeding the ST7580's `VCC`, hardware transmit-current limit. Line coupling now built too — transmit active filter around the ST7580's own PA, receive resonant filter, and the coupling transformer into the mains. Topology from ST's AN4068, values rescaled from its A-band reference design to GRIDNET's 95–140 kHz band ([`docs/plc-coupling.md`](docs/plc-coupling.md)). PCB placement complete (REV 0.5), now a **four-layer** board: L1/L4 signals, In1.Cu GND plane, In2.Cu +5V plane. Four layers because the ST7580's nine +5V pads on a 48-pin 0.5mm-pitch package need a plane, and two two-layer copper layers are already spoken for by ground and the mains barrier — see that directory's README for the four runs that established it. The 7.96mm isolation barrier cuts all four layers and only the AC-DC module and the coupling transformer cross it; verified geometrically on every pad, track, via and filled zone. Routing (REV 0.6) runs end to end: the autorouter gets 174 nets to 4-10 and the repair step closes most of the rest, but every attempt ends holding exactly one connection. Six defects were fixed getting there — QFN power fanout, pour-before-repair ordering, netclass-aware repair, a mains column too narrow for its own clearance rule, a keepout halo that made a pad unroutable, and a footprint hanging off the board edge. |
| Case design (CAD) | 📋 Planned — only target external dimensions exist (see Hardware Overview); no CAD model |
| Software architecture (Zephyr + Forth VM) | ✅ Complete |
| Electrical safety analysis | ✅ Complete |
| Protocol & Forth VM reference prototypes ([`tools/`](tools/), Python, pre-hardware validation) | ✅ Complete |
| **PCB fabrication / Hardware prototype** | 🔄 Next step — Main Board has been through two design-review passes and is DRC-clean. RF layout is no longer on its list: there is no RF net on the board (the antenna is a cable assembly from the module's own jack). The stackup is no longer an open decision — it is now `STACKUP` in `build_pcb.py` (1.6mm FR-4, two layers, 1oz copper) and written into the board's own design rules, which turned up that KiCad's manufacturing minimums had been left at zero all along: every "0 violations" this project reported before that had been measured against no process limit at all. The board passes the real rules unchanged. What is left before fab is a return-path review of the SPI/I2C buses and a human eye on the autorouted copper (see [`hardware/pcb/main-board`](hardware/pcb/main-board) "What's not done yet"). Board 1 is further along than "schematic complete" — it is placed, four-layer, and routed end to end but for a single connection every attempt ends holding (REV 0.6). Before it is fabricated it needs that last net closed and the mains creepage/clearance treatment the Main Board never required; before any EN 50065-1 claim it needs a conducted-emission sweep |
| Embedded firmware (Zephyr, on real hardware) | 📋 Planned — starts after PCB prototype |
| Field testing | 📋 Planned |

---

## Known Gaps

Things this design does not currently do. They are listed here rather than
left for a reader to discover, because two of them affect whether the
network can be trusted in the situation it exists for.

**There is no message authentication.** `SRC` is a plaintext field in the
packet header, and on a shared broadcast medium any node can set it to any
value. The sandbox rule in [`docs/protocol.md`](docs/protocol.md) —
"source address locked, app cannot spoof sender" — constrains a Forth app
running on its own device; it says nothing about a modified node. The
consequences follow directly:

- **ROUTE poisoning.** The routing layer is distance-vector with no
  authentication, so any node can advertise `hop_count 0` for an address it
  does not own and pull that traffic to itself.
- **Forged emergency broadcasts.** `BROADCAST 0x03` is flooded to the whole
  mesh and signed by nothing.
- **Storage exhaustion.** Store-and-forward holds messages for 7 days on
  behalf of unauthenticated senders.
- **Unverified code distribution.** `APP_DATA 0x10` moves Forth applications
  peer-to-peer, from peers whose identity is not established.

Firmware updates *are* signed — Ed25519, verified by the bootloader
([`docs/firmware-arch.md`](docs/firmware-arch.md)). The network layer has
no equivalent. Closing that gap is a design task that has not been started,
and there is no threat model document yet.

**Duplicate addresses are not detected.** Addresses are self-assigned with
no registry, and `docs/protocol.md` currently attributes collision
detection to CSMA/CA. That is a media-access mechanism — it detects a busy
channel, not two nodes claiming `01.03.07.12`. Nothing in the protocol
notices the duplicate, and the routing table oscillates when it happens.

**No encryption.** Message contents are plaintext on the wire and plaintext
in every relaying device's store-and-forward queue.

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
│   │   └── plc-board/          (Board 1 — KiCad schematic + placed PCB, see its README)
│   └── bom.md                 (bill of materials)
├── docs/
│   ├── protocol.md            (full protocol stack)
│   ├── firmware-arch.md       (Zephyr + Forth VM)
│   ├── electrical-safety.md   (CENELEC compliance)
│   ├── plc-adapter-power.md   (adapter power architecture + EN 50065 analysis)
│   └── plc-coupling.md        (line coupling network: AN4068 retuned for B+C)
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
