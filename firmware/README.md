GRIDNET — Firmware

Status: In Development
Firmware development begins after hardware prototype is complete and validated.


Planned Structure
firmware/
├── README.md              ← this file
├── CMakeLists.txt         ← Zephyr build system
├── prj.conf               ← Kconfig project configuration
├── boards/
│   └── gridnet/           ← Custom Zephyr BSP
│       ├── gridnet.dts    ← Device Tree
│       ├── gridnet_defconfig
│       └── board.cmake
├── src/
│   ├── main.c             ← Entry point, task init
│   ├── plc/               ← ST7580 driver + protocol stack
│   ├── mesh/              ← Wi-Fi mesh (ESP32-C3 interface)
│   ├── router/            ← Mesh routing, store-and-forward
│   ├── ui/                ← LCD driver, screen rendering
│   ├── keyboard/          ← Key matrix, TrackPoint
│   ├── forth/             ← Forth VM + sandbox
│   ├── storage/           ← LittleFS + microSD
│   └── channel/           ← Automatic channel switching
└── bootloader/
    ├── main.c             ← Bootloader (microSD + DFU update)
    └── crypto/            ← Ed25519 signature verification

Build Requirements

Zephyr RTOS v3.x
West (Zephyr build tool)
RISC-V GCC toolchain
Optional: OpenOCD (JTAG debug)


Contributing
If you have experience with Zephyr RTOS, RISC-V, or ST7580 PLC and want to contribute, please open an Issue or see CONTRIBUTING.md.

See docs/firmware-arch.md for full architecture documentation.
