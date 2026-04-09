GRIDNET — Electrical Safety Analysis
Overview
GRIDNET injects 24V AC onto the power line when grid power fails. This document analyzes the safety of this approach for household equipment, other devices on the same network, and humans.
Summary: The 24V AC injection is safe for all connected equipment and humans, and is compliant with CENELEC EN50065.

Why 24V AC Injection Is Safe for Household Equipment
1. Voltage Difference
ParameterGridGRIDNET InverterVoltage230V AC24V ACFrequency50 Hz9–148 kHz (PLC band)CurrentUp to 16A (breaker limit)Max 100mA
Household appliances are designed for 230V / 50Hz. The 24V AC signal at kilohertz frequencies is completely irrelevant to their power circuits.
2. Frequency Filtering
PLC signals operate at 9–148 kHz — between 180 and 3000 times the grid frequency. Consumer electronics power supplies, transformers, and filter capacitors are designed for 50Hz and naturally attenuate signals at kilohertz frequencies. The PLC signal is invisible to household devices.
This is the same principle used by HomePlug, G.hn, and other powerline networking technologies deployed in millions of homes for over two decades without reported equipment damage.
3. Current Limitation
GRIDNET injects a maximum of 100mA onto the wire. For reference:

The smallest USB phone charger draws ~500mA
A household circuit breaker trips at 16A (160× more than GRIDNET's injection)
The injected current is too small to affect any connected load


Why the Injection Is Safe for Humans
Per IEC 60479 (Effects of current on human beings and livestock):

Voltages below 50V AC are classified as SELV (Safety Extra-Low Voltage)
Under normal dry conditions, voltages below 50V AC do not cause ventricular fibrillation
GRIDNET injects 24V AC — well below the 50V threshold

Additionally, the signal is at high frequency (9–148 kHz). At these frequencies, the body's impedance is higher than at 50Hz, further reducing any physiological effect.

Standard Compliance
CENELEC EN50065
GRIDNET operates in the A-band of CENELEC EN50065:
BandFrequencyUsersA9–95 kHzEnergy companies, smart meters, GRIDNETB95–125 kHzHome automationC125–140 kHzHome automation (CSMA)D140–148 kHzAlarm systems
The A-band is specifically defined for signaling on public electricity networks. Devices operating in this band are legally permitted to inject signals onto the power line in Europe, provided they meet the signal level limits defined in the standard.
GRIDNET's 24V AC, 100mA injection is within these limits.
IEC 60479
Classifies 24V AC as non-hazardous under normal dry conditions. Full compliance with SELV (Safety Extra-Low Voltage) definition.

Inverter Master Protocol — Preventing Voltage Conflicts
If multiple GRIDNET devices on the same segment all inject simultaneously, the signals would interfere with each other. The inverter master protocol prevents this:
Grid power fails
  → All devices wait 2 seconds and listen
  → Is 24V AC present on the wire?
      YES → Another device is already injecting → stay passive
      NO  → Become master → start injecting

Master device:
  → Broadcasts MASTER_ALIVE packet every 10 seconds
  → If no MASTER_ALIVE for 30 seconds:
      → Lowest-address active device becomes new master
Result: Exactly one device injects at any time. Maximum current on the wire: 100mA.

Protection Circuit
The adapter includes a three-layer protection circuit that handles:
Layer 1 — Transient Suppression

TVS Diode: P6KE250CA (bidirectional, 250V clamp)
Absorbs fast voltage spikes (lightning, switching transients)
Response time: < 1 picosecond

Layer 2 — Sustained Overvoltage

MOV: S20K275 (275V varistor)
Handles sustained overvoltage conditions
Self-resetting after overvoltage clears

Layer 3 — Isolation and Switching

Relay: HK19F — galvanically isolates the inverter from the line when grid is present
Optocoupler: PC817 — isolates control signals (5kV isolation rating)
Voltage sensing circuit — detects grid presence and controls relay

Transition Timing
Grid returns after inverter mode:
  1. V-Sense detects 230V AC present
  2. Inverter stops immediately (< 1ms)
  3. Relay waits 20ms (zero-crossing alignment)
  4. Relay closes, reconnects to grid
  5. Normal PLC mode resumes
This prevents any voltage spike during the transition back to grid power.

Galvanic Isolation
This is mandatory and non-negotiable in the design.
The ST7580 PLC chip and the inverter output always connect to the power line through a transformer. There is no direct electrical connection between the low-voltage digital circuits and the 230V power line.
This means:

The user can never receive a mains voltage shock through the terminal
A fault in the digital circuits cannot energize the mains line
The design complies with basic insulation requirements of IEC 60950/62368


Comparison With Existing Powerline Technologies
TechnologyFrequencyVoltageCurrentIn Use SinceHomePlug AV1.8–30 MHz~1V (signal)< 1mA2001G.hn2–100 MHz~1V (signal)< 1mA2009Smart meter (DLMS)9–95 kHz~1V (signal)< 1mA1990sGRIDNET (inverter mode)9–148 kHz24V100mA—
GRIDNET's inverter mode injects significantly more power than typical PLC systems — this is intentional, as it must be able to drive signal across building transformers and over longer distances. However, it is still well within safe limits.

Frequently Asked Questions
Q: Will GRIDNET damage my neighbor's television / refrigerator / computer?
No. The 24V / 100mA signal at 9–148kHz is filtered out by every household appliance's power supply. The signal is invisible to their power circuits.
Q: Will GRIDNET interfere with my neighbor's HomePlug adapter?
Potentially, if both operate on the same frequency band. GRIDNET uses CSMA/CA (listen-before-transmit) to minimize interference. In a neighborhood scenario, GRIDNET devices cooperate and form a single network rather than interfering with each other.
Q: Is it legal to inject signals onto the power line?
In Europe: Yes, within the CENELEC EN50065 A-band limits. GRIDNET is designed to comply with these limits.
In other regions: regulations vary. Check local EMC regulations before deploying.
Q: What if two GRIDNET devices inject at the same time?
The inverter master protocol prevents this. Only one device injects at any time. See the protocol documentation for details.

Last updated: 2026 — REV 0.4
See also: docs/protocol.md — Inverter Master Protocol section
