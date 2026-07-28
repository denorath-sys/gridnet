GRIDNET — Electrical Safety and Regulatory Analysis
REV 0.6

Overview
--------

GRIDNET couples a low-voltage signal onto household mains wiring in the
CENELEC signalling band, through a transformer, to carry data between
adapters. This document covers what that means for connected equipment,
for people, and for regulatory compliance.

**REV 0.6 is a correction.** Every earlier revision of this document was
written around a 24V AC "inverter mode" in which one adapter energised the
wire during a grid outage. That feature has been removed — see
docs/plc-adapter-power.md for the full reasoning. Two things were wrong
with it:

1. **It could never have run.** The PLC Adapter's only supply was the
   HLK-5M05, which needs 90–264V AC. When the grid fails the adapter loses
   power, so it could not have driven an inverter, and the 24V it was
   meant to inject could not have powered a neighbouring adapter either.
2. **It was not compliant.** This document previously stated that
   "GRIDNET's 24V AC, 100mA injection is within these limits", citing
   EN 50065-1. That was false by a factor of 5 to 24 — see "Regulatory
   compliance" below.

What replaces it: the adapter is powered from the Terminal's battery over
a detachable cable during an outage, and the signal is driven by the
ST7580's own integrated power amplifier at a level the standard permits.

Regulatory compliance
---------------------

### EN 50065-1 signal levels

EN 50065-1 governs signalling on low-voltage electrical installations
between 3 kHz and 148.5 kHz. For narrow-band signals in the A-band, the
output level **shall not exceed 134 dB(µV) at 9 kHz, decreasing linearly
with the logarithm of frequency to 120 dB(µV) at 95 kHz** — that is
5 Vrms falling to 1 Vrms.

GRIDNET's transmitter is the ST7580's integrated power amplifier, rated
at 14 V p-p (datasheet DocID022644 Rev 2), which is 4.95 Vrms.
STMicroelectronics sized the part to land on the limit; the design's job
is to not exceed it, and the hardware current limit described in
hardware/pcb/plc-board/README.md provides a backstop.

A 24V injection would have been 5 to 24 times over this limit depending
on frequency. It is not in the design any more.

### Band allocation

| Band | Frequency | Permitted users |
|---|---|---|
| A | 9–95 kHz | **Electricity suppliers only** |
| B | 95–125 kHz | General use, no access protocol required |
| C | 125–140 kHz | General use, CSMA access protocol required |
| D | 140–148.5 kHz | General use, alarm and security systems |

**GRIDNET is not an electricity supplier and cannot use the A-band.**
Earlier revisions of this document listed the A-band's users as "Energy
companies, smart meters, GRIDNET", which was wrong. General-purpose
equipment is confined to 95–148.5 kHz.

docs/protocol.md still specifies A-band operation throughout and needs
revisiting. The ST7580 covers both ranges, so this is a configuration and
documentation question rather than a hardware one — but it is unresolved,
and it is the single largest open compliance item in the project.

### Other regions

Outside Europe, regulations differ — FCC Part 15 in the US allocates
different bands and limits. Check local EMC regulations before deploying.

Why the signal is safe for household equipment
-----------------------------------------------

PLC signalling operates at 95–148.5 kHz, between 1900 and 3000 times the
50 Hz grid frequency. Consumer electronics power supplies, transformers
and filter capacitors are designed for 50 Hz and naturally attenuate
signals at these frequencies. The signal is effectively invisible to
their power circuits.

This is the same principle used by HomePlug, G.hn and smart-metering
systems deployed in millions of homes for over two decades. GRIDNET's
signal level is comparable to theirs, which is the point of staying inside
EN 50065-1 rather than above it.

