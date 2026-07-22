"""Command-line interface for Rainbow Energy Client."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from rainbow_energy_client.client import Client, ClientError
from rainbow_energy_client.device import RegisterReader
from rainbow_energy_client.profiles import (
    ProfileError,
    list_packaged_profiles,
    load_packaged_profile,
    load_profile,
)
from rainbow_energy_client.reader import ModbusReader
from rainbow_energy_client.support import run_check_profile


def _load_profile_ref(profile_ref: str):
    """Load a profile from a filesystem path or packaged stem name."""
    path = Path(profile_ref)
    if path.is_file():
        return load_profile(path)
    return load_packaged_profile(profile_ref)


def run_poll(profile_ref: str, keys: Sequence[str], reader: RegisterReader) -> int:
    """Poll once and print measurements as key, value, unit lines."""
    try:
        profile = _load_profile_ref(profile_ref)
    except (OSError, ProfileError) as error:
        print(f"profile error: {error}", file=sys.stderr)
        return 2

    try:
        client = Client(reader, profile, keys=keys)
        measurements = client.poll()
    except (ClientError, ValueError) as error:
        print(f"poll error: {error}", file=sys.stderr)
        return 1

    for measurement in measurements:
        print(f"{measurement.key}\t{measurement.value}\t{measurement.unit}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser and subcommands."""
    parser = argparse.ArgumentParser(prog="rainbow-energy-client")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-profiles", help="List packaged device profile names")
    check_profile = subparsers.add_parser(
        "check-profile",
        help="Validate a profile path or packaged profile name",
    )
    check_profile.add_argument(
        "profile",
        help="Path to a profile YAML file, or a packaged profile stem name",
    )
    poll = subparsers.add_parser(
        "poll",
        help="Read named measurements once over Modbus serial or TCP",
    )
    poll.add_argument(
        "--profile",
        required=True,
        help="Path to a profile YAML file, or a packaged profile stem name",
    )
    poll.add_argument(
        "--key",
        action="append",
        dest="keys",
        required=True,
        help="Measurement key to poll (repeat for multiple keys)",
    )
    transport = poll.add_mutually_exclusive_group(required=True)
    transport.add_argument(
        "--serial",
        metavar="PORT",
        help="Serial device path for Modbus RTU (for example /dev/ttyUSB0)",
    )
    transport.add_argument(
        "--tcp",
        metavar="HOST",
        help="Modbus TCP host name or address",
    )
    poll.add_argument(
        "--tcp-port",
        type=int,
        default=502,
        help="Modbus TCP port (default: 502)",
    )
    poll.add_argument(
        "--device-id",
        type=int,
        default=1,
        help="Modbus device / unit id (default: 1)",
    )
    return parser


def _open_reader(args: argparse.Namespace) -> ModbusReader:
    """Build a Modbus reader from poll transport arguments."""
    if args.serial is not None:
        return ModbusReader.serial(port=args.serial, device_id=args.device_id)
    return ModbusReader.tcp(host=args.tcp, port=args.tcp_port, device_id=args.device_id)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    if not argv:
        parser.print_usage(sys.stderr)
        return 2
    args = parser.parse_args(argv)
    if args.command == "list-profiles":
        for name in list_packaged_profiles():
            print(name)
        return 0
    if args.command == "check-profile":
        return run_check_profile(args.profile)
    with _open_reader(args) as reader:
        return run_poll(args.profile, args.keys, reader)
