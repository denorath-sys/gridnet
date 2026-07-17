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
- **ROUTE distance-vector routing** (`gridnet_sim/node.py`) — periodic
  table advertisements (own routes, hop-incremented) per
  `docs/protocol.md`'s REV 0.5 ROUTE Packet section, converging multi-hop
  reachability + next-hop info one hop per round, RIP-style hop-count cap
  and staleness pruning included.

## Running it

```bash
cd tools/protocol-sim
python3 run_demo.py --list
python3 run_demo.py master-failover
python3 -m unittest discover -s tests -v
```

Nine scenarios are in `gridnet_sim/scenarios.py`: `basic-exchange`,
`multihop-flood`, `routing`, `store-and-forward`, `master-election`,
`master-election-worst-case`, `cold-join`, `master-failover`,
`channel-fallback`. 36 unit tests in `tests/` cover packet framing, flooding
loop-prevention, store-and-forward, distance-vector route convergence, and
the inverter master state machine — all deterministic (seeded RNGs), run in
well under a second.

## Findings — and the fixes applied for them (REV 0.5)

Building and extending this surfaced three things about the *documented*
protocol (two REV 0.4 behavioral gaps, one packet type named but never
defined) and two bugs in the simulator's own code, one found while fixing
the other. All five are fixed. `docs/inverter-master.md` REV 0.5's "Design
Notes — REV History" section has the writeup for #1–2 aimed at firmware
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

### 4. FIXED (protocol gap) — ROUTE (0x04) was named but never defined

`docs/protocol.md`'s message-type table listed `ROUTE 0x04 — Routing table
update` alongside MASTER_ALIVE and MASTER_RESIGN, but unlike those two (which
got full C structs in `docs/inverter-master.md`), ROUTE had zero payload
definition anywhere — and "Mesh Routing" claimed every device maintains "a
neighbor table (address, hop count, last seen)" with no mechanism specified
for how a hop count beyond 1 would ever be learned. The simulator's own
flooding logic only ever produced 1-hop `known_nodes` entries (for inverter
master candidacy, deliberately segment-scoped) — there was no path to actual
multi-hop reachability info anywhere in this codebase either.

**Fix**: `docs/protocol.md` REV 0.5 now defines ROUTE as a distance-vector
advertisement — `{address:4B, hop_count:1B}` entries, periodic (60s, chosen
for airtime reasons — see the doc), never flooded (each device re-advertises
its own table, RIP-style propagation), with a 15-hop cap and 3-interval
staleness window. Implemented in `Node._advertise_routes` /
`Node._on_route`; `scenario_routing` and `tests/test_routing.py` demonstrate
a 4-node/3-hop chain converging to correct hop counts and next-hops in both
directions.

### 5. FIXED (simulator bug, not a protocol issue) — a shared RNG silently broke already-seeded tests

Wiring up ROUTE's periodic advertisement needed a randomized startup stagger
(so devices booting together don't broadcast in lockstep forever). The first
version drew it from `self._rng` — the same RNG `grid_lost()`/`cold_join()`
use for listen-delay jitter, and the one tests seed for reproducibility. That
extra draw at construction time shifted every subsequent draw from that
stream, silently changing the jitter values the already-passing
inverter-master tests depended on — `test_simultaneous_grid_loss_no_longer_reliably_collides`
started intermittently failing (split-brain rate crept from comfortably under
20% to 23%) with no change to any inverter-master code at all. Fixed by
giving the ROUTE stagger its own independent `self._route_rng` — sharing a
stateful RNG across unrelated concerns is exactly the kind of coupling that's
invisible until something downstream reads the stream differently.

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
- **ROUTE advertisement interval**: 60 seconds, hop cap 15, staleness 3
  intervals (180s) — none specified before REV 0.5; see `docs/protocol.md`'s
  ROUTE Packet section for the airtime-cost rationale behind 60s.

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
│   ├── scenarios.py             nine runnable demonstrations
│   └── simulator.py              discrete-event core
└── tests/
    ├── test_packet.py
    ├── test_flooding.py
    ├── test_routing.py
    ├── test_store_and_forward.py
    └── test_inverter_master.py
```
