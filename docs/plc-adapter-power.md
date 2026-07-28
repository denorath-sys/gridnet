GRIDNET — PLC Adapter Power Architecture
REV 0.1

Why this document exists
------------------------

Two questions were blocking the PLC Adapter's PCB: where the ST7580's 8–18V
`VCC` rail comes from, and how the IRF540N inverter is driven and configured.
Trying to answer them surfaced a third question that makes the first two much
easier — what the adapter runs on when the grid is down — and a fourth that
changes what the adapter should do at all: whether the 24V injection the
design is built around is legal.

This document records what was found, what was decided, and the numbers the
decisions rest on. Everything quoted from the ST7580 datasheet is from
STMicroelectronics DocID022644 Rev 2, read directly.

Finding 1 — the adapter had no power source during an outage
------------------------------------------------------------

The PLC Adapter's only supply was the HLK-5M05, which needs 90–264V AC. When
the grid fails the adapter loses its supply and stops. A stopped adapter
cannot run an inverter, so the entire inverter mode could never have been
entered.

Nothing in the design solved this. `hardware/bom.md` gives Board 1 no battery
and no supercapacitor; every battery line item in that file belongs to the
Terminal. And the 24V the master was supposed to inject could not have
powered any other adapter either, because 24V is far below the HLK-5M05's
input range — despite the inverter-master protocol document stating that a
slave "listens on the wire powered by the master's 24V injection". That
document, `docs/inverter-master.md`, has since been removed; it is in git
history.

The firmware protocol had already been written as though a battery existed:
`MASTER_ALIVE` carries a `battery_pct` field documented as "Master's battery
level", and `MASTER_RESIGN` defines reason `0x01 = low battery`. The protocol
was describing hardware the BOM never contained.

**Decision: the adapter is powered from the Terminal's battery** over a
detachable USB-C cable, with a supercapacitor in the adapter covering the gap
between the grid failing and the user connecting that cable.

Why from the Terminal rather than giving the adapter its own cell:

- The protocol already models one battery per node. `MASTER_ALIVE` has a
  single `battery_pct` field; a second cell in the adapter would have meant
  two batteries per node and no defined answer for which one to report.
- It avoids a lithium cell sealed inside a wall-plug enclosure under permanent
  float charge, which is a real fire-safety concern and would have pushed the
  chemistry choice towards LiFePO4 for that reason alone.
- The Terminal already carries 24.8Wh. Adding a second energy store to the
  system to cover the same outage is duplication.

What it costs, stated plainly:

- The README's "no cables needed inside the home" holds only in normal
  operation. During an outage the user must connect the cable.
- Channel switching is therefore no longer automatic in the outage case. Any
  claim of a "< 20ms" transition into outage mode is wrong — the transition
  takes as long as the user takes.
- If the Terminal is switched off, discharged, or not at home, its adapter is
  dead for the duration. An adapter with its own cell would not have been.

Finding 2 — the 24V injection is outside EN 50065-1
----------------------------------------------------

`docs/electrical-safety.md` claims "GRIDNET's 24V AC, 100mA injection is
within these limits", citing EN 50065-1. It is not.

EN 50065-1 limits the A-band (9–95 kHz) output to **134 dB(µV) at 9 kHz,
falling linearly with log frequency to 120 dB(µV) at 95 kHz** — that is 5 Vrms
down to 1 Vrms. A 24V injection is between 5 and 24 times the permitted level
depending on frequency.

Two further problems with the same paragraph:

- The A-band is allocated to **electricity suppliers**. General-purpose
  equipment is confined to 95–148.5 kHz. The document's own table lists the
  A-band users as "Energy companies, smart meters, GRIDNET" — GRIDNET is not
  an electricity supplier.
- The document lists the inverter's output frequency as "9–148 kHz (PLC
  band)", conflating a power waveform with a signalling band. These are
  different things and the design needs to say which one it meant.

The ST7580's own integrated power amplifier delivers **14 V p-p**, which is
4.95 Vrms — ST sized the part to land precisely on the A-band limit. The chip
already produces the strongest signal the standard permits.

