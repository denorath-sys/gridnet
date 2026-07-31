# GRIDNET — Firmware Architecture

## Overview

GRIDNET firmware runs on the GD32VF103 (RISC-V) processor using Zephyr RTOS. The ESP32-C3 handles Wi-Fi mesh and Bluetooth as a co-processor, communicating with the main MCU over UART.

## Operating System

| Parameter | Value |
|---|---|
| RTOS | Zephyr RTOS v3.x |
| Architecture | RISC-V 32-bit (RV32IMAC) |
| Boot time target | < 500ms |
| Board definition | Custom GRIDNET BSP (Device Tree) |
| Filesystem | LittleFS (power-failure safe) |

## Boot Sequence

```
Power on
  → Bootloader (Flash sector 0, never overwritten)
      → Check microSD for gridnet_update.bin
          Found + valid signature → flash new firmware → delete file → continue
          Not found or invalid    → continue normally
  → Zephyr kernel init
  → Device Tree hardware init (GPIO, SPI, I2C, UART)
  → LittleFS mount
  → Channel monitor start
  → UI init → display boot screen
  → READY
```

Boot screen (Commodore 64 homage — `64K RAM SYSTEM` is quoted from the C64,
not this device's memory; the GD32VF103CCT6 has 32KB):

```
**** GRIDNET OS V1.0 ****
64K RAM SYSTEM  8192K FLASH  BLUETOOTH 5.0
PLC CHANNEL: ACTIVE [3 NODES FOUND]
WIFI BRIDGE: STANDBY  MICROSD: 32GB

READY.
█
```

## Task Architecture

Tasks listed in priority order (0 = highest):

| Task | Priority | Stack | Description |
|---|---|---|---|
| CHANNEL_MONITOR | 0 | 512B | V-Sense ISR, automatic channel switching |
| PLC_RX | 1 | 1024B | ST7580 UART interrupt-driven receive |
| MESH_RX | 2 | 1024B | ESP32-C3 UART, Wi-Fi packet receive |
| ROUTER | 3 | 2048B | Routing table, store-and-forward |
| KEYBOARD | 4 | 512B | Key matrix scan, TrackPoint ADC |
| UI | 5 | 4096B | LCD draw commands over SPI to the RA8875 (which holds the actual frame buffer in its own onboard SDRAM), screen update |
| BACKGROUND | 6 | 1024B | Archive GC, battery monitor, LEDs |

## Filesystem Layout

LittleFS on 8MB SPI Flash:

```
/lfs/
├── messages/
│   ├── inbox/        ← received messages
│   ├── outbox/       ← pending delivery (store-and-forward)
│   └── sent/         ← sent messages archive
├── contacts/         ← address book
├── routing/          ← routing table (persisted across reboots)
├── apps/             ← Forth applications (.fth files)
└── config/           ← user settings
```

microSD (if present):

```
/sd/
├── apps/             ← additional Forth apps
├── games/            ← game data
├── media/            ← sounds, assets
└── gridnet_update.bin ← firmware update (checked at boot, deleted after flashing)
```

## Forth VM

A minimal sandboxed Forth interpreter runs as part of the UI task.

| Parameter | Value |
|---|---|
| RAM footprint | ~2KB |
| Stack depth | 64 cells |
| Dictionary size | ~8KB Flash |
| Max app size | 64KB (Flash) or unlimited (microSD) |

### Security Sandbox

| Rule | Description |
|---|---|
| Address lock | App cannot change source address |
| Rate limit | Max 5 packets/second per app |
| Message size | Max 256 bytes per message |
| Broadcast | Requires explicit BROADCAST permission |
| Filesystem | Each app isolated to `/lfs/apps/<app_id>/` |
| Screen | Limited to 80×25 character area |

These rules bound what an application can do on the device running it. They
are not a network security model — nothing here authenticates a *remote*
sender, because the protocol has no authentication at all. See
[`protocol.md`](protocol.md) "Security — What Is Not Protected".

A Python prototype of this VM — language core plus the `WRITE`/`KEY`/`KEY?`/`SEND-MSG` words and every sandbox rule above except filesystem isolation (nothing to isolate yet, no file words exist in the prototype) — lives at [`tools/forth-vm/`](../tools/forth-vm/), validated against the corner-shop example in the top-level README (it actually runs there now, including the `BEGIN...AGAIN` main loop).

## App Distribution

Forth apps (`.fth` files) can be sent peer-to-peer over the network — exactly like BBS-era program sharing. A neighbor shares their market order system, you receive it, it runs locally.

The sending peer is not authenticated. Unlike firmware updates (below), a
received application carries no signature and nothing establishes where it
actually came from.

## Firmware Update Mechanisms

### 1. microSD Update (Primary — Recommended)

1. Download `gridnet_update.bin` from GitHub releases
2. Copy to microSD root
3. Power off terminal, insert microSD, power on
4. Bootloader detects file, verifies signature, flashes firmware
5. File is deleted, device boots normally

### 2. USB-C DFU Update (Secondary)

1. Hold `FN + F12` while powering on → enters DFU mode
2. Connect USB-C to computer
3. Run: `dfu-util -a 0 -D gridnet_vX.Y.bin`
4. Device reboots automatically

### 3. Over-the-Air (Optional, future)

OTA updates over the mesh network are technically possible but very slow (~hours for 500KB over PLC). Planned as an optional feature for firmware v2.x.

### Signature Verification

All firmware updates are signed. The bootloader verifies the signature before flashing:

```c
if (!verify_ed25519_signature(firmware_buf, firmware_size, PUBLIC_KEY)) {
    bootloader_halt("Invalid signature — update rejected");
}
```

The public key is burned into the bootloader at manufacture. Users who build their own firmware can replace the public key.

This is currently the only authenticated path in the whole system.

## ESP32-C3 Co-processor

The ESP32-C3 handles Wi-Fi and Bluetooth independently, communicating with GD32VF103 over UART at 115200 baud.

| Function | Description |
|---|---|
| Wi-Fi mesh | ESP-NOW based mesh, fallback when PLC unavailable |
| Wi-Fi AP | Access point for PLC adapter wireless connection |
| Bluetooth 5.0 LE | HID profile — wireless keyboard and mouse support |
| AT command set | Simple UART interface to main MCU |

## Hardware Abstraction

All hardware access goes through Zephyr device drivers defined in the GRIDNET BSP:

```
boards/riscv/gridnet/
├── gridnet.dts          ← Device Tree (pin assignments, peripherals)
├── gridnet_defconfig    ← Kconfig defaults
├── board.cmake          ← Build system integration
└── support/
    └── openocd.cfg      ← Debug probe configuration
```

## Power Budget (REV 0.6)

The Channel Layer figures in [`protocol.md`](protocol.md) (~58/260/138mA) describe the
PLC Adapter's mains-powered channel-switching current, not the
battery-powered Terminal's total draw — the Terminal has no PLC SoC at all
(see "ESP32-C3 Co-processor" above) and always talks to its adapter, or to
other terminals in mesh fallback, over WiFi. An earlier revision of this
project used those channel-layer numbers as a stand-in for the Terminal's
whole-device battery life, which left out its two biggest continuous
loads entirely: the TFT backlight and the keyboard backlight.

Recomputed here from typical datasheet-class figures for the actual named
parts (see [`hardware/bom.md`](../hardware/bom.md)) — not measurements, since no hardware
exists yet to measure:

**Active use** (screen on, WiFi connected with mesh traffic, keyboard backlight on)

| Component | Current |
|---|---|
| MCU (GD32VF103CCT6 @108MHz, active) | 45mA |
| ESP32-C3 WiFi mesh, connected + traffic (avg) | 90mA |
| RA8875 controller (driving display) | 30mA |
| TFT backlight (5", mid brightness) | 150mA |
| Keyboard backlight (40× amber LED, multiplexed) | 30mA |
| Misc (RTC, SPI flash/SRAM idle, TrackPoint, µSD idle) | 10mA |
| **TOTAL** | **355mA** |

**Standby** (screen off, mesh-listen only)

| Component | Current |
|---|---|
| MCU (Zephyr tickless idle) | 3mA |
| ESP32-C3 WiFi modem/light-sleep (periodic mesh check) | 8mA |
| Display: OFF | 0mA |
| Keyboard backlight: OFF | 0mA |
| Misc (RTC, idle peripherals) | 3mA |
| **TOTAL** | **14mA** |

Runtime, at 6700mAh ([`hardware/bom.md`](../hardware/bom.md)) and ~88% typical
boost-converter efficiency (IP5306-class):

- Active use: ~16.6 hours (~0.7 days) — not the "~5 days active use" the
  top-level README claimed before this revision.
- Standby (screen off): ~421 hours (~17.5 days).

A multi-day runtime figure is physically real for this battery — just only
in the low-power standby/mesh-listening state, not with the screen on and
in active use. The two states differ by roughly 25×, which is the number
worth remembering here; the absolute mA figures are estimates that will
shift once real firmware power management (backlight PWM level, WiFi sleep
duty-cycling, MCU sleep aggressiveness) exists to measure against — none of
that has been written yet.

## Development Status

| Component | Status |
|---|---|
| Architecture design | ✅ Complete |
| Zephyr BSP / Device Tree | 📋 Planned — starts after PCB prototype |
| ST7580 PLC driver | 📋 Planned |
| LCD driver (RA8875) | 📋 Planned — see `hardware/bom.md` REV 0.5 history: ILI9488 (REV 0.4) doesn't support this display's 800×480 resolution |
| Keyboard / TrackPoint driver | 📋 Planned |
| PLC protocol stack | 📋 Planned |
| Forth VM | 📋 Planned |
| Wi-Fi mesh (ESP32-C3) | 📋 Planned |
| Bluetooth HID | 📋 Planned |
| Firmware update (microSD + DFU) | 📋 Planned |
| Message authentication | ❌ Not designed — see [`protocol.md`](protocol.md) "Security — What Is Not Protected" |

---

Last updated: 2026 — REV 0.7
