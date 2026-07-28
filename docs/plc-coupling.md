GRIDNET — PLC Line Coupling
REV 0.1

Board 1's last open block: the network between the ST7580's power amplifier
and the mains. This document is the analysis behind every component value in
`hardware/pcb/plc-board/kicad_gen/build_schematic.py`'s line-coupling
section.

Sources
--------

- **AN4068**, *ST7580 power line communication system-on-chip design guide*,
  DocID022923 Rev 2, section 7.1 and Table 3 — the reference design's
  topology, its equations, and its bill of material.
- **ST7580 datasheet**, DocID022644 Rev 1 — sections 3.1 (absolute maximum
  ratings), 5.1–5.4 (AFE), 5.6 (zero-crossing comparator), and the
  electrical characteristics tables.
- **Würth 750510231 specification sheet**, rev 6E (8/22) — the coupling
  transformer's real terminals and measured parameters.

Earlier revisions of this project recorded AN4068 as unobtainable (st.com
serves nothing to this environment). It was eventually read through
alldatasheet's HTML viewer, which carries each page's text even though the
page images come back blank — enough for the values, the equations and the
tables, but **not** for Figure 6 (the coupling schematic) or Figure 14 (the
zero-crossing circuit), which are images with no text layer. Where the
connectivity below could not be read off a figure, it is derived from the
equations and stated as such.

The band problem
-----------------

AN4068's reference design is a **CENELEC A-band** node. That is not a
detail of its filters; it is what the whole coupling section is tuned for:

| Block | AN4068 centre / corner |
|---|---|
| Reception passive filter | 80 kHz |
| Line coupling series resonance | 85 kHz |
| Receive sensitivity specified at | fC = 86 kHz |
| Transmission active filter corner | 150 kHz |

GRIDNET cannot use the A band. It is allocated to electricity suppliers;
general-purpose equipment belongs in 95–148.5 kHz (see
[`electrical-safety.md`](electrical-safety.md)). This project sits in **B+C,
95–140 kHz** — B needs no access protocol, C requires one and GRIDNET
already does CSMA/CA, and D is reserved for alarm and security systems,
which this is not.

So AN4068's values cannot be copied. Its whole passband sits below ours: a
receive filter centred on 80 kHz puts 140 kHz two-thirds of the way down its
skirt. What *can* be copied is the topology, the equations, and the design
ratios — which is what was done.

Retuning method
----------------

Three rules, applied to every block:

1. **Keep AN4068's Q.** It picked those Q values against measured mains
   impedance and a Montecarlo tolerance analysis this project cannot repeat.
2. **Keep AN4068's ratios to the band edge**, not its absolute corners. Its
   transmit filter corner is 1.58× its band's top edge and its RC pre-filter
   is 1.12×; both ratios carry over to a 140 kHz top edge.
3. **Move reactances, not resistors.** Every resistor below keeps its
   reference value. This is not a stylistic choice — it falls out of solving
   for the new centre frequencies with E-series parts, and it means the gain
   and Q expressions (which are resistor ratios) are untouched.

Each block was checked by reproducing AN4068's own stated result from its
own values before rescaling. A formula that does not reproduce 150 kHz,
Q = 1.03 and A₀ = 4.3 from AN4068's parts is a formula that was
mis-transcribed from a page of broken equation layout, and two were.

Transmission path
------------------

**Stage 1 — R-C pre-filter on `TX_OUT`.** `C12` stays at AN4068's 1 nF: it
says that value was chosen as the largest that does not load `TX_OUT` into
distortion, which is a property of the pin rather than of the band. The
corner therefore moves through the resistor alone.

| | AN4068 | GRIDNET |
|---|---|---|
| Series R | R16 = 1.5 kΩ | `R15` = 1 kΩ |
| Shunt C | C22 = 1 nF C0G | `C12` = 1 nF C0G |
| Corner | 106 kHz (1.12 × 95) | **159 kHz** (1.14 × 140) |

