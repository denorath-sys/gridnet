# GRIDNET — Routing

**REV 0.1**

`ROUTE` as specified in [`protocol.md`](protocol.md) does not scale. This
document works out why, and redesigns it around a property of the medium
that the original design did not use.

Nothing here is implemented.

## The problem

A full-size `ROUTE` advertisement is 255 bytes of payload — 276 bytes on
air with preamble, header and CRC — which at 2.4 kbps occupies the channel
for **920 ms**. Every device broadcasts its own full table every 60
seconds.

| Nodes on the segment | Channel consumed by routing alone |
|---|---|
| 5 | 7.7% |
| 10 | 15.3% |
| 20 | **30.7%** |
| 30 | 46.0% |

An apartment building on one distribution segment reaches twenty nodes
easily. CSMA/CA does not degrade gracefully at that offered load — it
collapses well before 100%, because every station that defers and backs off
is competing with every other one. Routing overhead alone would make the
network unusable at exactly the density the project is designed for.

Adding signatures (see [`threat-model.md`](threat-model.md)) takes 20 nodes
from 30.7% to 37.8%. **Signatures are not the problem.** A 255-byte table
broadcast every 60 seconds on a 2.4 kbps link is.

## The assumption nobody wrote down

`protocol.md` specifies a distance-vector mesh where "every device is both a
node and a repeater", but no document in this project states what the
network's topology actually *is*. That assumption is load-bearing and it was
never made explicit, so here it is.

**A CENELEC-band PLC segment is a broadcast domain.** Within one low-voltage
distribution segment — everything on the secondary side of the same MV/LV
transformer — a signal injected at any outlet reaches essentially every
other outlet. Attenuation varies with cable length, load impedance and
noise, but the default case is that all nodes hear each other **directly, at
one hop**.

**The distribution transformer is the boundary.** CENELEC-band signals are
attenuated heavily crossing an MV/LV transformer — enough that a segment
should be treated as isolated unless a coupler is fitted at the transformer,
and this design has no such coupler.

Two things follow, and the second one is uncomfortable.

1. **Within a segment, multi-hop is the exception, not the rule.** It arises
   only where attenuation is bad enough that some pairs cannot hear each
   other — long runs, heavy loads, noisy branches. A general distance-vector
   protocol is the wrong shape for a medium where the common case is "one
   hop to everyone".

2. **The powerline reach of this network is one distribution segment.**
   "Communicate with your neighbourhood over the power grid" is true within
   the transformer's service area and not beyond it. Reaching a further
   segment needs the Wi-Fi mesh, which the README currently frames only as a
   fallback for damaged wire — not as the mechanism that joins segments
   together. That framing needs revisiting on its own; it is a premise
   question, not a routing one.

**This assumption is unvalidated.** No hardware exists, so nobody has
measured what fraction of a real segment actually hears each other. The
design below is built so that being wrong about it degrades gracefully
rather than failing — see "If the assumption is wrong".

## The redesign

### R1 — One-hop neighbours are learned passively, for free

Every transmission on the segment is heard by every node on the segment.
A node that receives any packet already knows the transmitter is one hop
away. **That information costs zero airtime, and the current design pays
920 ms per node per minute to re-derive it.**

So: any received packet marks its sender as a one-hop neighbour, with a
last-heard time. No routing traffic is involved.

This requires distinguishing "the node that transmitted this frame" from
"the node the packet is from", because a relayed packet carries the
originator in `SRC`. Inferring one-hop reachability from a relayed packet's
`SRC` would be wrong.

**`TYPE` bit 6 solves it at zero cost.** The threat model already claims bit
7 as the signed flag, and type codes `0x01`–`0x12` need only six bits:

```
TYPE byte:  [7] SIGNED   [6] RELAYED   [5:0] type code (0x00-0x3F)
```

A node sets bit 6 when relaying. Passive discovery trusts only packets with
bit 6 clear. No new header field, no bytes spent.

### R2 — `BEACON`, and why it is rare

Passive discovery only finds nodes that transmit. A silent node still has to
be reachable, so it announces itself.

**`BEACON` 0x07** — header only, no payload. 21 bytes on air unsigned; 85
bytes signed, which is 283 ms.

It is signed because a forged beacon is a cheap denial attack: it makes
every node believe an absent address is present, so traffic is sent to it,
never acknowledged, and retried. The signature is 64 bytes on a 21-byte
packet — a terrible ratio, and affordable only because the interval is long.

**Interval: 300 s, suppressed if the node has transmitted any unrelayed
packet in that window.** In an active network beacons approach zero; only
genuinely silent nodes pay for them.

Discovery of a *new* node does not wait 300 s. The threat model already has
a joining node broadcast `IDENT` immediately, which is an unrelayed packet
and therefore triggers passive discovery at once. Beacons maintain liveness;
`IDENT` handles arrival.

