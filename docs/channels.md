# GRIDNET — The Two Channels

**REV 0.1**

[`protocol.md`](protocol.md) ranks the channels: powerline first, Wi-Fi mesh
second, the mesh used when "line damaged or PLC failed". The README frames
the mesh the same way — a fallback.

That framing is wrong, and [`routing.md`](routing.md) is what exposed it. If
PLC stops at the distribution transformer, the mesh is not a backup for the
powerline; it is the only thing that joins anything the powerline cannot.

This document works out what each channel actually reaches, and what the
routing layer should do with two interfaces instead of a ranked pair.

Nothing here is implemented.

## Wi-Fi is doing two unrelated jobs

The README's diagram runs them together:

```
Normal mode:  [Terminal] ←WiFi→ [PLC Adapter] ←powerline→ [neighbor's adapter] ←WiFi→ [neighbor's Terminal]
```

Both arrows say "WiFi" and they are not the same thing.

**W1 — the tether.** A Terminal reaching its *own* Adapter. The Adapter is
an access point; the Terminal associates with it. This is a private
point-to-point link to the node's own modem, conceptually a cable that
happens to be radio. It carries no one else's traffic and it is not a
network interface for routing purposes.

**W2 — the mesh.** A node reaching *other people's* nodes over ESP-NOW.
This is a genuine second routing interface, and it is the one the README
calls a fallback.

Conflating them is why the mesh reads as an emergency measure. W1 is
always in use, so "Wi-Fi" looks like it is already accounted for.

## What each channel actually reaches

**PLC reaches electrical neighbours. The mesh reaches physical neighbours.
These are not the same set, and neither contains the other.**

That is the whole point, and it is why one cannot be a fallback for the
other.

### PLC's boundaries

| Boundary | Effect |
|---|---|
| **MV/LV distribution transformer** | CENELEC-band signals are attenuated heavily crossing it. Treat a segment as isolated; this design fits no transformer coupler. |
| **Phase** | LV distribution is three-phase and households sit on one of L1/L2/L3. This Adapter couples L-to-N through a Schuko plug, so it transmits on one phase. Cross-phase coupling exists — through the transformer and through connected loads — but with substantial additional attenuation, commonly cited in the 20–40 dB range and highly variable. |

The second one matters more than the first for the use case this project
describes. A transformer district in a European city typically covers a
street or several buildings, so "my neighbourhood" is often within one
segment. But **within a single building, the three phases can partition the
network into up to three groups that barely hear each other** — and the
flats in those groups are interleaved, not separated.

### The mesh's boundary

Physical distance and walls. ESP32-C3 at 2.4 GHz with a ≤2.33 dBi antenna
reaches adjacent and vertically-stacked flats; it does not reach the far end
of a street.

### Why they compose well

The most common way PLC connectivity fails inside a building is **the
neighbour is on another phase** — and that is exactly the case where
physical adjacency holds and the mesh works. The mesh's reach is not a
weaker version of PLC's; it is orthogonal to it, and it covers PLC's
most likely gap.

## The energy argument points the same way

During a grid outage the Adapter runs from the Terminal's battery, so both
channels draw from the same 24.8 Wh. Using [`plc-adapter-power.md`](plc-adapter-power.md)'s
own figures:

| | Power | Rate | Marginal energy per bit |
|---|---|---|---|
| PLC transmit, battery, reduced `TX_GAIN` | 2.7 W (0.5 W idle → 2.2 W marginal) | 2.4 kbps | ~0.92 mJ/bit |
| ESP32-C3 with traffic | ~0.4 W, **already being spent** | ESP-NOW, unmeasured | ≲0.004 mJ/bit |

Two to three orders of magnitude, and robust to pessimistic assumptions —
even charging the mesh its full 0.4 W and assuming only 100 kbps effective
throughput, it still comes out over 200× cheaper per bit.

The reason is that **the radio is already on**. W1 keeps the Adapter's
ESP32-C3 up as an access point at ~400 mW whether or not anyone meshes over
it, and that 400 mW is already the dominant term in the Adapter's 0.5 W
idle draw. Peering with neighbouring Adapters on the same radio adds
almost nothing.

So in an outage — the scenario this project exists for — the channel the
current design treats as an emergency fallback is the cheaper one to use,
and the expensive one is the default.

