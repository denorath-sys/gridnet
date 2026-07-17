#!/usr/bin/env python3
"""Run a small Forth program through the VM and print its output.

Usage:
    python3 run_demo.py <example>
    python3 run_demo.py --list
    python3 run_demo.py --repl
"""

import argparse
import sys

from forth_vm.vm import ForthError, ForthVM

EXAMPLES = {
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
    "corner-shop": (
        # The ~15-line market order system from the README, adapted to what
        # this core VM currently supports (no real screen/keyboard yet — see
        # docs/firmware-arch.md's Forth VM section for the eventual I/O words).
        ": HEADER\n"
        "  .\" +---------------+\" CR\n"
        "  .\" |  CORNER SHOP  |\" CR\n"
        "  .\" +---------------+\" CR ;\n"
        ": MENU HEADER .\" 1. Bread  2. Milk\" CR ;\n"
        "MENU"
    ),
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

    vm = ForthVM()
    try:
        vm.run(EXAMPLES[args.example])
    except ForthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(vm.output)
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
