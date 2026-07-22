"""Command-line interface for Rainbow Energy Client."""

from __future__ import annotations

import argparse
import sys

from rainbow_energy_client.profiles import list_packaged_profiles
from rainbow_energy_client.support import run_check_profile


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
    return parser


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
    return run_check_profile(args.profile)