**Stages 2–3 — Sallen-Key cell around the ST7580's own PA.** The datasheet
brings `PA_IN+`, `PA_IN-` and `PA_OUT` out precisely so that a filter can be
built around the internal amplifier (section 5.3, "All pins of the power
amplifier are accessible").

```
    f_C = 1 / (2π · √(R16 · R17 · C13 · C14))
    Q   = √(R16 · R17 · C13 · C14) / (R17·C14 + R16·C14 + R16·C13·(1 − A₀))
    A₀  = 1 + R18/R19
```

| | AN4068 | GRIDNET |
|---|---|---|
| First series R | R15 = 5.1 kΩ | `R16` = 5.1 kΩ |
| Second series R | R12 = 22 kΩ | `R17` = 22 kΩ |
| Feedback C | C23 = 100 pF C0G | `C13` = 68 pF C0G |
| Shunt C | C15 = 100 pF C0G | `C14` = 68 pF C0G |
| Gain pair | R6 = 33 kΩ, R10 = 10 kΩ | `R18` = 33 kΩ, `R19` = 10 kΩ |
| f_C | 150 kHz | **221 kHz** |
| Q | 1.03 | **1.03** |
| A₀ | 4.3 (12.7 dB) | **4.3 (12.7 dB)** |

Both Q and gain are invariant when the two capacitors scale together, which
is why only the caps move: 100 pF → 68 pF shifts f_C by √2.15 and holds
AN4068's 1.58× ratio to the band edge (150/95 = 221/140).

Reception path
---------------

A series resistor into a parallel L-C to analog ground — high impedance at
resonance, so the band passes and everything else is shunted.

```
    f_c = 1 / (2π · √(L2 · C15))
    Q   = ω · R20 · L2 · C15 / (R20 · R_L · C15 + L2)      R_L ≈ 2 Ω
```

AN4068 is explicit that R_L — the inductor's own DC resistance, not just the
series resistor — sets the selectivity, so it stays in the expression.

| | AN4068 | GRIDNET |
|---|---|---|
| Series R | R5 = 150 Ω | `R20` = 150 Ω |
| Inductor | L2 = 220 µH | `L2` = 150 µH |
| Capacitor | C3 = 18 nF | `C15` = 12 nF |
| f_c | 80 kHz | **118.6 kHz** |
| Q | 1.3 | **1.31** |
| −3 dB bandwidth | ~62 kHz | **~90 kHz** |

95–140 kHz sits inside that with room on both sides. Solving Q and f_c
together for the new centre lands on 150 Ω unchanged with a 150 µH/12 nF
pair, which is the E-series-friendly answer and one fewer value to justify.

**No DC blocking capacitor**, and none in AN4068 either. `RX_IN`'s absolute
maximum range is −(VCCA+0.3) to VCC+0.3 (datasheet section 3.1): it is
specified to swing *below* ground, so the pin is meant to sit at 0 V DC. The
`V(RX_IN) BIAS = VCCA/2` line in the electrical table describes the internal
PGA node, not what the pin wants externally. The transformer primary would
ground the pin through its own winding regardless.

Line coupling
--------------

```
    f_c' = 1 / (2π · √((L3 + T1 leakage) · C17))
    Q    = 2π · f_c' · L3' / R_line          (R_line = 5 Ω, AN4068's figure)
```

| | AN4068 | GRIDNET |
|---|---|---|
| DC block | C2 = 10 µF/50 V X5R | `C16` = 10 µF/50 V X5R |
| Transformer | T1, 1:1 | `T1`, 1:1 |
| Power inductor | L1 = 15 µH | `L3` = 12 µH |
| X1 safety cap | C4 = 220 nF | `C17` = 150 nF |
| Series resonance | 85 kHz | **114 kHz** |
| Q into 5 Ω | 2 | **1.9** |
| −3 dB bandwidth | 40 kHz | **61 kHz** |

Note that AN4068 never asked this resonance to be flat across its band: 40
kHz of bandwidth for an 86 kHz-wide band. Ours is wider than the 45 kHz it
has to carry, which is the easier case. `L3` must keep AN4068's own
selection criteria — **≥2 A saturation and ≤0.1 Ω DC resistance** — or the
insertion loss and distortion under a heavily loaded line go with it.

`C17` is the X1 safety capacitor as well as a filter element: it is the part
standing between this board's analog ground and the live conductor. X1 grade
and the 15 mm through-hole pitch are not negotiable for a filter value.

The coupling transformer
-------------------------

AN4068 Table 4 specifies the part; `hardware/bom.md` REV 0.5 carried it as
"Würth Elektronik WE-PLCC series — confirm exact part against ST7580
application note before ordering". AN4068 names it: **Würth 750510231**,
with TDK SRW13EP-X05H002 as the alternate. Measured against Würth's own
specification sheet:

| AN4068 Table 4 | Required | Würth 750510231 | |
|---|---|---|---|
| Turns ratio | 1:1 | 1:1 ±1% | ✅ |
| Shunt inductance | ≥ 1 mH | 1.00 mH +35/−25% @ 100 kHz | ✅ |
| Leakage inductance | ≤ 1.5 µH | ≤ 1.0 µH | ✅ |
| DC total resistance | ≤ 0.5 Ω | ≤ 0.20 Ω per winding | ✅ |
| DC saturation current | ≥ 15 mA | measured at 15 mA DC bias | ✅ |
| Inter-winding capacitance | ≤ 30 pF | ≤ 30 pF | ✅ |
| Withstanding voltage | ≥ 4 kV | **2000 VAC for 1 s** | ⚠️ |

**The last row is the one open item on this part.** 2000 VAC rms is 2.83 kV
peak, and AN4068's ≥4 kV comes from EN 50065-4-2, which specifies impulse
withstand (1.2/50 µs), not a one-second AC test — the two numbers are
different measurements and a part passing 2000 VAC/1 s may well pass 4 kV
impulse. But that is an inference, not a specification, and the transformer
is one of the two galvanic barriers between a user's hands and 230 V. It
needs confirming with Würth before fabrication. AN4068 itself declines to
stand behind the number: "ST does not guarantee transformer isolation."

The symbol carries the real terminal numbers — primary **1–4**, secondary
**10–7** — rather than KiCad's generic 1/2, 3/4 transformer. Pin-number
mismatches between a symbol and the real part are the specific failure this
project has hit twice already, both times found only at PCB stage.

The footprint (`gridnet_footprints.pretty/Transformer_Wuerth_750510231`) is
the "recommended P.C. pattern" from the same sheet: four ⌀1.20 mm holes on a
10.16 × 7.62 mm rectangle, 14.22 mm square body, 13.48 mm high.

Zero crossing: recorded, not built
-----------------------------------

AN4068 section 7.1.4 gives a complete isolated zero-crossing circuit, and it
is worth writing down even though this board does not use it:

- Neutral and phase each reach the optocoupler through **two 56 kΩ SMD-2512
  resistors in series** — four in total. Two per line is deliberate: it
  keeps a single degraded resistor from becoming a short across the barrier.
- The series resistors limit the photodiode to ~1 mA rms at 230 VAC, so the
  whole circuit dissipates under 250 mW.
- An **LL4148** free-wheels the photodiode during the negative half-wave.
- The optocoupler is a **TLP781(GB)** in an inverting configuration.
- Measured timing: positive edge −75 µs, negative edge +430 µs, both ±300 µs.

`ZC_IN` itself wants a bipolar signal centred on VSS: comparator thresholds
are ±30–50 mV with 70 mV of hysteresis, and the input range is ±5 V
(10 V p-p). An optocoupler's output is unipolar, so something must
re-centre it on ground before the pin — Figure 14 would show what, and
Figure 14 is one of the images with no text layer. **Do not build this
block from the list above without reading that figure.**

Board 1 does not build it at all, for reasons that have nothing to do with
the missing figure:

- The datasheet calls zero-crossing detection **optional** (section 5.6).
- [`protocol.md`](protocol.md) defines no mains-synchronous behaviour. There
  is nothing in this project that would consume the signal.
- The one scenario this product exists for is the one where **there is no
  mains to synchronise to**. A feature that stops working exactly when the
  device matters most is a strange thing to spend a second mains-referenced
  creepage path on.

It is a self-contained five-part block, so adding it later costs a board
revision and nothing else.

What the filters do not do
---------------------------

Harmonic suppression is weaker in B+C than in the A band, and this is
inherent rather than a consequence of any choice above. A carrier at 95 kHz
puts its second harmonic at 190 kHz, which is *below* the 221 kHz Sallen-Key
corner. Working the 3-pole response through:

| Second harmonic of | lands at | attenuated by |
|---|---|---|
| 95 kHz | 190 kHz | ~2.7 dB |
| 140 kHz | 280 kHz | ~8.9 dB |

(The Sallen-Key's Q = 1.03 peaks slightly near its corner, which is why the
190 kHz figure is as poor as it is — the RC stage's −3.9 dB is partly given
back.)

This is survivable because the filter is the *second* line of defence, not
the first. The ST7580's own transmitter is specified at 0.1–0.2 % THD and
−70 dBc typical third-harmonic distortion (−55 dBc worst case); the network
above trims what is left. But "survivable by argument" is not the same as
"measured", and AN4068 earns its own numbers with a conducted-emission
sweep against the EN 50065-1 LISN (its section 8.2). **A GRIDNET prototype
needs the same measurement before any claim of EN 50065-1 compliance.**
Lowering the Sallen-Key corner towards 160 kHz would buy harmonic rejection
at the cost of flatness at the top of the band; that trade is best made
against a measurement rather than in advance.

Two smaller items also stay open:

- The **PA supply**. `VCC` is 12 V from the MT3608 (datasheet range 8–18 V),
  and the transmit current ceiling is set to 500 mA rms by `R14` = 270 Ω.
  The datasheet's I(VCC)-vs-I(PA_OUT) curve tops out near 500 mA of supply
  current at 1 A of output; at our 500 mA limit the boost converter's rating
  is comfortable, but the number has not been read off that curve precisely.
- **Component tolerance.** AN4068 backs each filter with a Montecarlo
  analysis (±20 % on the X1 capacitor and the coils, ±5 % on ceramics, ±1 %
  on resistors) showing ±1 dB of in-band variation. The rescaled values
  inherit the topology's sensitivity but not that analysis.
