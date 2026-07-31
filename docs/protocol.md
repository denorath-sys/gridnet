# GRIDNET — Communication Protocol Stack

## Overview

GRIDNET uses a custom lightweight protocol designed for low-bandwidth, high-latency powerline communication. Every device is both a node and a repeater.

## Physical Layer

| Parameter | Value |
|---|---|
| Technology | PLC (Powerline Communication) |
| Chip | ST7580 (STMicroelectronics) |
| Standard | CENELEC EN50065, bands B+C (A-band is utility-only, see [`electrical-safety.md`](electrical-safety.md)) |
| Frequency | 95–140 kHz — the ST7580 covers 9–148 kHz, but Board 1's coupling network is tuned for B+C and changing that means changing four component values ([`plc-coupling.md`](plc-coupling.md)) |
| Modulation | OFDM / FSK |
| Typical data rate | 2.4–9.6 kbps |
| Fallback | ESP32-C3 Wi-Fi 2.4GHz mesh |

## Packet Format

```
[AA AA AA] [55] [LEN 2B] [SRC 4B] [DST 4B] [SEQ 2B] [TYPE 1B] [PAYLOAD] [CRC16 2B]
 preamble   sync   len    source    dest      seq      type       data      checksum
```

- Total header size: 15 bytes
- Maximum payload: 256 bytes
- Broadcast address: `FF.FF.FF.FF`

There is no authentication field. `SRC` is set by the sender and verified by
nothing — see "Security — What Is Not Protected" below before relying on it.

## Addressing

Hierarchical 4-byte address — no central registry required:

```
[CITY 1B] [DISTRICT 1B] [BUILDING 1B] [UNIT 1B]
   01           03            07           12      →  01.03.07.12
```

Addresses are self-assigned. **Duplicate addresses are not currently
detected.** Earlier revisions of this document attributed collision detection
to CSMA/CA; that is a media-access mechanism, which detects a busy channel and
has no view of addressing at all. Two nodes that both claim `01.03.07.12` will
each answer for it, and the distance-vector table below will oscillate between
them. A duplicate-address probe (claim-on-join, defend-on-conflict, in the
manner of ARP announcement or DHCP `ARPCHECK`) is unspecified work.

## Message Types

| Type | Code | Description |
|---|---|---|
| MSG | `0x01` | Standard message |
| ACK | `0x02` | Delivery acknowledgement |
| BROADCAST | `0x03` | Emergency broadcast, all nodes |
| ROUTE | `0x04` | Routing table update |
| APP_DATA | `0x10` | Forth application data |
| GAME_STATE | `0x11` | Game state packet |
| GAME_ACTION | `0x12` | Game action packet |

## Mesh Routing

- Every device maintains a neighbor table (address, hop count, last seen) — populated by periodic ROUTE broadcasts, see "ROUTE Packet" below
- Unknown destination: flooded to all neighbors, each device repeats once
- Store-and-forward: if destination is unreachable, message is stored for up to 7 days
- Every device acts as a repeater automatically
- CSMA/CA collision avoidance: listen before transmit, back off if channel busy

### ROUTE Packet (REV 0.5)

Distance-vector routing table advertisement — this is how the neighbor table above actually learns hop counts beyond 1, which REV 0.4 left unspecified. Unlike MSG/APP_DATA, a ROUTE packet is never flooded/relayed across the mesh; instead every device periodically re-broadcasts its own table (already hop-incremented) on its own schedule, and the information spreads outward one hop per advertisement cycle — the same mechanism RIP uses.

```c
typedef struct {
    uint8_t  type;          // 0x04 = ROUTE
    uint8_t  src[4];        // Advertiser's address
    uint16_t seq;           // Sequence number
    RouteEntry entries[];   // One per known destination, packed back-to-back
} RoutePacket;

typedef struct {
    uint8_t  address[4];    // Destination address
    uint8_t  hop_count;     // Hops from the advertiser to this destination (0 = the advertiser itself)
} RouteEntry;               // 5 bytes per entry — up to 51 entries fit in one 256-byte payload
```

Every device always includes itself at `hop_count` 0. On receipt, a device compares each entry's (`hop_count` + 1) against its own table and keeps the lower value, recording the sender as `next_hop`. A device discards any incoming entry whose address is its own — the minimal loop-prevention this simplified distance-vector scheme relies on (no split-horizon/poison-reverse).

Hop counts are capped at 15 (RIP-style "infinity"); entries at or above the cap are dropped rather than propagated further, bounding runaway counts across a brief segment partition/reconnect. An entry not refreshed within 3 advertisement intervals (180s) is considered stale and dropped from that device's own next advertisement — the usual "3 missed heartbeats" convention.

