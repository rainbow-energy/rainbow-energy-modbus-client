"""Command-line interface for Rainbow Energy Modbus Client."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from rainbow_energy_modbus_client.client import Client, ClientError
from rainbow_energy_modbus_client.device import RegisterReader, RegisterTransport, WriteValue
from rainbow_energy_modbus_client.profiles import ProfileError, load_profile
from rainbow_energy_modbus_client.reader import ModbusReader
from rainbow_energy_modbus_client.support import run_check_profile


def run_poll(profile_path: str, keys: Sequence[str], reader: RegisterReader) -> int:
    """Poll once and print measurements as key, value, unit lines."""
    try:
        profile = load_profile(profile_path)
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


def run_write(
    profile_path: str,
    values: Mapping[str, WriteValue],
    transport: RegisterTransport,
) -> int:
    """Write named profile values once and print confirmation lines."""
    try:
        profile = load_profile(profile_path)
    except (OSError, ProfileError) as error:
        print(f"profile error: {error}", file=sys.stderr)
        return 2

    try:
        # Poll keys are unused for write; pass write targets for Client init.
        client = Client(transport, profile, keys=tuple(values))
        client.write(values)
    except (ClientError, ValueError, KeyError) as error:
        print(f"write error: {error}", file=sys.stderr)
        return 1

    for key, value in values.items():
        print(f"wrote\t{key}\t{value}")
    return 0


def _parse_set_value(raw: str) -> WriteValue:
    """Parse a --set value into bool, int, float, or string."""
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_set_argument(raw: str) -> tuple[str, WriteValue]:
    """Parse one KEY=VALUE --set argument."""
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"expected KEY=VALUE, got {raw!r}"
        )
    key, value = raw.split("=", 1)
    if not key:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {raw!r}")
    return key, _parse_set_value(value)


def _add_transport_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared Modbus serial/TCP transport options."""
    transport = parser.add_mutually_exclusive_group(required=True)
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
    parser.add_argument(
        "--tcp-port",
        type=int,
        default=502,
        help="Modbus TCP port (default: 502)",
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=1,
        help="Modbus device / unit id (default: 1)",
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser and subcommands."""
    parser = argparse.ArgumentParser(prog="rainbow-energy-modbus-client")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_profile = subparsers.add_parser(
        "check-profile",
        help="Validate a profile YAML file",
    )
    check_profile.add_argument(
        "profile",
        help="Path to a profile YAML file",
    )
    poll = subparsers.add_parser(
        "poll",
        help="Read named measurements once over Modbus serial or TCP",
    )
    poll.add_argument(
        "--profile",
        required=True,
        help="Path to a profile YAML file",
    )
    poll.add_argument(
        "--key",
        action="append",
        dest="keys",
        required=True,
        help="Measurement key to poll (repeat for multiple keys)",
    )
    _add_transport_arguments(poll)
    write = subparsers.add_parser(
        "write",
        help="Write named measurements once over Modbus serial or TCP",
    )
    write.add_argument(
        "--profile",
        required=True,
        help="Path to a profile YAML file",
    )
    write.add_argument(
        "--set",
        action="append",
        dest="sets",
        required=True,
        type=_parse_set_argument,
        metavar="KEY=VALUE",
        help="Writable key and value (repeat for multiple keys)",
    )
    _add_transport_arguments(write)
    return parser


def _open_reader(args: argparse.Namespace) -> ModbusReader:
    """Build a Modbus reader from transport arguments."""
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
    if args.command == "check-profile":
        return run_check_profile(args.profile)
    with _open_reader(args) as reader:
        if args.command == "write":
            return run_write(args.profile, dict(args.sets), reader)
        return run_poll(args.profile, args.keys, reader)