**Decision: the 24V injection and the inverter are removed.** Its two
justifications were powering other adapters, which Finding 1 solves a
different way, and signal reach, which the ST7580's PA already provides at the
maximum legal level once `VCC` is actually supplied. What remains is not an
inverter but a properly-fed line driver.

This deletes the IRF540N pair, their gate driver, the HK19F relay, the PC817,
the voltage-sense circuit and the whole of protection Layer 3, whose only
function was isolating the inverter from the line.

It also removes the need for the inverter master protocol. That protocol
exists to stop two devices injecting energy simultaneously; with no injection
there is no energy conflict to arbitrate, and CSMA/CA at the data layer
already handles simultaneous *transmission*. See "Consequences" below.

Power architecture
------------------

Three sources feed one 5V rail, ORed with Schottky diodes:

```
  mains ──► HLK-5M05 ──┐
                       ├──►┤◄── 5V rail ──┬──► AMS1117-3.3 ──► +3V3 (ESP32-C3, ST7580 VDDIO)
  Terminal ─► USB-C ───┘                  │
                                          └──► boost ──► +12V ──► ST7580 VCC
                                     10Ω ─┴─ supercap (hold-up)
```

- **Schottky ORing** rather than an ideal-diode controller, consistent with
  this BOM's price point. Costs ~0.3V, leaving ~4.7V, which is above the
  boost's input minimum and leaves the AMS1117 enough headroom at the ~100mA
  it supplies.
- **The supercapacitor charges through a series resistor** (~10Ω, limiting
  inrush to ~500mA) and discharges into the rail through its own Schottky, so
  the resistor does not sit in the discharge path.
- **The USB-C inlet is a sink**: 5.1k CC pull-downs, same strapping as the
  Terminal's own input. No USB-PD negotiation.

### ST7580 VCC rail

| Parameter | Datasheet value |
|---|---|
| `VCC` operating range | 8 / 13 / 18 V (min/typ/max) |
| `VCC` undervoltage lockout | 6.1–7.5 V |
| `I(VCC)` receive | 0.35 mA typ, 0.5 mA max |
| `I(VCC)` transmit, no load | 22 mA typ, 30 mA max |
| `I(VCC)` transmit, full drive | ~550 mA at `I(PA_OUT)` = 1.1 A (Figure 4) |
| `I(PA_OUT)` max | 1000 mA RMS |
| `V(PA_OUT)` | 14 V p-p |

12V was chosen as the rail: comfortably inside the 8–18V window, far above the
7.5V lockout, and a standard boost output.

The transmit figure is what sizes everything. At full drive the PA alone is
~7.2W, which from a 5V input at 85% efficiency is about 1.7A on the cable —
more than the Terminal should be asked to source, and more than the Terminal's
own +5V rail was sized for in Main Board REV 0.7.

### Bounding transmit power

The ST7580 has a hardware output-current limit programmed by a single
resistor `RCL` between the `CL` pin and `VSS`. The chip mirrors 1/`CL_RATIO`
of the PA output current through it and, when the resulting voltage exceeds
`CL_TH`, walks `TX_GAIN` down one step at a time until it is back under.

```
RCL = CL_TH × CL_RATIO / I(PA_OUT) peak        CL_TH = 2.35 V, CL_RATIO = 80
```

Checked against the datasheet's own Table 8: 1 A RMS in FSK is 1.41 A peak,
giving 2.35 × 80 / 1.41 = 133 Ω, which is exactly the value tabulated. PSK's
2 A peak gives 94 Ω, also as tabulated.

This design targets **500 mA RMS** as the hardware ceiling — 705 mA peak in
FSK, so `RCL` ≈ 267 Ω (use 270 Ω, E24). The limit is a backstop, not the
operating point: firmware sets `TX_GAIN` lower still when running from the
Terminal's battery.

`CL_SEL` exists to switch `RCL` between the two modulations, whose crest
factors differ. This design does not use it — one fixed resistor means the
effective RMS ceiling differs slightly between FSK and PSK, which is
acceptable for a backstop. `CL_SEL` is a digital output and is left
unconnected. Anyone wanting the switched arrangement should take it from
AN4068 rather than infer it here; the datasheet does not give the circuit.

### Energy budget

