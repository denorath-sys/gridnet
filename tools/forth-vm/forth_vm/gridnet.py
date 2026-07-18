"""GRIDNET-specific words layered on top of the core Forth VM: the 80x25
screen, keyboard input, and SEND-MSG, matching docs/firmware-arch.md's
"Forth VM" section and docs/protocol.md's Forth Application Protocol.

This is where the sandbox rules from those docs are actually enforced:

    Rule            Description                          Enforced by
    Address lock    App cannot change source address      no word sets vm.address at all
    Rate limit      Max 5 packets/second per app           SandboxViolation in _do_send
    Message size    Max 256 bytes per message              SandboxViolation in _do_send
    Broadcast       Requires explicit permission            SandboxViolation in _do_send
    Screen          Limited to 80x25 character area        Screen.write() clips silently

Filesystem isolation isn't implemented here: this prototype has no file
words at all yet, so there's nothing to isolate — adding fake file access
just to sandbox it would test a feature that doesn't otherwise exist.

WAIT advances a virtual clock (vm.now), not a real one — this is a language
prototype validated by tests, not a real-time app host, and a virtual clock
makes the rate-limit window exact and instant to test (no real sleep()).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Union

from .vm import FALSE, TRUE, ForthError, ForthVM

SCREEN_WIDTH = 80
SCREEN_HEIGHT = 25

BROADCAST_ADDR = "FF.FF.FF.FF"  # matches docs/protocol.md's broadcast address
MAX_MESSAGE_SIZE = 256
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 1.0


class SandboxViolation(ForthError):
    """A GRIDNET sandbox rule was violated (rate limit, message size, or an
    unpermitted BROADCAST) — distinct from a plain ForthError so a host can
    tell "the app misbehaved" from "the app has a language bug"."""


@dataclass
class SentMessage:
    src: str
    dst: str
    payload: Union[str, int]
    timestamp: float


class Screen:
    def __init__(self) -> None:
        self._rows: List[List[str]] = self._blank()

    @staticmethod
    def _blank() -> List[List[str]]:
        return [[" "] * SCREEN_WIDTH for _ in range(SCREEN_HEIGHT)]

    def clear(self) -> None:
        self._rows = self._blank()

    def write(self, x: int, y: int, text: str) -> None:
        """Out-of-bounds writes are clipped, not errors — matches "Screen
        Limited to 80x25" being a hard boundary of the physical display, not
        something an app can be punished for touching."""
        if not 0 <= y < SCREEN_HEIGHT:
            return
        row = self._rows[y]
        for i, ch in enumerate(text):
            col = x + i
            if 0 <= col < SCREEN_WIDTH:
                row[col] = ch

    def render(self) -> str:
        return "\n".join("".join(row).rstrip() for row in self._rows)


class GridnetVM(ForthVM):
    def __init__(
        self,
        address: str = "00.00.00.00",
        allow_broadcast: bool = False,
        output=None,
        step_limit=None,
    ) -> None:
        super().__init__(output=output, step_limit=step_limit)
        self.address = address
        self.allow_broadcast = allow_broadcast
        self.now = 0.0
        self.screen = Screen()
        self.outbox: List[SentMessage] = []
        self._keyboard: Deque[int] = deque()
        self._send_times: List[float] = []
        self._register_gridnet_words()

    def feed_keys(self, keys: str) -> None:
        """Host-side API simulating a user typing — queues key codes for
        KEY/KEY? to consume, in order."""
        self._keyboard.extend(ord(ch) for ch in keys)

    def _do_send(self, payload, dst) -> None:
        # A string is the general case (menu text, order details, ...); a
        # bare int is accepted too and treated as a single raw byte — e.g.
        # KEY's result sent directly, matching how real firmware would just
        # ship the keycode byte without round-tripping it through text.
        if isinstance(payload, str):
            size = len(payload.encode("utf-8"))
        elif isinstance(payload, int):
            size = 1
        else:
            raise SandboxViolation(
                f"SEND-MSG payload must be a string or int, got {type(payload).__name__}"
            )
        if size > MAX_MESSAGE_SIZE:
            raise SandboxViolation(f"message is {size} bytes, sandbox max is {MAX_MESSAGE_SIZE}")
        if dst == BROADCAST_ADDR and not self.allow_broadcast:
            raise SandboxViolation("BROADCAST requires explicit permission (allow_broadcast)")

        window_start = self.now - RATE_LIMIT_WINDOW
        self._send_times = [t for t in self._send_times if t > window_start]
        if len(self._send_times) >= RATE_LIMIT_MAX:
            raise SandboxViolation(
                f"rate limit exceeded: max {RATE_LIMIT_MAX} messages per {RATE_LIMIT_WINDOW:.0f}s"
            )
        self._send_times.append(self.now)
        self.outbox.append(SentMessage(src=self.address, dst=dst, payload=payload, timestamp=self.now))

    def _register_gridnet_words(self) -> None:
        def word(name):
            def deco(fn):
                self.dictionary[name] = ("BUILTIN", fn)
                return fn

            return deco

        @word("WRITE")
        def _write(vm: "GridnetVM") -> None:
            s = vm.pop()
            y = vm.pop()
            x = vm.pop()
            if not isinstance(s, str):
                raise ForthError('WRITE expects a string on top of stack (did you mean S" ..."?)')
            vm.screen.write(x, y, s)

        @word("PAGE")
        def _page(vm: "GridnetVM") -> None:
            vm.screen.clear()

        @word("KEY")
        def _key(vm: "GridnetVM") -> None:
            if not vm._keyboard:
                raise ForthError("KEY: no input available")
            vm.push(vm._keyboard.popleft())

        @word("KEY?")
        def _key_q(vm: "GridnetVM") -> None:
            vm.push(TRUE if vm._keyboard else FALSE)

        @word("BROADCAST")
        def _broadcast(vm: "GridnetVM") -> None:
            vm.push(BROADCAST_ADDR)

        @word("WAIT")
        def _wait(vm: "GridnetVM") -> None:
            ms = vm.pop()
            vm.now += ms / 1000.0

        @word("SEND-MSG")
        def _send_msg(vm: "GridnetVM") -> None:
            dst = vm.pop()
            payload = vm.pop()
            vm._do_send(payload, dst)
