# GRIDNET — Threat Model

**REV 0.1**

This document says who GRIDNET defends against, who it does not, and why.
It exists because the protocol had no authentication of any kind and no
statement of what that cost — see the top-level README's "Known Gaps" and
[`protocol.md`](protocol.md)'s "Security — What Is Not Protected".

Nothing here is implemented yet. This is the analysis the implementation
should follow, and the decisions are recorded so they don't have to be
re-derived.

## Scope

**In scope: a hostile neighbour on the same wire.** Someone in the building
or the street who modifies their own device — flashes their own firmware,
transmits arbitrary frames, lies in the protocol. This is the realistic
adversary for a neighbourhood network and the one whose attacks are most
concrete.

**Out of scope, deliberately:**

| Not defended | Consequence, stated plainly |
|---|---|
| Device theft / physical access | The private key sits in flash. Whoever holds the device can impersonate it. There is no PIN, no at-rest encryption, no revocation. |
| A resourceful targeted adversary | A utility, law enforcement or an organised actor doing traffic analysis, long-term capture or supply-chain work. An open-hardware hobby project cannot honestly claim defence here. |
| Confidentiality | Messages stay plaintext on the wire and in every relay's 7-day queue. Encryption is separate work, not in this pass. |
| Traffic analysis | Who talks to whom, when, and how much is visible to anyone on the wire, signed or not. |
| Jamming | Anyone can inject noise onto the conductor. There is no defence at this layer and no plan for one. |

These are choices, not oversights. Widening the scope to device theft
would pull in revocation, key rotation and an unlock step — and an unlock
step on a device whose purpose is to work during an earthquake is a
usability decision, not just a security one.

## The trust anchor is physical, not cryptographic

GRIDNET has a property most networks don't: **to send a packet you must be
physically connected to the conductor.** Not a subscription, not an IP
address — a plug in a socket on the same low-voltage segment, behind the
same distribution transformer.

This bounds the adversary set to people who are physically present, and it
is what makes Sybil attacks expensive here. Minting a thousand identities
is free — an Ed25519 keypair costs nothing — but a thousand identities
transmitting from one flat is still one wire, one CSMA/CA participant, one
physical location. Quotas should therefore be **per neighbour**, meaning
per node observed at one hop, not per identity.

Wi-Fi mesh fallback weakens this: RF crosses walls and reaches the street.
Anything relying on the physical anchor is weaker in fallback mode, and the
fallback path should be treated as the more exposed one.

## Assets

1. **Message integrity and attribution** — that a message from `01.03.07.12` was written by whoever holds `01.03.07.12`.
2. **Routing correctness** — that traffic reaches its destination rather than an interceptor.
3. **Availability of the channel** — 2.4–9.6 kbps is scarce; airtime and queue space are exhaustible.
4. **Integrity of distributed code** — Forth applications move peer-to-peer and execute on arrival.

## Attacks

Each of these is reachable today with a modified node and no special
equipment.

### A1 — Source spoofing

`SRC` is a plaintext field verified by nothing. Any node transmits as any
address. Everything below builds on this.

### A2 — ROUTE poisoning

The routing layer is distance-vector with no authentication. A node
advertises `hop_count 0` for an address it does not own and pulls that
traffic to itself. There is no split-horizon or poison-reverse either, so
the false entry propagates outward one hop per 60s cycle.

### A3 — Forged emergency broadcast

`BROADCAST 0x03` floods the whole mesh and is signed by nothing. In the
disaster scenario this system exists for, a forged "gas leak, evacuate" is
the highest-consequence attack in this list.

### A4 — Store-and-forward exhaustion

Every node holds messages for up to 7 days on behalf of senders it cannot
identify. Filling neighbours' queues costs the attacker only airtime.

### A5 — Unverified code distribution

`APP_DATA 0x10` moves executable Forth between peers whose identity is not
established. The VM sandbox bounds what the code can do once running; it
says nothing about where the code came from.

### A6 — Replay

`SEQ` is a 2-byte sequence number for ordering and duplicate suppression,
not a nonce. A captured packet can be retransmitted.

### A7 — Duplicate address

Addresses are self-assigned with no registry and no duplicate detection
(see [`protocol.md`](protocol.md)). Two nodes claiming `01.03.07.12` both
answer for it, and the distance-vector table oscillates. This is reachable
by accident as well as on purpose.

## Decisions

### D1 — Identity is an Ed25519 key, bound to an address by trust-on-first-use

The hierarchical address stays exactly as it is: human-readable,
self-assigned, `01.03.07.12`. It is a *name*, not a credential.

Each node generates an Ed25519 keypair on first boot. The first time a node
sees an address, it pins the key that came with it. If a different key later
claims the same address, the user is shown a conflict rather than one
silently winning:

```
!! 01.03.07.12 is presenting a different key
   expected  9f3a...c1   (first seen 12 March)
   received  d802...7a
   [accept]  [reject]  [verify in person]
```

This is SSH's model. It needs no registry, no authority and no coordination
— which matters for a network whose entire premise is that infrastructure
has failed.

**Its weakness is first contact**, and it is a real one: an attacker who
gets there first owns the address on that device. There is no fix within
TOFU. What mitigates it in practice is that neighbours can compare
fingerprints face to face, and that A7 above means duplicate-address
conflicts must surface to the user anyway.

Cryptographic addresses (address derived from the key) would close first
contact completely and were rejected: they would delete the readable
hierarchy, the CITY/DISTRICT/BUILDING/UNIT structure and the geographic
routing that depends on it.

### D2 — Signing is tiered

