GRIDNET — Bill of Materials (BOM)
REV 0.4 — Prototype (Single Unit, Retail Pricing)

Board 1 — PLC / Power Board (100×80mm)
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1PLC SoCST7580CENELEC EN50065, OFDM/FSK, 9–148kHz1$5.70$5.702MOSFETIRF540NN-channel, 100V/33A — DC-AC inverter2$0.80$1.603TVS DiodeP6KE250CABidirectional, 250V — surge protection1$0.60$0.604MOVS20K275275V varistor — overvoltage protection1$0.40$0.405RelayHK19F-DC5V5V coil, 250VAC/10A — line isolation1$0.80$0.806OptocouplerPC817Signal isolation, 5kV2$0.15$0.307SMPS ModuleHLK-5M05230VAC → 5VDC, 1A1$3.50$3.508Coupling transformer—PLC line coupling, 1:1, 9–150kHz1$2.00$2.009Connector J1—2×8 pin, 2.54mm — main board interface1$0.30$0.3010Passive components—Resistors, capacitors, ferrite beads—$1.50$1.50Board 1 Total~$16.70

Board 2 — Main Board (100×80mm)
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1MCUGD32VF103CBT6RISC-V, 108MHz, 32KB RAM, 128KB Flash1$1.50$1.502Wi-Fi / BT ModuleESP32-C3-MINI-1Wi-Fi 2.4GHz mesh + Bluetooth 5.0 LE1$0.80$0.803SRAM23LC10241Mb SPI SRAM1$1.20$1.204FlashW25Q64JVSSIQ8MB SPI NOR Flash1$0.60$0.605RTCDS3231SNI2C RTC, ±2ppm accuracy1$1.80$1.806RTC BatteryCR20323V coin cell1$0.30$0.307LiPo chargerMCP73831Single-cell LiPo charge controller1$0.50$0.508Boost converterIP53065V boost + battery management1$0.60$0.609LDOAMS1117-3.33.3V LDO regulator2$0.15$0.3010AmplifierPAM84033W class-D audio amplifier1$0.40$0.4011microSD socket—SPI, push-push type1$0.50$0.5012USB-C connector—Power input, DFU firmware update1$0.40$0.4013SMA connector—External antenna, edge mount1$0.80$0.8014Passive components—Resistors, capacitors, inductors—$1.50$1.50Board 2 Total~$11.20

Display & Input
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1LCD Display—5.0" STN, 800×480, 256 colors, ILI94881$18.00$18.002Keyboard controllerCH552GUSB MCU, key matrix scanning1$0.50$0.503Key switchesKailh PG1350Low-profile mechanical, 40 pcs40$0.25$10.004Keycaps—Low-profile, custom legend1 set$3.00$3.005Keyboard backlight—Amber SMD LED, 0402, 40 pcs40$0.03$1.206TrackPoint module—Analog stick, PS/2 compatible1$2.50$2.507Speaker—1W, 8Ω, 28mm diameter1$1.50$1.50Display & Input Total~$36.70

Power System
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1Li-ion cell18650 (2500mAh)3.7V, 2500mAh — 2 cells in parallel2$3.50$7.002Battery holder—2× 18650 parallel holder1$1.50$1.503Protection circuit—Overcurrent + overvoltage PCM1$0.80$0.80Power Total~$9.30

Enclosure
#ComponentDescriptionQtyUnit Cost (USD)Total1Top caseMat black ABS-PC, clamshell lid1$8.00$8.002Bottom caseMat black ABS-PC, keyboard base1$8.00$8.003Hinge assemblySteel, 135° stop, ×21 set$3.00$3.004Corner bumpersTPU rubber, ×41 set$1.00$1.005Screws & insertsM2 screws + brass inserts1 set$1.50$1.50Enclosure Total~$21.50

PLC Adapter (Separate Unit)
#ComponentPart NumberDescriptionQtyUnit Cost (USD)Total1PLC SoCST7580CENELEC EN50065, OFDM/FSK1$5.70$5.702Wi-Fi ModuleESP32-C3-MINI-1Wi-Fi AP for terminal connection1$0.80$0.803SMPSHLK-5M05230VAC → 5VDC1$3.50$3.504Inverter MOSFETsIRF540NDC-AC, 24V AC injection2$0.80$1.605Protection circuitTVS + MOV + relaySame as Board 11 set$2.00$2.006Schuko plug—Direct wall mount, 230V1$1.50$1.507EnclosureMat black ABSCompact square, ~80×80×40mm1$3.00$3.008LEDs—3× status LED (Power/PLC/WiFi)3$0.10$0.309Passive components—Resistors, capacitors—$1.00$1.00Adapter Total~$19.40

PCB Manufacturing (JLCPCB, 5 units each)
BoardSizeLayersQtyCostPLC / Power Board100×80mm25 pcs~$8.00Main Board100×80mm25 pcs~$8.00Adapter Board70×60mm25 pcs~$5.00PCB Total~$21.00

Cost Summary
ModuleCost (USD)Board 1 — PLC / Power~$16.70Board 2 — Main Board~$11.20Display & Input~$36.70Power System~$9.30Enclosure~$21.50PLC Adapter~$19.40PCB Manufacturing~$21.00TOTAL (single prototype)~$135.80

Note: Costs are single-unit retail estimates. Volume pricing significantly reduces cost:
10 units → ~$95/unit · 100 units → ~$62/unit · 1000 units → ~$38/unit


Where To Source
SupplierWhat To BuyLCSCAll ICs, passives, connectors (China, fast shipping)JLCPCBPCB fabrication + optional SMT assemblyAliExpress18650 cells, enclosure parts, mechanical partsMouserST7580 (official distributor), DS3231, protection ICsDigiKeyAlternative for all major ICs

Last updated: 2026 — REV 0.4
