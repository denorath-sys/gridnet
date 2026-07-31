GRIDNET — PLC/Power Board KiCad Schematic + PCB
REV 0.6 (Board 1, the PLC Adapter's own PCB — see "Board 1 is the PLC
Adapter's PCB" below.)

What changed in REV 0.6
------------------------

**The stackup is a rule now, not a sentence.** `STACKUP` in `build_pcb.py`
is written into the board's design settings: 1.6mm FR-4, four layers, 1oz
outer copper (0.5oz inner, which does not matter here — the inner layers carry
only planes and every current-carrying trace, the 1.0mm mains nets included,
is on an outer layer), 0.2mm minimum track and clearance, 0.6mm vias on 0.3mm
drills, 0.15mm annular ring, 0.25mm hole-to-hole.

This came out of closing the same item on the Main Board, where it exposed
something worse than an undocumented assumption: KiCad's minimums default to
zero, and both boards carried `m_TrackMinWidth = 0.0` and
`m_MinClearance = 0.0` through every DRC run this project has reported. A
0.05mm trace would have passed.

It caught something here immediately. The power fanout sends each of U4's
power pads 1.6mm straight out, and those pads are on a 0.5mm pitch — so their
vias landed on a 0.5mm pitch too, which with a 0.3mm drill is 0.2mm
hole-to-hole against the 0.25mm rule. Three pairs. The fanout now checks
hole spacing and steps a crowded neighbour further out.

A routing pass. It did not finish — every run still ends one connection
short — but what it found is worth more than the routing would have been:
six separate defects stood between this board and a routed one, and each was
invisible until the router hit it.

**The QFN's power pins had no fanout.** The ST7580 puts nine +5V pads on
three edges of a 48-pin 0.5mm-pitch package. Nothing passes between adjacent
pads there, so each escapes radially, and the router then has to bring nine
radial escapes back together around the outside of eleven others. Every run
this project had made died on that. `add_power_fanout()` now gives each power
pad a 1.6mm stub and a via at build time — what a person does by hand on a
QFN and what no autorouter does for itself.

**The pour ran after the repair, so the fanout vias were islands.** Planes
are what connect those vias; until the copper is poured they are isolated
points, and the repair router was being asked to tie them together — the
exact problem the fanout removes. `route.sh` now pours before repairing. This
is not the ordering the Main Board warns about: there the danger is pouring
before *routing*, which makes the autorouter treat GND as done. With those
two changes together, +5V stopped being a holdout at all.

**The repair router ignored netclasses.** It laid 0.2mm track at 0.2mm
clearance into the `Mains` class, which is 1.0mm at 2.5mm — on the mains side
that is not a style question, it is the live-to-neutral spacing. Seven
clearance errors in one run, every one on `/AC_L`, `/AC_N` or `/PLC_LINE`,
all laid by the step meant to be finishing the job. It now reads the rules
from the same table `build_pcb.py` writes into the project file: KiCad 9's
Python binding returns `GetNetClass()` as a bare object with no accessors, so
importing the source of truth is both simpler and harder to get out of step.

**Correcting that exposed a floorplan that could not satisfy it.** Four mains
nets at 1.0mm and 2.5mm need a 3.5mm pitch — about 16.5mm of channel with
margins — and the mains column had 9.7mm once the parts were in it. The
varistor lying flat is 22mm wide and blocked the column outright. `BARRIER_X`
moved from 30 to 36, the varistor and the X1 capacitor now stand on end, and
the isolated side gave up 6mm it was no longer short of.

**And then `/AC_N` still would not route — the repair router again.** It
stamped rule areas as obstacles inflated by the netclass clearance, which for
a mains net is a 3mm halo. The isolation band starts at x = 32.02, so the halo
reached 29.02 and swallowed T1's own mains pad at 30.92: that pad was
unroutable by construction. A keepout is a boundary, not a conductor — copper
may come up to its edge, it just may not cross. Stamping it with half the
track width instead closed `/AC_N` in two segments.

**A footprint was hanging off the board.** The JTAG header was moved to the
top edge without checking its height: 13.79mm upright, centred at y = 4.6, put
a third of it past y = 0. A whole routing run went by before anything noticed,
and what noticed was the repair router reporting an unconnected item at
y = −0.58. `check_on_board()` is now one line of arithmetic at placement time.

Where that leaves routing: the autorouter gets 174 nets down to 4–10, the
repair step closes most of the rest — eleven connections in one run — and each
attempt ends holding exactly one. The holdouts are now a different ordinary
signal every time (`/PLC_LED`, `/ST_CL`, `/ST_BR0`) rather than the systematic
`+5V` cluster they were before, which is the signature of a board at the edge
of what this toolchain does rather than of a defect. A ten-attempt run was
started to let nondeterminism land it; Freerouting hung on the first attempt
for 46 minutes and the run timed out. That hang is documented in the Main
Board's README too.

The board committed here is therefore placement, not routing: 62 components,
25 thermal vias, 11 power fanouts, two keepout zones, DRC clean at 0 errors.

What changed in REV 0.5
------------------------

**This is a four-layer board now**, and not for signal density — it could very
nearly be routed on two. It is four because of what has to be *planed*.

```
  L1  F.Cu    signals, all components
  L2  In1.Cu  GND plane      (4984 mm², isolated side only)
  L3  In2.Cu  +5V plane      (4960 mm², isolated side only)
  L4  B.Cu    signals
```

The ST7580 puts nine +5V pads on three edges of a 48-pin 0.5mm-pitch package.
Nothing passes between adjacent pads there — a 0.2mm track with 0.2mm
clearance needs 0.6mm and the gap is 0.25mm — so every pin escapes radially,
and those nine have to find each other around the outside of eleven other
escapes. **Four full two-layer routing runs failed on exactly that**, and
never on the same pad twice: (52.05, 6.70), (59.45, 11.25), (59.45, 8.25),
and twice on the pin 3 / pin 48 pair that wraps the top-left corner. A fifth
run with a filled +5V island on F.Cu routed cleanly — and was then broken by
its own ground pour, which chopped the island from 413 mm² to 109 mm² and
stranded eight connections. That net wants a plane, and on two layers both
copper layers are already spoken for by ground and the mains barrier.

**The barrier goes through all four layers.** An inner plane that crossed it
would bridge mains to SELV *inside the laminate*, where no inspection would
ever find it. Both keepout rule areas are on all four copper layers and both
planes stop at `SELV_MIN`; that is checked, not assumed — the filled polygons
start at exactly x = 33.98.

Two things the layer change taught, both recorded in `route.sh` so they are
not rediscovered:

- **Do not mark the inner layers `(type power)` in the DSN.** KiCad writes
  every copper layer as `(type signal)`, and rewriting the two inner ones does
  stop Freerouting laying signals across the planes — but it also stops it
  treating those planes as connecting GND and +5V, so it routes both as
  ordinary nets on two layers and fails badly: 52 unrouted against 7 without
  the change. The planes take some cutting from inner-layer signals; each is
  ~5000 mm² and the refill after routing closes around whatever crosses them.
- **The repair router had no idea planes existed.** It indexed a two-entry
  layer tuple with whatever layer it found a track on, and threw on the first
  inner-layer track. It now ignores inner-plane copper for its F.Cu/B.Cu
  occupancy grid, and can terminate a connection with a via down to a plane
  instead of a track to another pad — which on a planed net is usually the
  correct answer and is what Freerouting itself does.

Routing is **not finished**; see "What's not done yet".

What changed in REV 0.4
------------------------

The board has a PCB. `plc-board.kicad_pcb` places all 62 components inside
the 100×80mm outline, with thermal vias under both exposed pads and the
design rules written into `plc-board.kicad_pro`. Nothing is routed yet.

The thing that shapes this layout and did not exist on the Main Board is that
**half of this board is at mains potential**:

```
  x = 0                     BARRIER_X = 30                       x = 100
  |<----- mains side ------>|<-- 7.96mm -->|<--- isolated side --->|
  | J1 mains in, TVS, MOV,  |   no copper  | ST7580 + coupling     |
  | X1 cap, series inductor |  either side | filter, ESP32, power  |
  |                         |              | tree, USB-C to the    |
  |         U1 (HLK-5M05) --+--------------+-- Terminal, LEDs      |
  |         T1 (coupling) --+--------------+                       |
```

Only two parts cross that band, and each crosses it *inside its own body*,
where the manufacturer rather than this project is responsible for the
insulation: the HLK-5M05 (AC pins one end, DC pins 33.6mm away at the other)
and the coupling transformer. **The barrier's width is not a number this
project picked**: it is what T1's own land pattern leaves between primary and
secondary once the 2.2mm pads come off the 10.16mm pitch. Würth sized that
gap for a transformer whose entire job is to sit across a mains barrier.

Three mechanisms keep it that way, because placement alone would not:

- `check_isolation_barrier()` in `kicad_gen/build_pcb.py` tests **every pad of
  every net** on the board — not just the parts someone remembered to
  classify as mains — against the band, using pad bounding boxes rather than
  centres, since it is the copper edge that matters for creepage. It also
  asserts that exactly `U1` and `T1` have pads on both sides. The build
  refuses to write a board that fails either test; that refusal was checked by
  deliberately dragging `C17` across the barrier and confirming it fired.
- **The ground pour is clipped to the isolated side.** This is the one
  function that could not be reused from the Main Board unchanged. There the
  pour is the whole board; here a full-width pour would put GND copper
  straight through the barrier, and it would do it *silently*, because a zone
  is not a track and would not show up in a routing review. The mains side
  gets no plane at all, which is also correct on its own terms — there is no
  mains-referenced ground on this board, since the Schuko earth pin is unused.
- **The stitching-via grid starts at the barrier**, not at the board edge.

What the standards ask, and what is still open: reinforced insulation from
230V mains to a user-accessible SELV circuit is usually quoted around 5mm
creepage and 3–4mm clearance (IEC 60950-1 / 62368-1, pollution degree 2,
material group IIIa), with 8mm a common industry rule of thumb that includes
margin. 7.96mm sits in that band. The insulation here has to be *reinforced*
rather than basic, because the user physically handles the USB-C cable on the
isolated side while the adapter is in a wall socket. Confirming the exact
figure against the standard itself is listed under "What's not done yet" — it
is the one number in this layout taken from convention rather than from a
document this project has read.

Two findings came out of running DRC on the first placement, neither of which
a schematic pass could have surfaced:

- **The mains connector could not meet its own clearance rule.** The 2.5mm
  L-to-N spacing in the `Mains` netclass is the standards-derived figure; the
  5.08mm-pitch terminal block leaves 2.08mm between its own pads. The part was
  the placeholder, not the rule, so `J1` is now a 7.62mm-pitch Würth block.
- **The ST7580 footprint's built-in thermal vias are 0.2mm**, under the 0.3mm
  minimum in this project's board setup and JLCPCB's standard process, which
  hardware/bom.md's PCB line assumes. All 25 came back as `drill_out_of_range`.
  `U4` now uses the plain QFN footprint and `add_thermal_vias()` lays a 4×4
  array at 0.3mm — 4×4 because that is the array AN4068 measures the part's
  50 °C/W on, not a round number.

And one the DRC could not have found, which took rendering the board and
looking at it: **the ESP32-C3-MINI-1's antenna was in the middle of the
board.** The `-1` variant has an on-module PCB antenna and a real keepout
zone in its footprint (5.4 × 13.2mm, marked "Antenna Area", blocking copper
pour, tracks and vias), and the first placement had it surrounded by circuit
on all four sides. It is now at the right edge with the antenna facing out.
Note the asymmetry with the Main Board: that one carries the `-1U`, whose
datasheet Note A says explicitly it has *no* keepout zone because its radio
leaves on a cable. Same datasheet, same pin table, opposite layout rule.

What changed in REV 0.3
------------------------

The line coupling is built. That was the last open block on this board and
the reason its PCB layout had not started: the ST7580 datasheet specifies
the PA's pins but not the network hung off them, and AN4068 — which does —
could not be retrieved from this environment. It was eventually read, and
the whole section between `TX_OUT`/`PA_OUT` and the mains now exists.

The values are **not** AN4068's. Its reference design is a CENELEC A-band
node — receive filter on 80 kHz, coupling resonance on 85 kHz, sensitivity
specified at 86 kHz — and A-band is allocated to electricity suppliers.
GRIDNET sits in B+C, 95–140 kHz, which puts our entire band on the skirt of
their filters. Each resonance was rescaled to ~117 kHz holding AN4068's own
Q values and its own ratios between corner frequency and band edge; every
resistor keeps its reference value and only the reactive parts move.
[`docs/plc-coupling.md`](../../../docs/plc-coupling.md) has the arithmetic,
the cross-checks, and what the filters still do not do.

Also settled here: the coupling transformer. AN4068 names the part
(**Würth 750510231**), and its specification sheet meets every line of
AN4068's Table 4 except the withstanding-voltage row, where it quotes
2000 VAC for 1 s against Table 4's ≥4 kV — different tests, not necessarily
a conflict, but not something to assume about a galvanic barrier to 230 V.
It carries a custom symbol with the part's real terminal numbers (primary
1–4, secondary 10–7) rather than KiCad's generic 1/2–3/4 transformer, and a
footprint built from the sheet's own recommended land pattern.

