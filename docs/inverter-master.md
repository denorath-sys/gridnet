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
GRID_ON ──────────── grid fails ──────────────────→ LISTEN
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
New device joining: A new device always listens first. If it hears MASTER_ALIVE, it becomes a slave. If not, it waits for the timeout before considering becoming master.

Timing Parameters
ParameterValueRationaleInitial listen delay2 secondsAllow other devices to assert firstMASTER_ALIVE interval10 secondsBalance between overhead and responsivenessMaster timeout30 seconds3 missed heartbeats before failoverFailover grace period5 secondsPrevent split-brain during brief signal lossRelay switching time20msZero-crossing alignment, prevents sparking

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

Related Documents

docs/protocol.md — Full protocol stack including packet format
docs/electrical-safety.md — Why 24V injection is safe
hardware/bom.md — Protection circuit components


Last updated: 2026 — REV 0.4
