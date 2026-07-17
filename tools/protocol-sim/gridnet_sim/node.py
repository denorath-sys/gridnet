"""A single GRIDNET device: flooding/store-and-forward mesh routing
(docs/protocol.md) plus the inverter master election state machine
(docs/inverter-master.md).

Timers are implemented with a "stale callback" guard rather than real
cancellation, since the simulator's event queue doesn't support removal: each
state-changing transition bumps `self._inv_epoch`, and every scheduled
inverter-state callback closes over the epoch value at schedule time. When it
fires, it first checks the epoch (and often the state) still matches — if not,
something else already resolved the situation and the callback is a no-op.
"""

from __future__ import annotations

import itertools
import random
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Optional

from .address import BROADCAST, Address
from .medium import Medium
from .packet import MessageType, Packet, PacketError

# --- Inverter master timing (docs/inverter-master.md REV 0.5 "Timing Parameters") ---
LISTEN_DELAY = 2.0
LISTEN_JITTER = 0.5  # spread otherwise-identical timeouts (see grid_lost())
JOIN_LISTEN_DELAY = 12.0  # MASTER_ALIVE_INTERVAL + 2s margin (see cold_join())
MASTER_ALIVE_INTERVAL = 10.0
MASTER_TIMEOUT = 30.0
FAILOVER_GRACE_PERIOD = 5.0
KNOWN_NODE_STALE = 60.0  # "last seen within 60 seconds" candidate filter

# --- Mesh routing timing — not specified in docs/protocol.md, chosen to be
# small relative to the 7-day retention so retries actually happen, and large
# enough relative to DEDUP_WINDOW that a retried packet isn't suppressed as a
# duplicate by nodes that already saw (and forgot) the earlier attempt. ---
DEDUP_WINDOW = 15.0
OUTBOX_RETRY_INTERVAL = 30.0
OUTBOX_EXPIRY = 7 * 24 * 3600.0  # 7 days, per docs/protocol.md

# --- ROUTE / distance-vector timing (docs/protocol.md REV 0.5 "ROUTE Packet") ---
ROUTE_ADVERTISE_INTERVAL = 60.0  # much longer than MASTER_ALIVE: a full table costs real airtime
ROUTE_ENTRY_SIZE = 5  # 4-byte address + 1-byte hop count
MAX_ROUTE_ENTRIES = 256 // ROUTE_ENTRY_SIZE  # fits in one packet's MAX_PAYLOAD
MAX_ROUTE_HOPS = 15  # RIP-style "infinity" — bounds runaway counts across a brief partition
ROUTE_STALE = 3 * ROUTE_ADVERTISE_INTERVAL  # "3 missed heartbeats", same convention as MASTER_TIMEOUT


class InverterState(IntEnum):
    GRID_ON = 0
    LISTEN = 1  # grid just failed / re-electing — deciding master vs slave
    INV_MASTER = 2
    INV_SLAVE = 3


class ResignReason(IntEnum):
    LOW_BATTERY = 0x01
    SHUTDOWN = 0x02
    GRID_RETURNING = 0x03


@dataclass(eq=False)
class OutboxEntry:
    packet: Packet
    added_at: float
    expire_at: float
    attempts: int = 0


@dataclass(eq=False)
class RouteEntry:
    hop_count: int
    next_hop: Address
    last_seen: float


def _pack_route_entries(entries) -> bytes:
    return b"".join(addr.to_bytes() + struct.pack("B", hop_count) for addr, hop_count in entries)


def _unpack_route_entries(payload: bytes):
    usable = len(payload) - (len(payload) % ROUTE_ENTRY_SIZE)
    for offset in range(0, usable, ROUTE_ENTRY_SIZE):
        addr = Address.from_bytes(payload[offset : offset + 4])
        hop_count = payload[offset + 4]
        yield addr, hop_count