### R3 — `ROUTE` carries only what cannot be heard

A node advertises **only destinations it can reach that are not directly
audible to it**. On a segment where everyone hears everyone, that set is
empty and `ROUTE` is never transmitted at all.

What remains in the table is genuinely remote: nodes across an attenuated
branch, or across a Wi-Fi-bridged segment. Those tables are small.

### R4 — Triggered updates, with the periodic sync as a backstop

Instead of re-broadcasting a full table on a short timer:

- **On change:** advertise the changed entries only, after a random 1–5 s
  delay so simultaneous reactions to one event coalesce rather than collide.
  Minimum 30 s between triggered updates from one node, so a flapping link
  cannot turn into a broadcast storm.
- **Periodically:** full table every **600 s**, as a safety net for nodes
  that missed a triggered update.

### R5 — Split horizon and route poisoning

`protocol.md` states plainly that it has neither. Both are cheap here.

- **Split horizon**, per interface: routes learned on the PLC segment are
  not advertised back onto it. With one broadcast domain per interface this
  is simple — omit them — and it removes the classic two-node routing loop.
- **Route poisoning:** when a route dies, advertise it immediately at
  `hop_count` 16 (infinity) rather than waiting for it to age out. Valid hop
  counts stay 0–15, matching the existing RIP-style cap.

## What it costs

Worst case, twenty nodes on one segment, **all of them silent** so every
beacon is actually transmitted:

| | Current | Redesigned |
|---|---|---|
| Beacons | — | 20 × 283 ms / 300 s = **1.89%** |
| `ROUTE` | 20 × 920 ms / 60 s = **30.7%** | 0% (nothing non-audible to advertise) |
| **Total** | **30.7%** | **1.89%** |

A **16× reduction**, and the realistic figure is lower still because active
nodes suppress their beacons.

Degraded case — each node cannot hear five of the other nineteen, so each
advertises five entries (110 bytes signed, 367 ms, every 600 s):

| | |
|---|---|
| Beacons | 1.89% |
| `ROUTE` | 20 × 367 ms / 600 s = 1.22% |
| **Total** | **3.11%** |

Still an order of magnitude better than the current design's best case.

## If the assumption is wrong

The design's dependence on "most nodes hear each other" is bounded, because
a node advertises exactly what it cannot hear. As audibility gets worse,
tables grow and the protocol converges toward classical distance-vector —
but never exceeds it, because directly-audible destinations are never
advertised by anyone.

The pathological case is a segment where almost nobody hears anybody, which
would land near the current design's cost. That case also breaks the
project's premise, not just its routing.

**This needs a measurement, not an argument.** A conducted-emission sweep is
already required before any EN 50065-1 claim
([`electrical-safety.md`](electrical-safety.md)); a link-budget survey across
a real building should be run on the same prototype. Until then the numbers
above are arithmetic, not evidence.

## Consequences for the wire format

The format is not frozen, and these should land before it is:

| Change | Cost |
|---|---|
| `TYPE` bit 6 = RELAYED | 0 bytes |
| `TYPE` bit 7 = SIGNED (from the threat model) | 0 bytes |
| New type `BEACON` 0x07 | new code, no format change |
| `hop_count` 16 = unreachable | none, field is already a byte |
| `ROUTE` semantics: non-audible destinations only | none |
| `ROUTE` payload is a bare `RouteEntry[]` | **−7 bytes** |
| `SEQ` 2B → 4B | +2 bytes |

The `SEQ` widening is the one change that costs anything, and it is settled
rather than open — see [`protocol.md`](protocol.md) "`SEQ` is 4 bytes". At
16 bits the counter wraps in 3.6 hours at the Forth app rate limit, while
store-and-forward retains messages for 7 days, so a stored message can
outlive the counter that identifies it. Every figure in this document
already includes the wider header.

Removing the `RoutePacket` wrapper gives most of it back: that struct
restated `type`, `src` and `seq` from the header, so a `ROUTE` packet pays
+2 for `SEQ` and −7 for the wrapper, and comes out 5 bytes smaller than
before.

## Open questions

1. **Does a segment really behave as one broadcast domain?** The whole design rests on it. Needs a link-budget survey on real hardware.
2. **Is 300 s the right beacon interval?** It sets worst-case liveness detection at 900 s (three missed beacons). Shorter costs airtime linearly; longer delays noticing a node that has gone away silently.
3. **How do segments actually join?** If PLC stops at the transformer, the Wi-Fi mesh is not a damage fallback but the inter-segment bridge, and the README describes it as the former. A premise question worth settling before the routing layer is built on either answer.
4. **Does relay election need to exist?** On a broadcast domain where all nodes hear a flood, "each device repeats once" means twenty simultaneous retransmissions of one packet. That is a separate scaling problem in `protocol.md`'s flooding rule, not addressed here.

---

Last updated: 2026 — REV 0.1
