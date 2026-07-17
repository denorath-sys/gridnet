GRIDNET — Communication Protocol Stack
Overview
GRIDNET uses a custom lightweight protocol designed for low-bandwidth, high-latency powerline communication. Every device is both a node and a repeater.

Physical Layer
ParameterValueTechnologyPLC (Powerline Communication)ChipST7580 (STMicroelectronics)StandardCENELEC EN50065, A-bandFrequency9–148 kHzModulationOFDM / FSKTypical data rate2.4–9.6 kbpsFallbackESP32-C3 Wi-Fi 2.4GHz mesh

Packet Format
[AA AA AA] [55] [LEN 2B] [SRC 4B] [DST 4B] [SEQ 2B] [TYPE 1B] [PAYLOAD] [CRC16 2B]
 preamble   sync   len    source    dest      seq      type       data      checksum
Total header size: 15 bytes
Maximum payload: 256 bytes
Broadcast address: FF.FF.FF.FF

Addressing
Hierarchical 4-byte address — no central registry required:
[CITY 1B] [DISTRICT 1B] [BUILDING 1B] [UNIT 1B]
   01           03            07           12      →  01.03.07.12
Addresses are self-assigned. Collision detection via CSMA/CA.

Message Types
TypeCodeDescriptionMSG0x01Standard messageACK0x02Delivery acknowledgementBROADCAST0x03Emergency broadcast, all nodesROUTE0x04Routing table updateMASTER_ALIVE0x05Inverter master heartbeatAPP_DATA0x10Forth application dataGAME_STATE0x11Game state packetGAME_ACTION0x12Game action packet

Mesh Routing

Every device maintains a neighbor table (address, hop count, last seen) — populated by periodic ROUTE broadcasts, see "ROUTE Packet" below
Unknown destination: flooded to all neighbors, each device repeats once
Store-and-forward: if destination is unreachable, message is stored for up to 7 days
Every device acts as a repeater automatically
CSMA/CA collision avoidance: listen before transmit, back off if channel busy

ROUTE Packet (REV 0.5)

Distance-vector routing table advertisement — this is how the neighbor table above actually learns hop counts beyond 1, which REV 0.4 left unspecified. Unlike MSG/APP_DATA, a ROUTE packet is never flooded/relayed across the mesh; instead every device periodically re-broadcasts its own table (already hop-incremented) on its own schedule, and the information spreads outward one hop per advertisement cycle — the same mechanism RIP uses.

ctypedef struct {
    uint8_t  type;          // 0x04 = ROUTE
    uint8_t  src[4];         // Advertiser's address
    uint16_t seq;             // Sequence number
    RouteEntry entries[];      // One per known destination, packed back-to-back
} RoutePacket;

ctypedef struct {
    uint8_t  address[4];    // Destination address
    uint8_t  hop_count;      // Hops from the advertiser to this destination (0 = the advertiser itself)
} RouteEntry;                // 5 bytes per entry — up to 51 entries fit in one 256-byte payload

Every device always includes itself at hop_count 0. On receipt, a device compares each entry's (hop_count + 1) against its own table and keeps the lower value, recording the sender as next_hop. A device discards any incoming entry whose address is its own — the minimal loop-prevention this simplified distance-vector scheme relies on (no split-horizon/poison-reverse).

Hop counts are capped at 15 (RIP-style "infinity"); entries at or above the cap are dropped rather than propagated further, bounding runaway counts across a brief segment partition/reconnect. An entry not refreshed within 3 advertisement intervals (180s) is considered stale and dropped from that device's own next advertisement — the same "3 missed heartbeats" convention docs/inverter-master.md uses for MASTER_TIMEOUT.

Advertisement interval: 60 seconds. Much longer than MASTER_ALIVE's 10s, deliberately: a full table (up to 255 bytes of payload) costs meaningfully more airtime than a 9-byte heartbeat on a 2.4–9.6kbps link — at 2.4kbps, one full-size ROUTE broadcast occupies the channel for roughly 900ms, so every device doing this too often would eat directly into the bandwidth available for MSG traffic. Routing information is also far less time-critical than the inverter master heartbeat, which gates a physical 24V injection decision.

Automatic Channel Selection
Priority order, evaluated continuously:
PriorityChannelConditionCurrent draw1Powerline (PLC)Grid power on, line intact~58mA2Inverter + PLCGrid off, line physically intact~260mA3Wi-Fi MeshLine damaged or PLC failed~138mA
Transition time between channels: < 20ms (relay-controlled).

Inverter Master Protocol
When grid power fails, only one device per segment injects 24V AC onto the wire to prevent voltage conflicts.
Grid power lost
  → Wait 2 seconds
  → Listen for 24V AC on wire
      YES → Another device is master → enter passive mode
      NO  → Become master → start injecting 24V AC

Master behavior:
  → Broadcast MASTER_ALIVE packet every 10 seconds
  → If no MASTER_ALIVE received for 30 seconds:
      → Lowest-address active device becomes new master
Why only one master?
Multiple devices injecting simultaneously cause voltage conflicts and signal corruption. The master selection protocol ensures exactly one inverter is active per segment at any time.

Electrical Safety

Injected voltage: 24V AC (safe per IEC 60479, below 50V AC threshold)
Injected current: max 100mA (household breakers trip at 16A)
Frequency: 9–148kHz — consumer electronics naturally filter this band
Standard compliance: CENELEC EN50065 A-band
Galvanic isolation: ST7580 and inverter always connect through transformer — no direct line connection


Forth Application Protocol
Forth applications communicate using TYPE 0x10 packets:
ctypedef struct {
    uint8_t  app_id[8];     // Application identifier
    uint8_t  msg_type;      // Application-defined message type
    uint8_t  payload[247];  // Application data
} AppPacket;
Security constraints enforced by VM sandbox:

Source address locked — app cannot spoof sender
Rate limit: 5 packets/second per application
Max message size: 256 bytes
Broadcast requires explicit permission flag
Filesystem isolation: each app can only access its own directory


Last updated: 2026 — REV 0.5
