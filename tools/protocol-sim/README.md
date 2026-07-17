# GRIDNET Protocol Simulator

A pure-Python, hardware-independent reference implementation of
[`docs/protocol.md`](../../docs/protocol.md) and
[`docs/inverter-master.md`](../../docs/inverter-master.md). It exists to
validate the mesh routing and inverter master election logic *before* the
hardware prototype exists — the firmware architecture doc lists the protocol
stack as "✅ Complete," but until now that meant "specified in prose,"
not "specified and exercised by running code."

No dependencies beyond the Python 3 standard library.

## What it implements

- **Packet framing** (`gridnet_sim/packet.py`) — the exact wire format from
  `docs/protocol.md`: preamble/sync/len/src/dst/seq/type/payload/CRC16, with
  encode/decode and CRC validation.
- **Hierarchical addressing** (`gridnet_sim/address.py`) — the 4-byte
  `CITY.DISTRICT.BUILDING.UNIT` scheme, including the broadcast address.
- **A discrete-event simulator** (`gridnet_sim/simulator.py`) — simulated
  time, not wall-clock time, so a "7-day" store-and-forward expiry costs
  nothing extra to run.
- **A shared-medium / CSMA-CA model** (`gridnet_sim/medium.py`) — one
  `Medium` per PLC segment or per WiFi mesh: carrier sensing, random backoff,
  and collisions between overlapping transmissions. Simplified (no PHY-level
  bit errors, no capture effect) — it's here to exercise the *link-layer
  contention* the protocol assumes, not to model CENELEC OFDM/FSK.
- **Mesh flooding + store-and-forward + inverter master election**
  (`gridnet_sim/node.py`) — a `Node` that floods unknown destinations,
  relays each `(src, seq)` exactly once, retries undelivered messages until
  ACKed or expired, and runs the full inverter master state machine
  (listen → master/slave → failover → split-brain resolution) from
  `docs/inverter-master.md`.

## Running it

```bash
cd tools/protocol-sim
python3 run_demo.py --list
python3 run_demo.py master-failover
python3 -m unittest discover -s tests -v
```

Eight scenarios are in `gridnet_sim/scenarios.py`: `basic-exchange`,
`multihop-flood`, `store-and-forward`, `master-election`,
`master-election-worst-case`, `cold-join`, `master-failover`,
`channel-fallback`. 28 unit tests in `tests/` cover packet framing, flooding
loop-prevention, store-and-forward, and the inverter master state machine —
all deterministic (seeded RNGs), run in well under a second.

## Findings — and the protocol fixes applied for them (REV 0.5)

Building this surfaced two behaviors of the REV 0.4 *documented* protocol
that reproduced every run, not as rare edge cases — plus one simulator bug
of its own. All three are now fixed; `docs/inverter-master.md` REV 0.5's
"Design Notes — REV History" section has the same writeup for firmware
readers who don't want to read this file.

### 1. FIXED — Simultaneous grid loss reliably triggered split-brain, not just as an edge case

