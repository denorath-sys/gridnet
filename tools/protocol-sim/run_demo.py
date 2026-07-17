#!/usr/bin/env python3
"""Run a GRIDNET protocol simulator demo scenario and print its event log.

Usage:
    python3 run_demo.py <scenario>
    python3 run_demo.py --list
"""

import argparse
import sys

from gridnet_sim.scenarios import SCENARIOS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS), help="scenario to run")
    parser.add_argument("--list", action="store_true", help="list available scenarios and exit")
    args = parser.parse_args()

    if args.list or not args.scenario:
        print("Available scenarios:")
        for name, func in sorted(SCENARIOS.items()):
            doc = (func.__doc__ or "").strip().splitlines()[0]
            print(f"  {name:<20} {doc}")
        return 0 if args.list else 1

    print(f"=== {args.scenario} ===\n")
    SCENARIOS[args.scenario]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
