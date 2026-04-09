GRIDNET — Firmware Architecture
Overview
GRIDNET firmware runs on the GD32VF103 (RISC-V) processor using Zephyr RTOS. The ESP32-C3 handles Wi-Fi mesh and Bluetooth as a co-processor, communicating with the main MCU over UART.

Operating System
ParameterValueRTOSZephyr RTOS v3.xArchitectureRISC-V 32-bit (RV32IMAC)Boot time target< 500msBoard definitionCustom GRIDNET BSP (Device Tree)FilesystemLittleFS (power-failure safe)
Boot Sequence
Power on
  → Bootloader (Flash sector 0, never overwritten)
      → Check microSD for gridnet_update.bin
          Found + valid signature → flash new firmware → delete file → continue
          Not found or invalid   → continue normally
  → Zephyr kernel init
  → Device Tree hardware init (GPIO, SPI, I2C, UART)
  → LittleFS mount
  → Channel monitor start
  → UI init → display boot screen
  → READY
Boot screen (Commodore 64 homage):
**** GRIDNET OS V1.0 ****
64K RAM SYSTEM  8192K FLASH  BLUETOOTH 5.0
PLC CHANNEL: ACTIVE [3 NODES FOUND]
WIFI BRIDGE: STANDBY  MICROSD: 32GB

READY.
█

Task Architecture
Tasks listed in priority order (0 = highest):
TaskPriorityStackDescriptionCHANNEL_MONITOR0512BV-Sense ISR, automatic channel switchingPLC_RX11024BST7580 UART interrupt-driven receiveMESH_RX21024BESP32-C3 UART, Wi-Fi packet receiveROUTER32048BRouting table, store-and-forwardKEYBOARD4512BKey matrix scan, TrackPoint ADCUI54096BLCD frame buffer, screen updateBACKGROUND61024BArchive GC, battery monitor, LEDs

Filesystem Layout
LittleFS on 8MB SPI Flash:
/lfs/
├── messages/
│   ├── inbox/        ← received messages
│   ├── outbox/       ← pending delivery (store-and-forward)
│   └── sent/         ← sent messages archive
├── contacts/         ← address book
├── routing/          ← routing table (persisted across reboots)
├── apps/             ← Forth applications (.fth files)
└── config/           ← user settings
microSD (if present):
/sd/
├── apps/             ← additional Forth apps
├── games/            ← game data
├── media/            ← sounds, assets
└── gridnet_update.bin ← firmware update (checked at boot, deleted after flashing)

Forth VM
A minimal sandboxed Forth interpreter runs as part of the UI task.
ParameterValueRAM footprint~2KBStack depth64 cellsDictionary size~8KB FlashMax app size64KB (Flash) or unlimited (microSD)
Security Sandbox
RuleDescriptionAddress lockApp cannot change source addressRate limitMax 5 packets/second per appMessage sizeMax 256 bytes per messageBroadcastRequires explicit BROADCAST permissionFilesystemEach app isolated to /lfs/apps/<app_id>/ScreenLimited to 80×25 character area
App Distribution
Forth apps (.fth files) can be sent peer-to-peer over the network — exactly like BBS-era program sharing. A neighbor shares their market order system, you receive it, it runs locally.

Firmware Update Mechanisms
1. microSD Update (Primary — Recommended)

Download gridnet_update.bin from GitHub releases
Copy to microSD root
Power off terminal, insert microSD, power on
Bootloader detects file, verifies signature, flashes firmware
File is deleted, device boots normally

2. USB-C DFU Update (Secondary)

Hold FN + F12 while powering on → enters DFU mode
Connect USB-C to computer
Run: dfu-util -a 0 -D gridnet_vX.Y.bin
Device reboots automatically

3. Over-the-Air (Optional, future)
OTA updates over the mesh network are technically possible but very slow (~hours for 500KB over PLC). Planned as an optional feature for firmware v2.x.
Signature Verification
All firmware updates are signed. The bootloader verifies the signature before flashing:
cif (!verify_ed25519_signature(firmware_buf, firmware_size, PUBLIC_KEY)) {
    bootloader_halt("Invalid signature — update rejected");
}
The public key is burned into the bootloader at manufacture. Users who build their own firmware can replace the public key.

ESP32-C3 Co-processor
The ESP32-C3 handles Wi-Fi and Bluetooth independently, communicating with GD32VF103 over UART at 115200 baud.
FunctionDescriptionWi-Fi meshESP-NOW based mesh, fallback when PLC unavailableWi-Fi APAccess point for PLC adapter wireless connectionBluetooth 5.0 LEHID profile — wireless keyboard and mouse supportAT command setSimple UART interface to main MCU

Hardware Abstraction
All hardware access goes through Zephyr device drivers defined in the GRIDNET BSP:
boards/riscv/gridnet/
├── gridnet.dts          ← Device Tree (pin assignments, peripherals)
├── gridnet_defconfig    ← Kconfig defaults
├── board.cmake          ← Build system integration
└── support/
    └── openocd.cfg      ← Debug probe configuration

Development Status
ComponentStatusArchitecture design✅ CompleteZephyr BSP / Device Tree📋 Planned — starts after PCB prototypeST7580 PLC driver📋 PlannedLCD driver (ILI9488)📋 PlannedKeyboard / TrackPoint driver📋 PlannedPLC protocol stack📋 PlannedForth VM📋 PlannedWi-Fi mesh (ESP32-C3)📋 PlannedBluetooth HID📋 PlannedFirmware update (microSD + DFU)📋 Planned

Last updated: 2026 — REV 0.4
