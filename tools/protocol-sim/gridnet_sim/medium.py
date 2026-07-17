"""Shared broadcast medium — models one PLC segment or the WiFi mesh.

Each Medium is a collision domain: overlapping transmissions from different
members corrupt each other, exactly what CSMA/CA (carrier sense, random
backoff before transmitting) exists to avoid. This is a simplified model
(slotted backoff, no capture effect) — good enough to exercise the flooding
and store-and-forward logic in docs/protocol.md, not a PHY-accurate model of
CENELEC OFDM/FSK.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

PROPAGATION_DELAY = 0.002  # seconds — arbitrary small constant, not modeled per-segment
BACKOFF_SLOT = 0.005  # seconds
MAX_BACKOFF_SLOTS = 8


@dataclass
class _Transmission:
    start: float
    end: float
    node_id: str
    collided: bool = False


class Medium:
    """A single shared channel. `bitrate_bps` sets how long a frame occupies the
    channel (airtime = frame_bytes * 8 / bitrate_bps)."""

    def __init__(
        self,
        name: str,
        bitrate_bps: float,
        loss_probability: float = 0.0,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.name = name
        self.bitrate_bps = bitrate_bps
        self.loss_probability = loss_probability
        self.rng = rng or random.Random()
        self.members: Dict[str, Callable[[bytes], None]] = {}
        self._transmissions: List[_Transmission] = []

    def attach(self, node_id: str, on_receive: Callable[[bytes], None]) -> None:
        self.members[node_id] = on_receive

    def detach(self, node_id: str) -> None:
        self.members.pop(node_id, None)

    def is_busy(self, now: float) -> bool:
        return any(t.start <= now < t.end for t in self._transmissions)

    def airtime(self, frame: bytes) -> float:
        return (len(frame) * 8) / self.bitrate_bps

    def transmit(self, sim, node_id: str, frame: bytes) -> None:
        """CSMA/CA: sense the channel; if busy, back off a random number of slots
        and retry. When clear, start transmitting (which may still collide with
        something that started in the same instant)."""
        if node_id not in self.members:
            return
        if self.is_busy(sim.now):
            backoff = self.rng.randint(1, MAX_BACKOFF_SLOTS) * BACKOFF_SLOT
            sim.schedule(backoff, lambda: self.transmit(sim, node_id, frame))
            return

        duration = self.airtime(frame)
        start, end = sim.now, sim.now + duration
        tx = _Transmission(start=start, end=end, node_id=node_id)

        for other in self._transmissions:
            if other.end > start and other.start < end:
                other.collided = True
                tx.collided = True
        self._transmissions.append(tx)

        def deliver() -> None:
            self._transmissions.remove(tx)
            if tx.collided:
                sim.log(f"{self.name}: collision destroyed frame from {node_id}")
                return
            for member_id, callback in list(self.members.items()):
                if member_id == node_id:
                    continue
                if self.rng.random() < self.loss_probability:
                    continue
                callback(frame)

        sim.schedule(duration + PROPAGATION_DELAY, deliver)