What changed in REV 0.2
------------------------

REV 0.1 left three gaps and said they needed power-electronics design
this project's docs didn't specify: no supply for the ST7580's 8–18V
`VCC`, no gate driver for the IRF540N inverter, and no defined inverter
topology. Trying to answer them turned up two problems that made the
questions themselves wrong, both written up in **docs/plc-adapter-power.md**:

1. **The adapter had no power source during an outage at all.** Its only
   supply was the HLK-5M05, which needs 90–264V AC. When the grid fails
   the adapter stops — so it could never have run an inverter, and the
   24V it was supposed to inject could not have powered a neighbouring
   adapter either. The firmware protocol had already been written against
   a battery (`MASTER_ALIVE.battery_pct`) that the BOM never contained.
2. **The 24V injection is outside EN 50065-1.** The A-band limit is
   5 Vrms at 9 kHz falling to 1 Vrms at 95 kHz; 24V is 5–24× over it. The
   ST7580's own PA delivers 14 V p-p — 4.95 Vrms — because ST sized the
   part to land on that limit.

So REV 0.2 does two things. The adapter is now **powered from the
Terminal's battery** over a detachable USB-C cable, with a supercapacitor
covering the moment of grid loss. And the **inverter is gone**, replaced
by a proper 12V rail for the power amplifier that was always going to do
the actual signalling.

