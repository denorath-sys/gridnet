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

Every device maintains a neighbor table (address, hop count, last seen)
Unknown destination: flooded to all neighbors, each device repeats once
Store-and-forward: if destination is unreachable, message is stored for up to 7 days
Every device acts as a repeater automatically
CSMA/CA collision avoidance: listen before transmit, back off if channel busy


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


Last updated: 2026 — REV 0.4
