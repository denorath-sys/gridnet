GRIDNET — Inverter Master Protocol
Problem
When grid power fails, every GRIDNET device on the same segment could attempt to inject 24V AC onto the wire simultaneously. This would cause:

Voltage conflict — two voltage sources on the same wire at different phases cancel or distort each other
Signal corruption — PLC packets become unreadable
Excess current — multiple injectors could push more current than the coupling transformers are designed for

The inverter master protocol solves this by ensuring exactly one device injects at any time.

Core Rule

In any given segment, only the lowest-address active device acts as master inverter.
All other devices remain passive — they receive and repeat signals but do not inject.


State Machine
Each device operates one of three inverter states:
┌─────────────────────────────────────────────────────────┐
│                    INVERTER STATES                      │
├──────────────┬──────────────────────────────────────────┤
│ GRID_ON      │ Grid power present — inverter off        │
│ INV_MASTER   │ Grid off, I am injecting 24V AC          │
│ INV_SLAVE    │ Grid off, another device is injecting    │
└──────────────┴──────────────────────────────────────────┘
State transitions:
GRID_ON ──── grid fails (I witnessed it myself) ────→ LISTEN (short: 2s + jitter)
device powers on / rejoins while grid already off ──→ LISTEN (long: 12s + jitter)
                                                        │
                                        ┌───────────────┴───────────────┐
                                        │ 24V detected on wire?         │
                                        ├───────────────────────────────┤
                                       YES                              NO
                                        │                               │
                                        ▼                               ▼
                                   INV_SLAVE                      INV_MASTER
                                        │                               │
                              master silent 30s                master alive
                                        │                               │
                                        ▼                               │
                              am I lowest address?                      │
                                   YES → INV_MASTER ←──────────────────┘
                                    NO → keep waiting

INV_MASTER or INV_SLAVE ──── grid returns ──────→ GRID_ON

REV 0.5: there are now two different listen delays feeding the same LISTEN
state, not one. A device that just watched its own grid power fail knows no
master can already exist (grid was on for it a moment ago), so it's safe to
listen briefly and assert quickly. A device that's powering on or rejoining
while the grid is *already* off has no idea how long the outage has been
running or whether a master is already active — it must listen long enough
to be sure it would have heard one. See "Timing Parameters" and "Design
Notes — REV History" below for why both delays changed from REV 0.4.

Protocol Messages
MASTER_ALIVE
Broadcast by the current master every 10 seconds.
ctypedef struct {
    uint8_t  type;        // 0x05 = MASTER_ALIVE
    uint8_t  src[4];      // Master's address
    uint16_t seq;         // Sequence number
    uint8_t  voltage;     // Injected voltage in V (24)
    uint8_t  battery_pct; // Master's battery level
} MasterAlivePacket;      // 9 bytes
MASTER_RESIGN
Sent by master when it needs to stop injecting (low battery, user shutdown, etc.)
ctypedef struct {
    uint8_t  type;        // 0x06 = MASTER_RESIGN
    uint8_t  src[4];      // Resigning master's address
    uint8_t  reason;      // 0x01=low battery, 0x02=shutdown, 0x03=grid_returning
} MasterResignPacket;     // 7 bytes

Master Selection Algorithm
When a device needs to select a new master (after 30s silence or MASTER_RESIGN):
cvoid select_new_master(void) {
    // Collect known active nodes from routing table
    // Filter: last seen within 60 seconds
    // Sort by address (ascending)
    // First in list = new master candidate

    if (candidate_address == my_address) {
        become_master();
    } else {
        // Wait 5 more seconds for candidate to assert
        // If still no MASTER_ALIVE, try next address
    }
}
Tie-breaking: Address 01.03.07.11 wins over 01.03.07.12 — lower address has priority.

New device joining (REV 0.5): A new/rebooting device always listens first — but which listen delay it uses depends on whether it just witnessed the grid failing itself, or is joining an outage already in progress:
- Grid just failed for me too (grid_lost): short listen (2s + jitter) is safe — by definition no master can exist yet, since the grid was on for me a moment ago.
- Powering on / rejoining while the grid is already off (cold_join): long listen (12s + jitter), covering a full MASTER_ALIVE cycle plus margin. A device in this state cannot assume a master doesn't exist just because it hasn't heard one yet.
If it hears MASTER_ALIVE during its listen window, it becomes a slave. If not, it becomes master.

Timing Parameters
ParameterValueRationaleInitial listen delay2 seconds + random(0–500ms) jitterAllow other devices to assert first; jitter spreads out timeouts that would otherwise fire at the exact same instant during a segment-wide outage (see REV History)Cold-join listen delay (REV 0.5)12 seconds + random(0–500ms) jitter = MASTER_ALIVE interval + 2s marginA device that didn't witness the grid failure firsthand must listen a full heartbeat cycle before assuming no master exists (see REV History)MASTER_ALIVE interval10 secondsBalance between overhead and responsivenessMaster timeout30 seconds3 missed heartbeats before failoverFailover grace period5 secondsPrevent split-brain during brief signal lossRelay switching time20msZero-crossing alignment, prevents sparking