## Decisions

### C1 — The mesh belongs to the Adapter, not the Terminal

Both units have an ESP32-C3. The mesh should run on the Adapter's:

- **Its position is fixed and known.** It is in a wall socket. The Terminal is carried around, closed, and switched off.
- **Its radio is already an AP and already powered** for W1.
- **It is present when the Terminal is not**, which matters for a network whose store-and-forward relays traffic for seven days.

The Terminal reaches the mesh through its own Adapter over W1 either way, so
this costs the Terminal nothing.

### C2 — All Adapters use one fixed Wi-Fi channel

ESP-NOW peers must sit on the same Wi-Fi channel, and a device acting as an
AP has its channel fixed by that role. If every Adapter picks its own
channel, W1 and W2 cannot both work: two Adapters serving their Terminals on
channels 6 and 11 cannot peer with each other.

So the Adapter's AP channel is a network-wide constant, not a per-device
choice.

The cost is real and should be stated: in a dense building every GRIDNET
Adapter contends on one 2.4 GHz channel, alongside whatever else is there.
GRIDNET's own traffic is kilobits, so this is tolerable, but it is a
deliberate trade rather than a free choice.

### C3 — Two interfaces, one router — not a priority list

This replaces `protocol.md`'s Automatic Channel Selection table.

A node has two routing interfaces, `PLC` and `MESH`. Neighbours are
discovered independently on each — passively, per [`routing.md`](routing.md)
— and a neighbour may appear on one, the other, or both. Destination
selection is per destination, by metric. There is no global ranking, and no
"the wire is damaged" state to detect: a PLC path that stops working simply
stops being advertised, and the mesh path wins on its own.

This is also what makes [`routing.md`](routing.md)'s per-interface split
horizon meaningful — there are now genuinely two interfaces for it to apply
to.

### C4 — `hop_count` becomes a cost, in the same byte

A hop is not a hop. One PLC hop and one mesh hop differ by roughly two
orders of magnitude in both throughput and energy, so counting them equally
would make the router prefer a slow, expensive one-hop PLC path over a fast,
cheap two-hop mesh path.

`RouteEntry`'s existing 1-byte field is reinterpreted — no format change,
still 5 bytes per entry:

| | Cost |
|---|---|
| Mesh hop | 1 |
| PLC hop | 4 |
| Unreachable (poison) | 64 |

Valid costs are 0–63, which allows fifteen PLC hops or sixty-three mesh
hops before the loop-prevention cap bites. This supersedes
[`routing.md`](routing.md)'s hop cap of 15 and poison value of 16.

**4:1 is deliberately conservative**, and not derived from the ~200×
throughput ratio. Metric ratios that large would send traffic down
arbitrarily long mesh chains, where each extra hop adds latency, another
relay that must be awake, and another chance to fail. 4:1 means "accept up
to three extra mesh hops to avoid one PLC hop", which is enough to prefer
the mesh in the case that actually matters — a neighbour on another phase,
one mesh hop away — without chasing it across a building. It should be
retuned once mesh reach and ESP-NOW throughput have been measured.

## What this does not settle

**Nothing here is measured.** Cross-phase attenuation, mesh reach through
real walls, and ESP-NOW's effective throughput for small frames are all
taken from general knowledge and datasheet-class reasoning. All three want
the same prototype survey that [`routing.md`](routing.md) already asks for.

**The Adapter has no storage for store-and-forward.** C1 puts the mesh on a
unit whose flash is not allocated for holding a week of messages. If
Adapters relay while Terminals sleep, either they need that allocation or
relaying stops when the Terminal does — which weakens the seven-day
retention promise in exactly the conditions that promise is for.

**Wi-Fi weakens the threat model's physical anchor.**
[`threat-model.md`](threat-model.md) leans on the fact that transmitting
requires being plugged into the same conductor. Radio crosses walls and
reaches the street, so the mesh interface has a wider adversary set than the
PLC one. Per-neighbour quotas should be tighter on `MESH` than on `PLC`, and
that is unspecified.

**The README's premise needs rewording, not just its diagram.** "Communicate
over the power grid" is accurate for one transformer district and one phase
within it. Everything beyond that is radio.

---

Last updated: 2026 — REV 0.1