Advertisement interval: 60 seconds. Deliberately long: a full table (up to 255 bytes of payload) costs meaningfully more airtime than a 9-byte heartbeat on a 2.4–9.6kbps link — at 2.4kbps, one full-size ROUTE broadcast occupies the channel for roughly 900ms, so every device doing this too often would eat directly into the bandwidth available for MSG traffic. Routing information is not time-critical: a stale hop count costs an extra relay, not a lost packet.

## Automatic Channel Selection

Priority order, evaluated continuously:

| Priority | Channel | Condition |
|---|---|---|
| 1 | Powerline (PLC) | Line intact — works whether or not the grid is energised |
| 2 | Wi-Fi Mesh | Line damaged or PLC failed |

During a grid outage the adapter keeps using PLC; what changes is where it gets its power, not which channel it uses. See [`plc-adapter-power.md`](plc-adapter-power.md).

## Operation During a Grid Outage

The wire remains a conductor whether or not the grid energises it, so PLC signalling continues to work. What stops is the adapter's own power supply, which runs from mains. During an outage each adapter is powered by its Terminal's battery over a USB-C cable the user connects; a supercapacitor holds the adapter up long enough to tell the Terminal that mains has gone.

Nothing is injected onto the wire and no arbitration between adapters is needed — every node transmits under CSMA/CA exactly as it does when the grid is up.

Earlier revisions specified a 24V "inverter mode" and an inverter master election protocol here. Both were removed: the adapter had no power source during an outage and so could never have run an inverter, and a 24V injection sits 5-24x outside EN 50065-1's signal limits. See [`plc-adapter-power.md`](plc-adapter-power.md) for the analysis and [`electrical-safety.md`](electrical-safety.md) REV 0.6 for the compliance correction.

## Electrical Safety

- **Signal level:** bounded by EN 50065-1. The ST7580's PA delivers 14 V p-p (4.95 Vrms); the adapter adds a hardware current limit as a backstop, set to 500 mA rms by a 270R resistor on `CL`.
- **Nothing is injected onto the wire** — GRIDNET signals, it does not energise.
- **Frequency:** consumer electronics naturally filter the CENELEC band.
- **Band allocation:** A-band (9–95 kHz) is for electricity suppliers; general equipment belongs in 95–148.5 kHz. GRIDNET uses B (95–125 kHz) and C (125–140 kHz) — C requires an access protocol, which is the CSMA/CA above. D (140–148.5 kHz) is reserved for alarm and security systems and is not used. The hardware now commits to this: see [`plc-coupling.md`](plc-coupling.md). What remains open is the measurement — harmonic suppression is inherently tighter in B+C than in the A band, and no EN 50065-1 conformance claim is justified before a conducted-emission sweep on a prototype.
- **Galvanic isolation:** the ST7580 reaches the line only through the coupling transformer, and the Terminal's USB-C cable sits on the isolated secondary.

## Forth Application Protocol

Forth applications communicate using TYPE `0x10` packets:

```c
typedef struct {
    uint8_t  app_id[8];     // Application identifier
    uint8_t  msg_type;      // Application-defined message type
    uint8_t  payload[247];  // Application data
} AppPacket;
```

Security constraints enforced by the VM sandbox:

- Source address locked — an app cannot spoof the sender **of its own device**
- Rate limit: 5 packets/second per application
- Max message size: 256 bytes
- Broadcast requires an explicit permission flag
- Filesystem isolation: each app can only access its own directory

## Security — What Is Not Protected

The constraints above are sandbox rules. They bound what a Forth application
can do on the device running it, and they are not a network security model.
At the protocol level:

- **No authentication.** Nothing binds a packet to its claimed `SRC`. A
  modified node — not an app, the node itself — can transmit as any address.
- **No encryption.** Payloads are plaintext on the wire, and plaintext in the
  7-day store-and-forward queue of every device that relays them.
- **No replay protection.** `SEQ` is a 2-byte sequence number for ordering and
  duplicate suppression, not a nonce; nothing prevents a captured packet from
  being retransmitted.
- **Unauthenticated routing.** Any node can advertise `hop_count 0` for an
  address it does not own and attract that traffic (see "ROUTE Packet"). There
  is no split-horizon or poison-reverse either.
- **Unverified application distribution.** `APP_DATA` moves executable Forth
  code between peers whose identity is not established.

By contrast, firmware updates *are* authenticated: Ed25519, verified by the
bootloader before flashing (see [`firmware-arch.md`](firmware-arch.md)). The
asymmetry is not deliberate — the network layer simply has no equivalent yet.

No threat model has been written. Designing message authentication (and
deciding whether it can afford a signature on a 2.4 kbps link at all) is open
work, tracked in the top-level README's "Known Gaps".

---

Last updated: 2026 — REV 0.6
