GRIDNET — Communication Protocol Stack
Overview
GRIDNET uses a custom lightweight protocol designed for low-bandwidth, high-latency powerline communication. Every device is both a node and a repeater.

Physical Layer
ParameterValueTechnologyPLC (Powerline Communication)ChipST7580 (STMicroelectronics)StandardCENELEC EN50065 (band under review — A-band is utility-only, see docs/electrical-safety.md)Frequency9–148 kHzModulationOFDM / FSKTypical data rate2.4–9.6 kbpsFallbackESP32-C3 Wi-Fi 2.4GHz mesh

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
TypeCodeDescriptionMSG0x01Standard messageACK0x02Delivery acknowledgementBROADCAST0x03Emergency broadcast, all nodesROUTE0x04Routing table updateAPP_DATA0x10Forth application dataGAME_STATE0x11Game state packetGAME_ACTION0x12Game action packet

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

Hop counts are capped at 15 (RIP-style "infinity"); entries at or above the cap are dropped rather than propagated further, bounding runaway counts across a brief segment partition/reconnect. An entry not refreshed within 3 advertisement intervals (180s) is considered stale and dropped from that device's own next advertisement — the usual "3 missed heartbeats" convention.

Advertisement interval: 60 seconds. Deliberately long: a full table (up to 255 bytes of payload) costs meaningfully more airtime than a 9-byte heartbeat on a 2.4–9.6kbps link — at 2.4kbps, one full-size ROUTE broadcast occupies the channel for roughly 900ms, so every device doing this too often would eat directly into the bandwidth available for MSG traffic. Routing information is not time-critical: a stale hop count costs an extra relay, not a lost packet.

Automatic Channel Selection
Priority order, evaluated continuously:
PriorityChannelCondition1Powerline (PLC)Line intact — works whether or not the grid is energised2Wi-Fi MeshLine damaged or PLC failed
During a grid outage the adapter keeps using PLC; what changes is where it gets its power, not which channel it uses. See docs/plc-adapter-power.md.

Operation During a Grid Outage
The wire remains a conductor whether or not the grid energises it, so PLC signalling continues to work. What stops is the adapter's own power supply, which runs from mains. During an outage each adapter is powered by its Terminal's battery over a USB-C cable the user connects; a supercapacitor holds the adapter up long enough to tell the Terminal that mains has gone.
Nothing is injected onto the wire and no arbitration between adapters is needed — every node transmits under CSMA/CA exactly as it does when the grid is up.
Earlier revisions specified a 24V "inverter mode" and an inverter master election protocol here. Both were removed: the adapter had no power source during an outage and so could never have run an inverter, and a 24V injection sits 5-24x outside EN 50065-1's signal limits. See docs/plc-adapter-power.md for the analysis and docs/electrical-safety.md REV 0.6 for the compliance correction.

Electrical Safety

Signal level: bounded by EN 50065-1 — 5 Vrms at 9 kHz falling to 1 Vrms at 95 kHz. The ST7580's PA delivers 14 V p-p (4.95 Vrms); the adapter adds a hardware current limit as a backstop.
Nothing is injected onto the wire — GRIDNET signals, it does not energise.
Frequency: consumer electronics naturally filter the CENELEC band
Band allocation: A-band (9–95 kHz) is for electricity suppliers; general equipment belongs in 95–148.5 kHz. This document still says A-band above and needs updating — the largest open compliance item in the project.
Galvanic isolation: the ST7580 reaches the line only through the coupling transformer, and the Terminal's USB-C cable sits on the isolated secondary


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
