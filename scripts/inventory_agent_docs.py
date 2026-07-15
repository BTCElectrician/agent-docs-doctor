#!/usr/bin/env python3
"""Compatibility entry point: emit the deterministic inventory."""

from __future__ import annotations

import argparse
import sys

from doctorlib import build_inventory, dump_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        sys.stdout.write(dump_json(build_inventory(args.root), args.pretty))
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
