#!/usr/bin/env python3
"""CLI entry point for checking device profile support."""

import sys

from rainbow_energy_modbus_client.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["check-profile", *sys.argv[1:]]))
