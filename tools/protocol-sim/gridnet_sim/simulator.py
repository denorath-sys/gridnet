"""Minimal discrete-event simulator core.

Simulated time is a float in seconds. Because it's event-driven rather than
wall-clock driven, simulating a 7-day store-and-forward expiry costs nothing
extra in real time — the loop just jumps straight to the next scheduled event.
"""

from __future__ import annotations

import heapq
import itertools
from typing import Callable, List, Tuple


class Simulator:
    def __init__(self) -> None:
        self.now: float = 0.0
        self._queue: List[Tuple[float, int, Callable[[], None]]] = []
        self._counter = itertools.count()
        self.log_events = True
        self._log: List[str] = []

    def schedule(self, delay: float, callback: Callable[[], None]) -> None:
        if delay < 0:
            raise ValueError(f"cannot schedule {delay}s in the past")
        self.schedule_at(self.now + delay, callback)

    def schedule_at(self, time: float, callback: Callable[[], None]) -> None:
        heapq.heappush(self._queue, (time, next(self._counter), callback))

    def run(self, until: float) -> None:
        while self._queue and self._queue[0][0] <= until:
            time, _, callback = heapq.heappop(self._queue)
            self.now = time
            callback()
        self.now = until

    def run_until_idle(self, max_time: float = 1e9) -> None:
        while self._queue and self.now <= max_time:
            time, _, callback = heapq.heappop(self._queue)
            self.now = time
            callback()

    def log(self, message: str) -> None:
        line = f"[t={self.now:9.3f}s] {message}"
        self._log.append(line)
        if self.log_events:
            print(line)

    @property
    def history(self) -> List[str]:
        return list(self._log)