Interaction With CSMA/CA
The inverter master protocol operates at the hardware/energy layer, while CSMA/CA operates at the data/packet layer. They are independent and complementary:
LayerMechanismPreventsEnergyInverter master protocolMultiple devices injecting simultaneouslyDataCSMA/CAMultiple devices transmitting packets simultaneously
A device can be INV_SLAVE (not injecting energy) while still transmitting data packets — it listens on the wire powered by the master's 24V injection.

Failure Scenarios
Master battery dies suddenly
Master stops broadcasting MASTER_ALIVE
  → 30 seconds silence
  → All slaves detect timeout
  → Lowest-address slave becomes new master
  → Network continues with brief interruption (~30s)
Two devices think they are master (split-brain)
Possible if MASTER_ALIVE packets are lost in both directions:
Both devices inject simultaneously
  → Voltage conflict detected (V-Sense sees unexpected waveform)
  → Both devices immediately stop injecting
  → Re-run master selection from scratch
  → Lower-address device wins
The V-Sense circuit (voltage sensing on the line) detects voltage conflicts within 1 cycle (~7 microseconds at 148kHz) and triggers an immediate shutdown.
All devices have equal address (misconfiguration)
Should not happen with proper setup, but handled:
Tie-breaking by sequential number embedded in packet
Lower sequential number wins
User is notified of address conflict on screen

Implementation Notes
c// Channel mode enum (Zephyr firmware)
typedef enum {
    CHAN_PLC_NORMAL,    // Grid on, normal PLC operation
    CHAN_INV_MASTER,    // Grid off, I am injecting
    CHAN_INV_SLAVE,     // Grid off, another device is injecting
    CHAN_MESH_WIFI,     // Wire damaged, using Wi-Fi mesh
} ChannelMode;

// Master state (persisted in RAM, not Flash — reset on reboot)
typedef struct {
    ChannelMode  mode;
    uint8_t      master_addr[4];
    uint32_t     last_alive_ms;
    uint8_t      is_master;
} InverterState;

Design Notes — REV History

REV 0.5 changed two timing values after both were exercised against a
software reference implementation of this protocol (tools/protocol-sim/,
which runs this state machine — not a mockup of it — against the scenarios
below). Neither issue is hypothetical; both reproduced from the REV 0.4 text
exactly as written, every run, not as rare edge cases.

1. Segment-wide outage → split-brain was the common case, not the fallback.
   REV 0.4's initial listen delay was a flat 2 seconds with no jitter. The
   most common real trigger for this whole protocol — an entire building or
   block losing grid power at once — meant every device on the segment hit
   that 2-second timeout at the exact same instant and every one of them
   tried to become master simultaneously, every time. Split-brain detection
   resolved it correctly (lower address wins), but that made split-brain the
   *primary* path for the most common outage pattern, not the rare fallback
   the "Failure Scenarios" section frames it as — directly working against
   this document's own rationale for avoiding simultaneous injection
   ("voltage conflict... signal corruption... excess current"). Fix: the
   initial listen delay is now 2s + random(0–500ms) jitter, so whichever
   device draws the shortest delay usually asserts first and the others hear
   it and become slaves normally — split-brain remains as a safety net for
   the residual case where two devices draw a near-identical jitter value,
   it's just no longer the expected path.

2. A new device could steal mastership from an already-stable master.
   REV 0.4 stated "a new device always listens first," using the same 2s
   delay for joining as for a fresh grid failure. But 2 seconds is much
   shorter than the 10-second MASTER_ALIVE interval, so a device joining at
   an arbitrary moment only had roughly a 20% chance of its listen window
   actually overlapping a heartbeat. The other ~80% of the time it heard
   nothing, timed out, and declared itself master — and if its address
   happened to be lower than the existing master's, it won the resulting
   split-brain and forced an already-running master to resign: a real
   service interruption caused purely by unlucky join timing, not any actual
   fault. Fix: joining a segment is no longer routed through the same short
   listen delay as a self-witnessed grid failure. A new/rebooting device
   uses a listen window sized to reliably span a full heartbeat cycle
   (MASTER_ALIVE interval + margin) instead, so it doesn't need luck to hear
   an existing master before speaking up.

Related Documents

docs/protocol.md — Full protocol stack including packet format
docs/electrical-safety.md — Why 24V injection is safe
hardware/bom.md — Protection circuit components
tools/protocol-sim/ — Reference implementation and test suite for this state machine


Last updated: 2026 — REV 0.5
