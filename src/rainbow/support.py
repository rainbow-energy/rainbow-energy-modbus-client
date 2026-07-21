"""Report profile features that Rainbow cannot handle yet."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from rainbow.decode import decode_register
from rainbow.profiles import DeviceProfile, ProfileError, RegisterDefinition, load_profile

SUPPORTED_FUNCTIONS = frozenset({"holding", "input"})
SUPPORTED_DATA_TYPES = frozenset({"uint16", "int16", "uint32", "int32", "float32", "string"})


@dataclass(frozen=True, slots=True)
class UnsupportedFeature:
    """Describe one unsupported register feature in a profile."""

    key: str
    reason: str


def _probe_values(register: RegisterDefinition) -> tuple[int, ...]:
    """Build synthetic register words that the decoder can accept."""
    if register.options:
        probe = next(iter(register.options))
        return (probe,) + (0,) * (register.count - 1)
    return (0,) * register.count


def check_profile_support(profile: DeviceProfile) -> tuple[UnsupportedFeature, ...]:
    """Return unsupported features found in a loaded device profile."""
    issues: list[UnsupportedFeature] = []
    for register in profile.registers:
        if register.function not in SUPPORTED_FUNCTIONS:
            issues.append(
                UnsupportedFeature(
                    key=register.key,
                    reason=f"unsupported function: {register.function}",
                )
            )
            continue
        if register.data_type not in SUPPORTED_DATA_TYPES:
            issues.append(
                UnsupportedFeature(
                    key=register.key,
                    reason=f"unsupported data_type: {register.data_type}",
                )
            )
            continue
        try:
            decode_register(register, _probe_values(register))
        except Exception as error:  # noqa: BLE001 - report any decode failure
            issues.append(
                UnsupportedFeature(
                    key=register.key,
                    reason=f"decode failed: {error}",
                )
            )
    return tuple(issues)


def main(argv: list[str] | None = None) -> int:
    """Load a profile path and print unsupported features."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate a device profile and list features Rainbow cannot "
            "handle yet (data types, functions, decode failures)."
        )
    )
    parser.add_argument(
        "profile",
        type=Path,
        help="Path to a profile YAML file",
    )
    args = parser.parse_args(argv)

    try:
        profile = load_profile(args.profile)
    except (OSError, ProfileError) as error:
        print(f"profile error: {error}", file=sys.stderr)
        return 2

    issues = check_profile_support(profile)
    if not issues:
        print(f"{args.profile}: all {len(profile.registers)} registers are supported")
        return 0

    print(
        f"{args.profile}: {len(issues)} unsupported "
        f"feature{'s' if len(issues) != 1 else ''}",
        file=sys.stderr,
    )
    for issue in issues:
        print(f"  {issue.key}: {issue.reason}", file=sys.stderr)
    return 1
