"""Load generic Modbus device profiles from YAML files."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml


class ProfileError(ValueError):
    """Raised when a device profile is invalid."""


@dataclass(frozen=True, slots=True)
class RegisterDefinition:
    """Describe how one named value is stored in a Modbus register."""

    key: str
    name: str
    address: int
    function: str
    data_type: str
    scale: float
    unit: str
    access: str


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """Describe a device model and its available Modbus registers."""

    manufacturer: str
    model: str
    registers: tuple[RegisterDefinition, ...]


def _load_registers(registers_data: list[object]) -> tuple[RegisterDefinition, ...]:
    registers = []
    for index, register_data in enumerate(registers_data):
        if not isinstance(register_data, Mapping):
            raise ProfileError(f"register {index} must be a mapping")
        registers.append(RegisterDefinition(**register_data))
    return tuple(registers)


def load_profile(path: str | Path) -> DeviceProfile:
    """Load a device profile from a YAML file."""

    try:
        with Path(path).open(encoding="utf-8") as profile_file:
            profile_data = yaml.safe_load(profile_file)
    except yaml.YAMLError as error:
        raise ProfileError(f"Invalid YAML: {error}") from error

    if not isinstance(profile_data, Mapping):
        raise ProfileError("Profile must be a YAML mapping")
    for field in ("manufacturer", "model", "registers"):
        if field not in profile_data:
            raise ProfileError(f"Missing required field: {field}")
    if not isinstance(profile_data["registers"], list):
        raise ProfileError("registers must be a list")

    return DeviceProfile(
        manufacturer=profile_data["manufacturer"],
        model=profile_data["model"],
        registers=_load_registers(profile_data["registers"]),
    )