REV 0.4's initial listen delay was a flat 2 seconds with no jitter. The most
common real-world trigger — an entire building or block losing grid power at
once — meant every device on the segment hit that 2-second timeout at the
*same instant* and every one of them tried to become master simultaneously,
every run. Split-brain detection resolved it correctly (lower address wins),
but that made split-brain the *primary* path for the most common outage
pattern, not a rare fallback — working against the doc's own rationale for
avoiding simultaneous injection ("voltage conflict... signal corruption...
excess current").

**Fix**: `grid_lost()` now uses `LISTEN_DELAY + random(0, LISTEN_JITTER)`
(2s + up to 500ms). Whichever device draws the shortest delay usually
asserts first and the others just hear it — no split-brain needed for the
common case. `scenario_master_election` demonstrates the fixed convergence;
`scenario_master_election_worst_case` / `test_split_brain_still_resolves_ties`
force an exact jitter tie to prove split-brain still works as the residual
safety net, same as REV 0.4.

### 2. FIXED — A new device could steal mastership from a stable, already-elected master

REV 0.4 stated: *"A new device always listens first. If it hears
MASTER_ALIVE, it becomes a slave."* But it used the same 2s window for
joining as for a fresh grid failure — much shorter than the 10s
MASTER_ALIVE interval, so a device joining at an arbitrary moment only had
roughly a 20% chance of its listen window actually overlapping a heartbeat.
The other ~80% of the time, it heard nothing, timed out, and declared itself
master. If its address happened to be lower than the existing master's, it
won the resulting split-brain and forced an already up-and-running master to
step down and resign — a real service interruption caused purely by unlucky
join timing, not any actual fault.

**Fix**: joining is no longer routed through the same short delay as a
self-witnessed grid failure. New method `cold_join()` — for a device
powering on or rejoining while the grid is already off, which can't assume
no master exists — uses `JOIN_LISTEN_DELAY + jitter` (12s, i.e.
`MASTER_ALIVE_INTERVAL + 2s` margin), reliably spanning a full heartbeat
cycle. `scenario_cold_join` and
`TestColdJoin.test_reliably_hears_existing_master_regardless_of_join_timing`
(swept across four join offsets spanning the heartbeat cycle) demonstrate
it now converges every time.
`test_grid_lost_is_the_wrong_call_for_joining_an_existing_segment` is kept
as a regression guard on the API distinction: calling `grid_lost()` instead
of `cold_join()` for a join still reproduces the old bug, which is correct —
that method's short delay is only safe for the scenario it's meant for.

### 3. FIXED (simulator bug, not a protocol issue) — a float-rounding edge case could permanently skip failover

While stress-testing fix #1 across many runs, `_check_master_timeout`
occasionally never triggered failover at all, even 30+ seconds after the
master went silent. Cause: it recomputed `sim.now - last_master_alive_heard
>= MASTER_TIMEOUT`, and floating-point rounding could land that a hair under
30 (observed: `29.999999999999996`), even though the callback is only ever
scheduled for exactly `last_heard + MASTER_TIMEOUT`. Since nothing else ever
rechecked it, the node just stayed `INV_SLAVE` forever, pointing at a master
that was gone. The check was redundant anyway — a matching `_inv_epoch` (the
staleness guard already used everywhere else in this file) already
guarantees no newer heartbeat arrived — so it's removed rather than patched
with an epsilon. Confirmed via a 300-run stress loop with unseeded jitter
after the fix (0 failures, previously ~35% failure rate).

## Assumptions made where the docs didn't specify a value

- **CRC16 variant**: CCITT-FALSE (poly `0x1021`, init `0xFFFF`) —
  `docs/protocol.md` says "CRC16" without naming a polynomial. Swap
  `gridnet_sim/crc16.py` if firmware settles on something else; nothing else
  depends on the specific algorithm.
- **Dedup / relay window**: 15 seconds — how long a node remembers a
  `(src, seq)` it has already relayed, so it doesn't repeat itself. Not
  specified in `docs/protocol.md`; chosen shorter than the retry interval so
  a legitimate retry isn't mistaken for a duplicate and silently dropped by
  intermediate relays.
- **Store-and-forward retry interval**: 30 seconds — not specified; the doc
  only gives the 7-day total retention.

## Repository layout

```
tools/protocol-sim/
├── README.md              (this file)
├── run_demo.py             CLI entry point
├── gridnet_sim/
│   ├── address.py          4-byte hierarchical addressing
│   ├── crc16.py             CRC16/CCITT-FALSE
│   ├── packet.py             wire framing, encode/decode
│   ├── medium.py              shared broadcast channel, CSMA/CA, collisions
│   ├── node.py                 flooding, store-and-forward, inverter master FSM
│   ├── scenarios.py             eight runnable demonstrations
│   └── simulator.py              discrete-event core
└── tests/
    ├── test_packet.py
    ├── test_flooding.py
    ├── test_store_and_forward.py
    └── test_inverter_master.py
```