Two of the three original gaps were therefore closed rather than deferred.
The third — the coupling transformer and PA output network — waited on one
specific document rather than on open design questions, and REV 0.3 closed
it too.

What this is
------------

A KiCad 9 schematic (`plc-board.kicad_sch`) for the PLC Adapter's main
board: mains input protection, the HLK-5M05 AC-DC supply, the ST7580
power-line-communication modem, an ESP32-C3-MINI-1 as Wi-Fi AP + UART
host, status LEDs, and a programming header. Like the Main Board, it's
generated by Python scripts in `kicad_gen/` (reusing that directory's
`sexp.py`/`make_symbol.py`/`pinmap.py`/`schematic.py` verbatim — they're
generic, not Main-Board-specific) rather than hand-drawn.

No PCB layout exists yet for this board — this pass is schematic only,
same staging Main Board went through (schematic, then a separate
placement pass, then routing).

Board 1 is the PLC Adapter's PCB
----------------------------------

hardware/bom.md lists both "Board 1 — PLC/Power Board" and a separate
"PLC Adapter (Separate Unit)" section, which read as two different things
at a glance. They're not: the top-level README's Hardware Overview
describes only **two** physical products, the Terminal (Board 2 — Main
Board's system) and the PLC Adapter, which talk to each other over Wi-Fi
only — the Terminal has no powerline hardware at all. Board 1's component
list (ST7580, 2x IRF540N, TVS, MOV, relay, PC817, HLK-5M05) matches the
PLC Adapter's own hardware table in the top-level README line for line.
Board 1 *is* the PCB inside the PLC Adapter housing; the BOM's two
sections just cost out the same board from two different angles (bare
PCB + parts vs. the fully assembled product including enclosure, plug,
and LEDs).

Two BOM inconsistencies fell out of confirming this and were fixed in
hardware/bom.md as part of this pass (see that file's "Design Notes — REV
History" item 6 for the full writeup):
- The PLC Adapter's enclosure was spec'd at ~80×80×40mm, too small for
  Board 1's own 100×80mm PCB — a REV 0.4 estimate that never got
  reconciled against the PCB size, unlike the other stale REV 0.4 numbers
  already caught elsewhere in the BOM. Corrected to ~110×90×30mm.
- Board 1's `J1` connector was described as a "main board interface,"
  which read as if it connected to Board 2. It doesn't — Board 1 and
  Board 2 are different products that never connect to each other. `J1`
  is this board's own connector to the Adapter's Schuko-plug wiring and
  status LEDs (not present in the current schematic pass — see below).

What this covers, and what it deliberately doesn't
-----------------------------------------------------

This board builds every part of the circuit that's fully specified by a
primary source — a datasheet section, or an unambiguous line in this
project's own docs — and stops there rather than guessing at the parts
that aren't.

### The power architecture (REV 0.2)

Three sources feed one 5V rail, ORed with Schottky diodes:

```
  mains ──► HLK-5M05 ──┐
                       ├──►┤◄── +5V ──┬──► AMS1117-3.3 ──► +3V3
  Terminal ─► USB-C ───┘              │
                                      └──► MT3608 boost ──► +12V ──► ST7580 VCC
                                 10Ω ─┴─ 1F supercap
```

- **ORing with Schottkys** (`D5`/`D6`) rather than an ideal-diode
  controller, consistent with this BOM's price point. ~0.3V drop leaves
  ~4.7V, above the boost's input minimum and still enough headroom for
  the AMS1117 at the ~100mA it supplies.
- **`J4`, the Terminal inlet**, is a USB-C receptacle strapped as a sink
  (5.1k CC pull-downs), power-only — no USB data on this board. It sits
  on the HLK-5M05's *isolated secondary*. The user handles this cable, so
  the isolation barrier docs/electrical-safety.md calls non-negotiable is
  what stands between them and the mains side.
- **`C7`, the 1F supercapacitor**, charges through `R11` (~500mA inrush
  limit) and discharges through `D7`, keeping the resistor out of the
  discharge path. Its job is not to keep the adapter running — it is to
  keep the ESP32-C3 alive long enough to tell the Terminal over Wi-Fi
  that mains has gone, so the Terminal can put "connect the adapter
  cable" on screen. 6.4J per farad between 5V and the boost's ~3.5V
  minimum; a couple of seconds of Wi-Fi is well under 1J.
- **`U5`, the MT3608 boost**, is a real KiCad library part, not a custom
  symbol. Values from its own datasheet: `VREF` = 0.6V and
  `VOUT = VREF × (1 + R1/R2)`, so 12V needs R1/R2 = 19 — 19.1k/1k gives
  12.06V. 22µH inductor (its recommended 4.7–22µH range), 22µF ceramic in
  and out, plus 100µF bulk on 12V to ride transmit bursts. It's an
  asynchronous boost, so the rectifier `D8` is external.

12V was chosen for `VCC` because it sits mid-window in the datasheet's
8/13/18V range and well clear of the 6.1–7.5V undervoltage lockout.

### Transmit current limit

The ST7580 has a hardware output-current limit set by one resistor. It
mirrors 1/`CL_RATIO` of the PA output current through `RCL` to `VSS` and,
once that voltage passes `CL_TH`, walks `TX_GAIN` down a step at a time
until it's back under (datasheet Section 5.4):

```
RCL = CL_TH × CL_RATIO / I(PA_OUT) peak     CL_TH = 2.35V, CL_RATIO = 80
```

Checked against the datasheet's own Table 8: 1 A RMS FSK is 1.41 A peak →
2.35 × 80 / 1.41 = 133 Ω, exactly the tabulated value.

`R14` = 270R sets a 500 mA RMS ceiling, bounding what the Terminal's
battery has to supply. It's a backstop, not the operating point —
firmware sets `TX_GAIN` lower still on battery. `CL_SEL`, which would
switch `RCL` between FSK and PSK crest factors, is not used; one fixed
resistor means the effective ceiling differs slightly between
modulations, which is fine for a backstop, and it's a digital output so
leaving it open is safe.

What *is* built and ERC-clean:

- Mains input (`J1`) with Layers 1-2 protection: TVS (`D_TVS`,
  P6KE250CA) and MOV (`Varistor`, S20K275) across L/N.
- HLK-5M05 AC-DC supply, isolated 5V output.
- ST7580: every digital, control, clock, and power/ground pin that the
  datasheet fully specifies — UART to the ESP32, JTAG debug header,
  baud-rate selection, reserved-pin handling, the 8MHz crystal (no
  external load caps needed, both `XIN`/`XOUT` have them integrated),
  and the complete power/ground scheme from the datasheet's own Figure 8
  (supply structure) and Figure 9 (ground scheme) — reproduced exactly,
  not approximated.
- ESP32-C3-MINI-1 (on-module PCB antenna, no antenna connector): Wi-Fi AP, UART host
  for the ST7580, a UART0 programming header (without this or a USB
  connector there'd be no way to flash the module at all — an omission
  this pass caught and fixed, not something any existing doc specified).
- Status LEDs: Power (always-on), PLC (driven directly by the ST7580's
  `PL_TX_ON`), Wi-Fi (GPIO-driven, so firmware can blink it for real
  status rather than it being a second always-on LED).
- **The line coupling (REV 0.3)**: the transmit active filter around the
  ST7580's own power amplifier (`R15`/`C12` R-C pre-filter, then a
  Sallen-Key cell on `PA_IN±`/`PA_OUT`), the receive passive filter into
  `RX_IN`, and the coupling itself — DC block, `T1`, the series inductor
  and the X1 safety capacitor into `AC_L`/`AC_N`. Topology from AN4068
  section 7.1, values rescaled from its A-band centre to GRIDNET's B+C
  band. Every number in [`docs/plc-coupling.md`](../../../docs/plc-coupling.md).

Datasheet verification
------------------------

All three custom-built symbols were checked pin-by-pin against
primary-source datasheets before being written into
`kicad_gen/build_library.py`, same
standard as the Main Board's parts:

- **ST7580** — checked against STMicroelectronics' real datasheet
  (DocID022644 Rev 2, obtained via LCSC's CDN after ST's own site and
  several mirrors were unreachable from this environment — see the
  session history for what didn't work). Figure 2 (pinout diagram) and
  Table 2 (pin description) for all 48 pins + exposed pad; Figure 8/9 for
  the power and ground scheme; Section 7 for the crystal spec. This is a
  from-scratch symbol (ST7580 isn't in any KiCad bundled or
  community library found), so every pin was being verified for the
  first time, not checked against a prior (possibly wrong) version like
  the Main Board's parts were.
- **ESP32-C3-MINI-1** — same datasheet and Table 3-1 already used to
  verify the Main Board's ESP32-C3-MINI-1U, since both modules share one
  datasheet and pin table. Pin list is identical to that symbol, full
  stop: Table 3-1's 53 pads are the same for both variants and neither
  has an RF pad. This symbol has no `ANT` pin, and neither does the Main
  Board's any more — the one it used to have was invented, and the pad it
  claimed to name does not exist on either module (see
  ../main-board/README.md's "The antenna path never touched the board").
  The difference between the variants is only where the radio goes: an
  on-module PCB antenna here, an on-module W.FL/MHF III jack on the -1U.
- **Würth 750510231** (the coupling transformer) — terminals and every
  electrical parameter checked against Würth's own specification sheet
  (rev 6E, 8/22). It exists as a custom symbol for one reason: the real
  part's terminals are **1/4** (primary) and **10/7** (secondary), while
  KiCad's `Device:Transformer_1P_1S` numbers its pins 1/2 and 3/4. Using
  the generic symbol would have put a wrong pin number into the netlist
  and shown up, if at all, on the PCB — which is exactly how this project
  has lost two passes already. Its parameters against AN4068 Table 4 are
  tabulated in [`docs/plc-coupling.md`](../../../docs/plc-coupling.md);
  six of seven rows pass outright and the seventh (withstanding voltage)
  is an open question about test methods, not a failure.
- **Footprints**: ST7580 uses a bundled KiCad `QFN-48-1EP_7x7mm_P0.5mm`
  footprint sized to the datasheet's Table 14 exposed-pad dimensions
  (5.1×5.1mm typ., closest bundled option). ESP32-C3-MINI-1 uses the
  real footprint vendored from Espressif's official KiCad library into
  `gridnet_footprints.pretty/` (CC-BY-SA 4.0), same source and process as
  the Main Board's MINI-1U footprint — see that directory's README.md.
  `T1` uses a footprint built for this project from the "recommended P.C.
  pattern" on Würth's own sheet: four ⌀1.20mm holes on a 10.16 × 7.62mm
  rectangle, 14.22mm square body, 13.48mm high.

Real KiCad library parts used as-is (same confidence as any normal KiCad
design, no custom symbol needed): `Device:D_TVS`, `Device:Varistor`,
`Converter_ACDC:HLK-5M05` (exact bundled match for the BOM part),
`Regulator_Linear:AMS1117-3.3`, `Device:FerriteBead`, `Device:Crystal`,
`Device:R`/`C`/`LED`, and generic connectors.

ERC result
----------

```
kicad-cli sch erc plc-board.kicad_sch --format json -o /tmp/erc.json
```

**350 violations, 0 errors.** (This file said 212 until REV 0.3 re-ran it.
That figure predated the REV 0.2 pass which took the board from 29 to 47
components, and nobody re-counted; the categories and the reasoning below
were unchanged by either pass, only the off-grid endpoint count, which
grows by one per new pin.) Same benign categories as the Main Board's ERC
results, for the same reasons (see that board's README for detail):
`endpoint_off_grid` (345, cosmetic), `lib_symbol_issues` (3) and
`footprint_link_issues` (2) (this headless environment doesn't have
`gridnet_parts`/`gridnet_footprints` registered as project libraries;
both load and place correctly regardless).

Two ERC categories that came up during this pass and are worth naming
explicitly, since they're not just cosmetic noise silenced by rote —
each reflects a real judgment call:

- `power_pin_not_driven` on the mains connector's `AC_L`/`AC_N` pins and
  on the ST7580's internally-generated rails (`VDD` x2, `VDD_REG_1V8`,
  `VDD_PLL`, `VCCA`, `VSSA`). Both are legitimately not driven by
  anything *on this board* — mains power comes from the wall, and those
  ST7580 pins are fed by the chip's own internal regulators from `VDDIO`
  (datasheet Section 6: "not designed to supply external circuitry...
  accessible for filtering purposes only"). Each got a `PWR_FLAG`, with
  a comment citing the specific reason, rather than being silently
  wired to something to make the warning go away.
- `pin_not_connected` on the ESP32's `IO2`/`IO3` and (before the
  programming header was added) `U0RXD`/`U0TXD` — real omissions this
  pass caught while building, not intentional simplifications. Fixed
  (see above), not just flagged.

Net plan (high level)
----------------------

- **Mains protection:** `AC_L`/`AC_N` (from `J1`) — TVS and MOV both
  shunt across the pair, not in series with it.
- **Power:** `AC_L`/`AC_N` → HLK-5M05 → `+5V` (isolated secondary,
  becomes this board's logic ground reference) → AMS1117-3.3 → `+3V3`
  for the ESP32.
- **ST7580 UART:** `TXD`/`RXD` ↔ ESP32 `IO4`/`IO5` (a secondary UART on
  spare GPIOs, not the ESP32's own `U0RXD`/`U0TXD`, which are reserved
  for flashing the ESP32 itself via the programming header).
- **ST7580 control:** `RESETN` ↔ ESP32 `IO6`, `T_REQ` ↔ ESP32 `IO7`,
  `BR0`/`BR1` strapped high for 57600 baud (Table 3 of the datasheet).
- **ST7580 power/ground:** exactly Figure 8/9 of the datasheet — see
  "What is built" above.
- **Status LEDs:** Power → `+5V` direct. PLC → ST7580 `PL_TX_ON` direct.
  Wi-Fi → ESP32 `IO8` (active-low sink).

What's not done yet
--------------------

- **A conducted-emission measurement.** The coupling network is built and
  its arithmetic checks out, but harmonic suppression is inherently weaker
  in B+C than in the A band — a 95 kHz carrier puts its second harmonic at
  190 kHz, below the Sallen-Key corner, where the 3-pole network only takes
  off ~2.7 dB. The ST7580's own transmitter linearity (0.1–0.2 % THD,
  −70 dBc typical HD3) is doing most of the work. AN4068 earns its
  compliance claim with a LISN sweep (its section 8.2); GRIDNET needs the
  same before claiming EN 50065-1 conformance. See
  [`docs/plc-coupling.md`](../../../docs/plc-coupling.md).
- **The transformer's withstanding voltage.** Würth quotes 2000 VAC for
  1 s; AN4068 Table 4 asks for ≥4 kV, which comes from EN 50065-4-2's
  impulse test. Probably compatible, not demonstrably so — confirm with
  Würth before fabrication.
- **`ZC_IN` (zero-crossing)** — deliberately not built, not merely absent.
  The datasheet calls it optional, docs/protocol.md defines no
  mains-synchronous behaviour, and during an outage there is no mains to
  synchronise to. AN4068's circuit is recorded in docs/plc-coupling.md if
  it is ever wanted; note that its Figure 14 could not be read, so the
  block cannot be built from that list alone.
- **Routing.** The pipeline runs end to end and gets close — 152 unrouted
  down to 4-8 from the autorouter, with the repair step closing most of what
  is left (`+5V`, `/ST_PA_OUT`, `/AC_N`, `/PLC_LINE`, `/ST_TMS`,
  `/ST_VDD_REG_1V8` across runs) — but no run has produced a complete board.
  Each ends holding one connection.

  Two specific things stand in the way, both in `finish_routing.py` rather
  than in the design:

  - **`drop_via_to_plane()` reports success without checking it helped.** It
    stitched the same point three times in one run: it finds a legal via site,
    returns True, DRC reports the same pair unconnected, and it stitches
    again. It also chose a site 0.1mm from pin 48's pad — same net, so it
    added nothing. It needs to verify the reported connection actually closed,
    and to stitch the endpoint that is a *pad* rather than whichever end comes
    first.
  - **U4 pin 3 (VDDIO, left edge) has no reachable via site.** The pad sits
    directly over solid +5V plane copper — confirmed, the filled polygon
    contains its coordinates — so the connection it needs is a via, not a
    track. There is no legal site within the helper's 6mm search, which is a
    congestion problem on the QFN's left edge, not a search-radius one.

  Everything else the routing pass needed is in place and verified: the DSN
  carries the barrier as a `keepout` on all four layers, the repair router
  respects rule areas, and `check_isolation_barrier()` now runs on copper —
  pads, tracks, vias and filled zone polygons — where it has already caught
  one real defect (stitching vias hanging 0.3mm into the band, because the
  grid started at `SELV_MIN` and a via has a radius).
- ~~The pour sliver past the antenna keepout~~ — closed in REV 0.5. A second
  rule area now covers the strip between `U2`'s antenna keepout and the right
  board edge, on all four layers.
- **The creepage figure itself.** 7.96mm comes from T1's land pattern and
  sits inside the range convention quotes for reinforced insulation at 230V,
  but this project has not read IEC 60950-1 or 62368-1 directly. Every other
  number in this design traces to a datasheet; this one does not yet.
- **The Layer 3 protection circuit** is not deferred any more — it is
  **deleted**. Relay, optocoupler and voltage sensing existed only to
  isolate the inverter from the line, and there is no inverter. Layers
  1–2 (TVS, MOV) remain and are built.
- ~~**Which CENELEC band, in the protocol docs.**~~ Closed. The hardware was
  never undecided — the coupling network is tuned for B+C, 95–140 kHz, and
  changing that means changing four component values — and docs/protocol.md
  now describes that band throughout. What remains is the conducted-emission
  sweep any EN 50065-1 claim depends on, which needs a prototype.
- **`J1`'s replacement**: the BOM's `J1` (Schuko-plug + LED wiring) isn't
  in this schematic pass — the mains connector here (also called `J1` in
  the generated schematic, a coincidental naming collision, not the same
  connector) stands in for wherever the Adapter's own plug wiring
  attaches, and the status LEDs are wired directly to the board's power
  rails rather than through a separate interface connector.