| Mode | ST7580 `VCC` | Logic (+3V3) | Total from 5V |
|---|---|---|---|
| Receive / idle | 0.35 mA @ 12V ≈ 4 mW | ESP32-C3 AP ~120 mA @ 3.3V ≈ 400 mW | ~0.5 W |
| Transmit, mains, `RCL` ceiling | ~250 mA @ 12V ≈ 3.0 W | ~400 mW | ~4.0 W |
| Transmit, battery, reduced `TX_GAIN` | ~150 mA @ 12V ≈ 1.8 W | ~400 mW | ~2.7 W |

Mains mode peaks at ~4.0W against the HLK-5M05's 5W rating. That fits, but
without much margin, so the 12V rail carries bulk capacitance to ride
transmit bursts rather than sizing the supply for peak.

Outage runtime, Terminal at 24.8Wh powering both itself and one adapter:

- Terminal active (1.78W) + adapter transmitting occasionally (~2.7W peak,
  less on average): **roughly 5–6 hours**
- Terminal screen off (0.07W) + adapter: **roughly 9 hours**

Only the node whose user is actually transmitting pays the transmit cost;
adapters that are only listening sit at ~0.5W.

### Supercapacitor sizing

Usable energy between the 5V rail and the boost's ~3.5V input minimum:

```
E = ½C(5² − 3.5²) = 6.4 J per farad
```

A 1F 5.5V part gives ~6.4J. Its job is not to keep the adapter running — it
is to keep the ESP32-C3 alive long enough to tell the Terminal over Wi-Fi that
mains has gone, so the Terminal can put "connect the adapter cable" on screen.
A couple of seconds of Wi-Fi activity is well under 1J. In an idle hold state
the same charge lasts on the order of minutes.

Consequences for the rest of the project
-----------------------------------------

Removing the inverter is not a local change. These all assert things that are
no longer true:

- `docs/inverter-master.md` — **removed.** The protocol it specified had no
  remaining purpose: `MASTER_ALIVE`, `MASTER_RESIGN`, the three inverter
  states and the master-selection algorithm all existed to arbitrate an
  injection that no longer happens. Available in git history.
- `tools/protocol-sim` — implements that state machine as its reference
  implementation.
- `docs/protocol.md` — the channel priority table drops from three rows to
  two (PLC, Wi-Fi mesh); the inverter master section goes.
- `docs/electrical-safety.md` — the EN 50065 compliance claim is wrong as
  written and needs replacing with the real limits; the Layer 3 section
  describes isolating an inverter that no longer exists. What the document
  gets right and should keep: galvanic isolation through the coupling
  transformer, and Layers 1–2 (TVS, MOV).
- `README.md` — the "Inverter mode" line in the architecture diagram, the
  Inverter Master Protocol section, and the PLC Adapter hardware table.
- `hardware/bom.md` — IRF540N ×2, HK19F relay, PC817 come out; USB-C inlet,
  supercapacitor, boost converter and the ORing diodes go in.

What GRIDNET still is after this change: a powerline mesh that keeps working
through a grid outage on battery power, at a signal level that is actually
legal. What it no longer claims: energising the wire itself.

Open questions
--------------

- **The coupling transformer is still unspecified.** `hardware/bom.md` flags
  the Würth WE-PLCC series as needing confirmation against ST's application
  note, and that is still true — AN4068 has the reference coupling circuit
  and this document does not reproduce it. The PA output network, the series
  coupling capacitor and the `RX_IN` path all depend on it.
- **`ZC_IN` (zero crossing)** has no circuit yet. With no relay to align to a
  zero crossing, its remaining use is mains-presence detection and PLC timing.
- **Which CENELEC band to use.** A-band is not available to this project. The
  95–148.5 kHz range is, and the ST7580 covers it, but `docs/protocol.md`
  specifies A-band throughout and that needs revisiting.
- **The Terminal must become a power source.** Its USB-C port is strapped as
  a sink (5.1k CC pull-downs). Sourcing to the adapter needs either a second
  dedicated connector or dual-role support, and Main Board REV 0.7's +5V
  netclass (0.4mm, ~0.9A design maximum) was not sized with the adapter's
  draw included.

Last updated: 2026 — REV 0.1
See also: hardware/pcb/plc-board/README.md, docs/electrical-safety.md