| Packet | Signed | Why |
|---|---|---|
| `ROUTE` 0x04 | Always | A2 — highest-value target, and a bounded, predictable 60s cadence |
| `BROADCAST` 0x03 | Always | A3 — highest consequence, and rare |
| `APP_DATA` 0x10 | Always | A5 — executable code |
| `IDENT` (new) | Always, self-signed | Identity records must carry their own proof |
| `MSG` 0x01 | Optional, per message | Airtime; user-visible as verified or not |
| `ACK` 0x02, `GAME_*` | Unsigned | Low value, high frequency |

The airtime argument, at 2.4 kbps (3.33 ms/byte, worst case):

| Packet | Now | With a 64-byte signature |
|---|---|---|
| Short message, 40B payload | 59B → 197ms | 123B → 410ms (**+108%**) |
| Full-size `ROUTE`, 255B payload | 274B → 913ms | 338B → 1127ms (+23%) |

Signing every packet costs a short message more than double its airtime, in
a band where airtime is the scarcest resource and is scarcest exactly when
everyone needs it at once. Signing the four types above costs far less and
covers every attack in the list that authentication can address at all.

### D3 — The signed flag is free

`TYPE` is one byte carrying codes `0x01`–`0x12`. Bit 7 is unused. `TYPE |
0x80` means "a 64-byte Ed25519 signature follows the payload". No new
header field, no bytes spent on negotiation.

The signature covers `LEN ‖ SRC ‖ DST ‖ SEQ ‖ TYPE ‖ PAYLOAD`. `CRC16` is
computed over everything including the signature — it is there for bit
errors, not for security, and this ordering keeps it that way.

### D4 — Two new packet types for key distribution

- **`IDENT` 0x05** — a self-signed record binding an address to a public key. 4B address + 32B key + 64B signature = 100B payload, ~397ms on air. Broadcast on join and in response to a request.
- **`IDENT_REQ` 0x06** — asks for the key belonging to an address. 4B payload.

Keys are not carried in ordinary packets. A node that receives a signed
packet from an unpinned address requests the identity once and caches it.

### D5 — Crypto runs on the ESP32-C3, and that moves the private key

Ed25519 verification on the GD32VF103 (RV32IMAC, 108MHz, no accelerator) is
roughly 10M cycles ≈ 93ms — about 1.5% CPU at ten neighbours advertising
once a minute, which is affordable. **Its working set is not.** Ed25519
needs 1–2KB of stack, and `ROUTER`'s task stack is 2048B total
([`firmware-arch.md`](firmware-arch.md)).

The ESP32-C3 is the better home regardless: 160MHz, and SHA-256 in
hardware, which is the bulk of Ed25519's cost.

The consequence is architectural, not just a code-placement choice. **The
keypair should be generated on the ESP32-C3 and never leave it** — the
GD32VF103 asks for a signature over a buffer and receives 64 bytes back
over the existing 115200-baud UART. Passing the private key across that
UART instead would put it in two places and on a wire, for no benefit.

This means the identity belongs to the ESP32-C3 module, so replacing that
module changes the node's identity. That is a real consequence and should
be documented for users, not discovered by one.

## What this does not fix

Three things stay broken after all of the above, and stating them is the
point of writing a threat model at all.

**Signing proves authorship, not truth.** A signed `ROUTE` packet proves
who advertised a route. It does not prove the route exists. A node can
honestly sign a claim that it has a 1-hop path to an address it cannot
reach, absorb the traffic and drop it. Authentication converts an anonymous
attack into an attributable one — the liar can be identified, pinned and
blocked — but it does not make distance-vector routing trustworthy.
Actually detecting the blackhole needs end-to-end evidence, such as whether
traffic routed via a neighbour ever produces an ACK. That is unspecified
work.

**Replay is bounded, not solved.** A per-source sliding window over `SEQ`,
persisted across reboots alongside the pin store, rejects duplicates and
old sequence numbers. But `SEQ` wraps at 65536, clocks are not synchronised
(the Terminal has a DS3231; the Adapter has no RTC at all), and a disaster
network cannot assume time sync. For `ROUTE` the 60s cadence and the
3-interval staleness rule bound the value of a replay to one advertisement
window. For `MSG` the window is weaker.

**Availability is not addressed.** Signing does nothing about jamming, and
per-neighbour quotas limit queue exhaustion without preventing an attacker
from spending their own airtime to make everyone else's worse.

## A finding that came out of this analysis

`ROUTE` does not scale, independently of anything security-related.

A full-size advertisement occupies the channel for ~913ms. At the specified
60s interval:

| Neighbours | Channel used by routing | With signatures |
|---|---|---|
| 10 | 15.2% | 18.8% |
| 20 | 30.4% | 37.6% |

An apartment building on one distribution segment can easily reach twenty
nodes. Signatures add 23% relative — they are not the problem. The 60s
interval against a 255-byte table on a 2.4 kbps link is the problem, and it
needs revisiting on its own terms: a longer interval, incremental rather
than full-table advertisements, or a smaller table.

## Open questions

1. **First-contact hardening.** Is there a practical out-of-band step — a fingerprint shown on screen, compared at the door — that fits the disaster use case rather than assuming calm conditions?
2. **Blackhole detection.** Is end-to-end ACK evidence worth its complexity at this scale, or is attributability enough?
3. **`SEQ` width.** Two bytes was sized for duplicate suppression, not for anti-replay. Widening it is a wire-format change and should be decided before the format is frozen, not after.
4. **Encryption.** Once every node has an Ed25519 key, X25519 key agreement is a small addition and would close the confidentiality gap. Deliberately not in this pass, but the key infrastructure here is most of the prerequisite.

---

Last updated: 2026 — REV 0.1
