#!/usr/bin/env python3
"""Run a small Forth program through the VM and print its output.

Usage:
    python3 run_demo.py <example>
    python3 run_demo.py --list
    python3 run_demo.py --repl
"""

import argparse
import sys

from forth_vm.gridnet import GridnetVM
from forth_vm.vm import ForthError, ForthVM, StepLimitExceeded

CORE_EXAMPLES = {
    "factorial": (
        ": FACT DUP 1 <= IF DROP 1 ELSE DUP 1 - FACT * THEN ;\n"
        ": SHOW-FACTS 10 0 DO I 1 + DUP FACT SWAP . .\" ! = \" . CR LOOP ;\n"
        "SHOW-FACTS"
    ),
    "fizzbuzz": (
        ": FIZZBUZZ 20 1 DO\n"
        "    I 15 MOD 0 = IF .\" FizzBuzz\"\n"
        "    ELSE I 3 MOD 0 = IF .\" Fizz\"\n"
        "    ELSE I 5 MOD 0 = IF .\" Buzz\"\n"
        "    ELSE I . THEN THEN THEN CR\n"
        "LOOP ;\n"
        "FIZZBUZZ"
    ),
    "fibonacci": (
        ": FIB DUP 2 < IF DROP 1 ELSE DUP 1 - FIB SWAP 2 - FIB + THEN ;\n"
        ": SHOW-FIBS 10 0 DO I FIB . 32 EMIT LOOP ;\n"
        "SHOW-FIBS"
    ),
}

# The ~15-line market order system from the top-level README, made to
# actually run: WRITE/KEY?/KEY/SEND-MSG are real GRIDNET words now (see
# forth_vm/gridnet.py), not the illustrative pseudocode the README sketched.
# The one deviation from the README's one-liner (`KEY? SEND-MSG`): KEY? is a
# boolean check in real Forth (and here), so the working equivalent checks
# it, then reads the key, then sends — see docs/inverter-master.md-style
# "Design Notes" framing: this is a documented adaptation, not a bug fix.
CORNER_SHOP_SRC = """
    : HEADER
        0 0 S" +---------------+" WRITE
        0 1 S" |  CORNER SHOP  |" WRITE
        0 2 S" +---------------+" WRITE ;
    : ORDER
        HEADER
        0 4 S" 1. Bread  2. Milk" WRITE
        KEY? IF KEY S" 01.03.07.99" SEND-MSG THEN ;
"""


def _run_core(src: str) -> None:
    vm = ForthVM()
    vm.run(src)
    print(vm.output)


def example_factorial() -> None:
    _run_core(CORE_EXAMPLES["factorial"])


def example_fizzbuzz() -> None:
    _run_core(CORE_EXAMPLES["fizzbuzz"])


def example_fibonacci() -> None:
    _run_core(CORE_EXAMPLES["fibonacci"])


def example_corner_shop() -> None:
    """A single ORDER call, no key pressed yet — draws the menu, sends nothing."""
    vm = GridnetVM(address="01.03.07.11")
    vm.run(CORNER_SHOP_SRC)
    vm.run("ORDER")
    print(vm.screen.render())
    print(f"\n(no key pressed yet — outbox is empty: {vm.outbox})")


def example_corner_shop_loop() -> None:
    """The README's actual MAIN loop — `BEGIN ORDER 1000 WAIT AGAIN` — which
    is genuinely infinite on real hardware (that's the point: a terminal app
    just runs). A demo/test harness needs a way to stop it anyway, which is
    exactly what step_limit is for: bound it, and treat StepLimitExceeded as
    "the demo's over", not a real error."""
    vm = GridnetVM(address="01.03.07.11", step_limit=20_000)
    vm.run(CORNER_SHOP_SRC + ": MAIN BEGIN ORDER 1000 WAIT AGAIN ;")
    vm.feed_keys("12")  # two customers order, on two different loop iterations
    try:
        vm.run("MAIN")
    except StepLimitExceeded:
        pass  # expected — MAIN never exits on its own, same as real firmware
    print(f"simulated {vm.now:.0f}ms of app runtime before the demo harness stopped it\n")
    for msg in vm.outbox:
        print(f"  sent: {msg.src} -> {msg.dst}: {msg.payload!r} @ t={msg.timestamp:.0f}ms")


EXAMPLES = {
    "factorial": example_factorial,
    "fizzbuzz": example_fizzbuzz,
    "fibonacci": example_fibonacci,
    "corner-shop": example_corner_shop,
    "corner-shop-loop": example_corner_shop_loop,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", nargs="?", choices=sorted(EXAMPLES), help="example program to run")
    parser.add_argument("--list", action="store_true", help="list available examples and exit")
    parser.add_argument("--repl", action="store_true", help="interactive read-eval-print loop instead")
    args = parser.parse_args()

    if args.repl:
        return _repl()

    if args.list or not args.example:
        print("Available examples:")
        for name in sorted(EXAMPLES):
            print(f"  {name}")
        return 0 if args.list else 1

    try:
        EXAMPLES[args.example]()
    except ForthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _repl() -> int:
    print("GRIDNET core Forth VM — interactive mode. Ctrl-D to exit.")
    vm = ForthVM()
    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return 0
        try:
            vm.run(line)
        except ForthError as exc:
            print(f"error: {exc}")
            continue
        if vm.output:
            print(vm.output, end="")
            vm.clear_output()
        print(f"  ok  [stack: {vm.stack}]")


if __name__ == "__main__":
    sys.exit(main())