| Technology | Frequency | Signal level | In use since |
|---|---|---|---|
| HomePlug AV | 1.8–30 MHz | ~1V | 2005 (HomePlug 1.0 from 2001) |
| G.hn | 2–100 MHz | ~1V | 2009 |
| Smart meter (DLMS) | 9–95 kHz | ~1V | 1990s |
| GRIDNET | 95–148.5 kHz | ≤5 Vrms, EN 50065-1 limited | — |

Galvanic isolation
------------------

This is mandatory and non-negotiable in the design, and REV 0.6 gives it
one more job than it had before.

There is no direct electrical connection between the mains and any
low-voltage circuit:

- The **ST7580's line interface** reaches the mains only through the
  coupling transformer.
- The **HLK-5M05** is an isolated AC-DC module; its output ground is the
  adapter's logic ground and is galvanically separate from L and N.
- The **USB-C cable to the Terminal** sits on that isolated secondary.
  This is new in REV 0.6 and it matters: the user physically handles this
  cable while the adapter is plugged into a wall socket. The isolation
  barrier inside the HLK-5M05 is what stands between them and the mains.

Consequences:

- The user cannot receive a mains shock through the Terminal or its cable.
- A fault in the digital circuits cannot energise the mains line.
- The design follows the basic insulation requirements of IEC 60950/62368.

Anyone reviewing this project for safety should start here: the isolation
barrier is the single load-bearing safety property, and the adapter-to-
Terminal cable is the newest thing depending on it.

Protection circuit
------------------

The adapter includes two layers of line protection.

**Layer 1 — Transient suppression.** TVS diode P6KE250CA (bidirectional,
250V clamp), absorbing fast voltage spikes from lightning and switching
transients. Response time under 1 ns.

**Layer 2 — Sustained overvoltage.** MOV S20K275 (275V varistor),
handling sustained overvoltage conditions and self-resetting once the
overvoltage clears.

Both are built in the schematic (hardware/pcb/plc-board).

**Layer 3 has been removed.** Earlier revisions specified a relay
(HK19F), an optocoupler (PC817) and a voltage-sensing circuit whose sole
function was isolating the inverter from the line and re-synchronising at
a zero crossing when the grid returned. With no inverter there is nothing
for them to isolate or re-synchronise, so they are gone from the design
rather than left as unexplained parts.

What happens during a grid outage
----------------------------------

There is no voltage injection and therefore no arbitration between
adapters. Each adapter is powered by its own Terminal over the USB-C
cable, and all of them transmit and receive normally using CSMA/CA at the
data layer, exactly as they do when the grid is up. The wire remains a
conductor whether or not it is energised.

This also removes the inverter master protocol entirely, which existed
only to ensure exactly one device injected energy at a time. See
docs/plc-adapter-power.md.

Frequently asked questions
---------------------------

**Will GRIDNET damage my neighbour's television / refrigerator /
computer?**
No. The signal sits inside EN 50065-1's limits at 95–148.5 kHz and is
filtered out by every household appliance's power supply.

**Will GRIDNET interfere with my neighbour's HomePlug adapter?**
HomePlug AV operates at 1.8–30 MHz, far above GRIDNET's band, so direct
interference is unlikely. Other CENELEC-band devices in the same
95–148.5 kHz range could conflict; GRIDNET uses CSMA/CA
(listen-before-transmit) to minimise this.

**Is it legal to put signals on the power line?**
In Europe, yes, within EN 50065-1's limits and in the bands available to
general-purpose equipment (95–148.5 kHz). It is *not* legal for a project
like this to operate in the A-band, and docs/protocol.md still needs
updating on that point. Elsewhere, check local EMC regulations.

**What happens when the power goes out?**
The adapter loses mains power and runs from the Terminal's battery over
the USB-C cable, which the user connects. A supercapacitor in the adapter
keeps it alive long enough to tell the Terminal that mains has gone so the
Terminal can prompt for the cable. Networking continues normally on
battery power; nothing is injected onto the wire.

Last updated: 2026 — REV 0.6
See also: docs/plc-adapter-power.md — the power architecture and the
analysis behind this revision