class Node:
    def __init__(
        self,
        sim,
        address: Address,
        plc_medium: Optional[Medium] = None,
        wifi_medium: Optional[Medium] = None,
        battery_pct: int = 100,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.sim = sim
        self.address = address
        self.id = str(address)
        self.plc_medium = plc_medium
        self.wifi_medium = wifi_medium
        self.line_intact = True
        self.grid_on = True
        self.battery_pct = battery_pct
        self._rng = rng or random.Random()
        # Deliberately a *separate* RNG from self._rng: self._rng is also
        # used for inverter-master listen-delay jitter (grid_lost/cold_join),
        # and callers frequently seed it for reproducible tests. Drawing from
        # the same stream here would consume state ahead of that jitter draw
        # and silently shift its value depending on unrelated ROUTE timing.
        self._route_rng = random.Random()

        self.outbox: List[OutboxEntry] = []
        self.inbox: List[Packet] = []  # application-delivered messages, for tests/inspection
        self.seen: Dict[tuple, float] = {}
        self.known_nodes: Dict[Address, float] = {}  # PLC-segment neighbors, for master candidacy
        self.routing_table: Dict[Address, RouteEntry] = {}  # multi-hop, from ROUTE advertisements
        self._seq = itertools.count(1)

        self.inverter_state = InverterState.GRID_ON
        self.master_addr: Optional[Address] = None
        self.last_master_alive_heard = float("-inf")
        self._inv_epoch = 0

        if self.plc_medium is not None:
            self.plc_medium.attach(self.id, lambda frame: self._on_receive_raw(frame, self.plc_medium))
        if self.wifi_medium is not None:
            self.wifi_medium.attach(self.id, lambda frame: self._on_receive_raw(frame, self.wifi_medium))

        # Staggered first advertisement (uniform over a full interval) so
        # devices that boot together don't all broadcast their (initially
        # empty) table in lockstep forever after; every advertisement after
        # that is a fixed ROUTE_ADVERTISE_INTERVAL from the previous one.
        self.sim.schedule(self._route_rng.uniform(0, ROUTE_ADVERTISE_INTERVAL), self._advertise_routes)

    def __repr__(self) -> str:
        return f"Node({self.address})"

    def attach_wifi(self, medium: Medium) -> None:
        """Attach a WiFi mesh medium after construction — used by scenarios
        that build the PLC segment first and add WiFi fallback capability
        afterwards."""
        self.wifi_medium = medium
        medium.attach(self.id, lambda frame: self._on_receive_raw(frame, medium))

    # ------------------------------------------------------------------ #
    # Application-level messaging
    # ------------------------------------------------------------------ #

    def send_message(self, dst: Address, payload: bytes, msg_type: MessageType = MessageType.MSG) -> Packet:
        seq = next(self._seq)
        pkt = Packet(src=self.address, dst=dst, seq=seq, type=msg_type, payload=payload)
        entry = OutboxEntry(packet=pkt, added_at=self.sim.now, expire_at=self.sim.now + OUTBOX_EXPIRY)
        self.outbox.append(entry)
        self._attempt_delivery(entry)
        return pkt

    def _attempt_delivery(self, entry: OutboxEntry) -> None:
        if entry not in self.outbox:
            return  # already acked or expired
        if self.sim.now >= entry.expire_at:
            self.outbox.remove(entry)
            self.sim.log(f"{self.address}: {entry.packet} expired undelivered after {entry.attempts} attempt(s)")
            return
        entry.attempts += 1
        self.sim.log(f"{self.address}: sending {entry.packet} (attempt {entry.attempts})")
        self._transmit(entry.packet)
        self.sim.schedule(OUTBOX_RETRY_INTERVAL, lambda: self._attempt_delivery(entry))

    def _send_control(self, dst: Address, msg_type: MessageType, payload: bytes = b"") -> Packet:
        seq = next(self._seq)
        pkt = Packet(src=self.address, dst=dst, seq=seq, type=msg_type, payload=payload)
        self._transmit(pkt)
        return pkt

    def _send_ack(self, original: Packet) -> None:
        self._send_control(original.src, MessageType.ACK, struct.pack(">H", original.seq))

    def _on_ack(self, pkt: Packet) -> None:
        if len(pkt.payload) < 2:
            return
        (acked_seq,) = struct.unpack_from(">H", pkt.payload, 0)
        for entry in self.outbox:
            if entry.packet.dst == pkt.src and entry.packet.seq == acked_seq:
                self.outbox.remove(entry)
                self.sim.log(f"{self.address}: {entry.packet} acknowledged by {pkt.src}")
                return

    # ------------------------------------------------------------------ #
    # Transmission / reception plumbing
    # ------------------------------------------------------------------ #

    def _active_medium(self) -> Optional[Medium]:
        if self.line_intact and self.plc_medium is not None:
            return self.plc_medium
        return self.wifi_medium

    def _transmit(self, pkt: Packet) -> None:
        medium = self._active_medium()
        if medium is None:
            return
        self.seen[pkt.key()] = self.sim.now
        medium.transmit(self.sim, self.id, pkt.encode())

    def _on_receive_raw(self, frame: bytes, medium: Medium) -> None:
        try:
            pkt = Packet.decode(frame)
        except PacketError as exc:
            self.sim.log(f"{self.address}: dropped corrupt frame ({exc})")
            return
        self._handle_packet(pkt, medium)

    def _handle_packet(self, pkt: Packet, medium: Medium) -> None:
        key = pkt.key()
        is_dup = key in self.seen and (self.sim.now - self.seen[key]) < DEDUP_WINDOW
        if medium is self.plc_medium:
            self.known_nodes[pkt.src] = self.sim.now
        if is_dup:
            return
        self.seen[key] = self.sim.now

        if pkt.type == MessageType.MASTER_ALIVE:
            if medium is self.plc_medium:
                self._on_master_alive(pkt)
            return
        if pkt.type == MessageType.MASTER_RESIGN:
            if medium is self.plc_medium:
                self._on_master_resign(pkt)
            return
        if pkt.type == MessageType.ROUTE:
            # Like MASTER_ALIVE/RESIGN: processed locally, never flood-relayed.
            # Unlike them, not restricted to the PLC medium — routing spans
            # both PLC segments and WiFi mesh bridges.
            self._on_route(pkt)
            return

        deliver_to_app = pkt.dst == self.address or pkt.dst == BROADCAST
        if deliver_to_app:
            if pkt.type == MessageType.MSG:
                self.sim.log(f"{self.address}: delivered {pkt}")
                self.inbox.append(pkt)
                if pkt.dst != BROADCAST:
                    self._send_ack(pkt)
            elif pkt.type == MessageType.ACK:
                self._on_ack(pkt)
            else:
                self.sim.log(f"{self.address}: received {pkt}")
                self.inbox.append(pkt)

        if pkt.dst != self.address:
            self._relay(pkt, arrived_via=medium)

    def _relay(self, pkt: Packet, arrived_via: Medium) -> None:
        for medium in (self.plc_medium, self.wifi_medium):
            if medium is not None and medium is not arrived_via:
                medium.transmit(self.sim, self.id, pkt.encode())

    # ------------------------------------------------------------------ #
    # ROUTE / distance-vector routing (docs/protocol.md REV 0.5)
    # ------------------------------------------------------------------ #

    def _active_routes(self):
        """(address, hop_count) pairs still fresh enough to advertise —
        excludes anything not refreshed within ROUTE_STALE or that's already
        hit the hop cap (advertising it further would only push it over)."""
        now = self.sim.now
        return [
            (addr, entry.hop_count)
            for addr, entry in self.routing_table.items()
            if now - entry.last_seen <= ROUTE_STALE and entry.hop_count < MAX_ROUTE_HOPS
        ]

    def _advertise_routes(self) -> None:
        entries = [(self.address, 0)] + sorted(self._active_routes(), key=lambda e: e[1])
        entries = entries[:MAX_ROUTE_ENTRIES]
        payload = _pack_route_entries(entries)
        for medium in (self.plc_medium, self.wifi_medium):
            if medium is not None:
                seq = next(self._seq)
                pkt = Packet(src=self.address, dst=BROADCAST, seq=seq, type=MessageType.ROUTE, payload=payload)
                medium.transmit(self.sim, self.id, pkt.encode())
        self.sim.schedule(ROUTE_ADVERTISE_INTERVAL, self._advertise_routes)

    def _on_route(self, pkt: Packet) -> None:
        now = self.sim.now
        for addr, hop_count in _unpack_route_entries(pkt.payload):
            if addr == self.address:
                continue  # a route back to myself — discard (basic loop suppression)
            candidate_hops = hop_count + 1
            if candidate_hops >= MAX_ROUTE_HOPS:
                continue
            existing = self.routing_table.get(addr)
            if existing is None or candidate_hops <= existing.hop_count or existing.next_hop == pkt.src:
                if existing is None:
                    self.sim.log(f"{self.address}: learned route to {addr} via {pkt.src} ({candidate_hops} hop(s))")
                elif candidate_hops != existing.hop_count or existing.next_hop != pkt.src:
                    self.sim.log(
                        f"{self.address}: updated route to {addr}: "
                        f"{existing.hop_count} hop(s) via {existing.next_hop} -> {candidate_hops} hop(s) via {pkt.src}"
                    )
                self.routing_table[addr] = RouteEntry(hop_count=candidate_hops, next_hop=pkt.src, last_seen=now)

    # ------------------------------------------------------------------ #
    # Physical channel events
    # ------------------------------------------------------------------ #

    def line_damaged(self) -> None:
        if not self.line_intact:
            return
        self.line_intact = False
        self.sim.log(f"{self.address}: PLC line damaged, falling back to WiFi mesh")

    def line_restored(self) -> None:
        if self.line_intact:
            return
        self.line_intact = True
        self.sim.log(f"{self.address}: PLC line restored")

    # ------------------------------------------------------------------ #
    # Inverter master protocol (docs/inverter-master.md)
    # ------------------------------------------------------------------ #

    def grid_lost(self) -> None:
        """Call when this device itself just watched its own grid power fail.
        Since the device was GRID_ON up to this instant, no master can
        already exist on the segment — a short listen is safe. A segment-wide
        outage means every device calls this at roughly the same moment, so
        the delay is jittered (LISTEN_JITTER) to avoid every device timing
        out at the identical instant and all claiming mastership together —
        see docs/inverter-master.md REV 0.5 for why REV 0.4's flat 2s delay
        made split-brain the common case instead of a rare fallback."""
        if not self.grid_on:
            return
        self.grid_on = False
        self._inv_epoch += 1
        epoch = self._inv_epoch
        self.inverter_state = InverterState.LISTEN
        delay = LISTEN_DELAY + self._rng.uniform(0, LISTEN_JITTER)
        self.sim.log(f"{self.address}: grid power lost, listening for existing master ({delay:.3f}s)")
        self.sim.schedule(delay, lambda: self._on_initial_listen_timeout(epoch))

    def cold_join(self) -> None:
        """Call when this device is powering on (or rebooting) while the grid
        is already off — unlike grid_lost(), it has no idea how long the
        outage has been running or whether a master is already active, so it
        cannot safely use the short listen delay: REV 0.4's flat 2s window
        was far shorter than the 10s MASTER_ALIVE interval, giving a joining
        device only a ~20% chance of actually hearing an existing master
        before timing out and (if its address happened to be lower) forcing
        a stable master to step down. JOIN_LISTEN_DELAY instead covers a full
        heartbeat cycle plus margin, so an existing master is reliably heard."""
        if not self.grid_on:
            return
        self.grid_on = False
        self._inv_epoch += 1
        epoch = self._inv_epoch
        self.inverter_state = InverterState.LISTEN
        delay = JOIN_LISTEN_DELAY + self._rng.uniform(0, LISTEN_JITTER)
        self.sim.log(f"{self.address}: joining during an outage, listening for a full heartbeat cycle ({delay:.3f}s)")
        self.sim.schedule(delay, lambda: self._on_initial_listen_timeout(epoch))

    def grid_restored(self) -> None:
        if self.grid_on:
            return
        if self.inverter_state == InverterState.INV_MASTER:
            self._send_control(BROADCAST, MessageType.MASTER_RESIGN, struct.pack("B", ResignReason.GRID_RETURNING))
            self.sim.log(f"{self.address}: grid restored, resigning as master")
        self._inv_epoch += 1
        self.grid_on = True
        self.inverter_state = InverterState.GRID_ON
        self.master_addr = None
        self.sim.log(f"{self.address}: grid power restored")

    def _on_initial_listen_timeout(self, epoch: int) -> None:
        if epoch != self._inv_epoch or self.inverter_state != InverterState.LISTEN:
            return
        self._become_master()

    def _become_master(self) -> None:
        self._inv_epoch += 1
        epoch = self._inv_epoch
        self.inverter_state = InverterState.INV_MASTER
        self.master_addr = self.address
        self.sim.log(f"{self.address}: becoming INV_MASTER (injecting 24V AC)")
        self._broadcast_master_alive(epoch)

    def _broadcast_master_alive(self, epoch: int) -> None:
        if epoch != self._inv_epoch or self.inverter_state != InverterState.INV_MASTER:
            return
        self._send_control(BROADCAST, MessageType.MASTER_ALIVE, struct.pack("BB", 24, self.battery_pct))
        self.sim.schedule(MASTER_ALIVE_INTERVAL, lambda: self._broadcast_master_alive(epoch))

    def _active_candidates(self) -> List[Address]:
        now = self.sim.now
        active = {addr for addr, last_seen in self.known_nodes.items() if now - last_seen <= KNOWN_NODE_STALE}
        active.add(self.address)
        return sorted(active)

    def _trigger_failover(self, reason: str) -> None:
        self._inv_epoch += 1
        epoch = self._inv_epoch
        self.inverter_state = InverterState.LISTEN
        self.sim.log(f"{self.address}: {reason} — starting master re-election")
        self._select_new_master(epoch, 0)

    def _select_new_master(self, epoch: int, candidate_index: int) -> None:
        if epoch != self._inv_epoch or self.inverter_state != InverterState.LISTEN:
            return  # already resolved (heard a MASTER_ALIVE in the meantime)
        candidates = self._active_candidates()
        if candidate_index >= len(candidates):
            self.sim.schedule(FAILOVER_GRACE_PERIOD, lambda: self._select_new_master(epoch, 0))
            return
        candidate = candidates[candidate_index]
        if candidate == self.address:
            self._become_master()
            return
        self.sim.log(f"{self.address}: waiting {FAILOVER_GRACE_PERIOD}s for {candidate} to assert as master")
        self.sim.schedule(FAILOVER_GRACE_PERIOD, lambda: self._select_new_master(epoch, candidate_index + 1))

    def _on_master_alive(self, pkt: Packet) -> None:
        sender = pkt.src
        now = self.sim.now

        if self.inverter_state == InverterState.LISTEN:
            self._inv_epoch += 1
            epoch = self._inv_epoch
            self.inverter_state = InverterState.INV_SLAVE
            self.master_addr = sender
            self.last_master_alive_heard = now
            self.sim.log(f"{self.address}: heard MASTER_ALIVE from {sender}, becoming INV_SLAVE")
            self.sim.schedule(MASTER_TIMEOUT, lambda: self._check_master_timeout(epoch))

        elif self.inverter_state == InverterState.INV_SLAVE:
            if sender == self.master_addr or sender < self.master_addr:
                if sender < self.master_addr:
                    self.sim.log(f"{self.address}: lower-address master {sender} detected, switching")
                self._inv_epoch += 1
                epoch = self._inv_epoch
                self.master_addr = sender
                self.last_master_alive_heard = now
                self.sim.schedule(MASTER_TIMEOUT, lambda: self._check_master_timeout(epoch))
            # else: higher-address impostor heartbeat — ignore

        elif self.inverter_state == InverterState.INV_MASTER:
            if sender != self.address:
                self._on_split_brain(sender)

    def _check_master_timeout(self, epoch: int) -> None:
        # No separate `now - last_heard >= MASTER_TIMEOUT` check here: this
        # callback is only ever scheduled for exactly `last_heard + MASTER_TIMEOUT`,
        # and any newer heartbeat bumps _inv_epoch (see _on_master_alive) and
        # reschedules a fresh check — so a matching epoch already guarantees
        # the timeout genuinely elapsed. Recomputing the time difference here
        # was redundant and, due to float rounding, could land a hair under
        # MASTER_TIMEOUT (e.g. 29.999999999999996), silently skipping failover
        # forever since nothing else ever re-checks it.
        if epoch != self._inv_epoch or self.inverter_state != InverterState.INV_SLAVE:
            return
        self.sim.log(f"{self.address}: master {self.master_addr} silent for {MASTER_TIMEOUT:.0f}s")
        self._trigger_failover("master timeout")

    def _on_split_brain(self, other_addr: Address) -> None:
        if self.address < other_addr:
            self.sim.log(f"{self.address}: split-brain with {other_addr} — I win (lower address), reasserting")
            self._send_control(BROADCAST, MessageType.MASTER_ALIVE, struct.pack("BB", 24, self.battery_pct))
        else:
            self.sim.log(f"{self.address}: split-brain with {other_addr} — stepping down (higher address)")
            self._inv_epoch += 1
            epoch = self._inv_epoch
            self.inverter_state = InverterState.INV_SLAVE
            self.master_addr = other_addr
            self.last_master_alive_heard = self.sim.now
            self.sim.schedule(MASTER_TIMEOUT, lambda: self._check_master_timeout(epoch))

    def _on_master_resign(self, pkt: Packet) -> None:
        if self.inverter_state == InverterState.INV_SLAVE and pkt.src == self.master_addr:
            self._trigger_failover(f"master {pkt.src} resigned")
