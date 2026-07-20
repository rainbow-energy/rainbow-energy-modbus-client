"""Load generic Modbus device profiles from YAML files."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml


_DATA_TYPE_COUNTS: dict[str, int | None] = {
    "uint16": 1,
    "int16": 1,
    "uint32": 2,
    "int32": 2,
    "float32": 2,
    "string": None,
}


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
    count: int = 1


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """Describe a device model and its available Modbus registers."""

    manufacturer: str
    model: str
    registers: tuple[RegisterDefinition, ...]


def _require_register_mapping(index: int, register_data: object) -> Mapping:
    """Return one register entry as a mapping."""
    if not isinstance(register_data, Mapping):
        raise ProfileError(f"register {index} must be a mapping")
    return register_data


def _validate_count(index: int, register_data: Mapping) -> int:
    """Return a valid Modbus register count."""
    count = register_data.get("count", 1)
    if type(count) is not int or not 1 <= count <= 125:
        raise ProfileError(
            f"register {index} count must be an integer between 1 and 125"
        )
    return count


def _validate_address(index: int, register_data: Mapping, count: int) -> None:
    """Validate a register address and its complete range."""
    if "address" not in register_data:
        raise ProfileError(f"register {index} missing required field: address")
    address = register_data.get("address")
    if type(address) is not int or not 0 <= address <= 65535:
        raise ProfileError(
            f"register {index} address must be an integer between 0 and 65535"
        )
    if address + count - 1 > 65535:
        raise ProfileError(f"register {index} range exceeds address 65535")


def _validate_data_type(index: int, register_data: Mapping, count: int) -> None:
    """Validate a data type and its required register count."""
    if "data_type" not in register_data:
        raise ProfileError(f"register {index} missing required field: data_type")
    data_type = register_data.get("data_type")
    if not isinstance(data_type, str):
        raise ProfileError(f"register {index} data_type must be a string")
    if data_type not in _DATA_TYPE_COUNTS:
        raise ProfileError(f"register {index} has unsupported data_type: {data_type}")

    required_count = _DATA_TYPE_COUNTS[data_type]
    if required_count is not None and count != required_count:
        raise ProfileError(
            f"register {index} data_type {data_type} requires count {required_count}"
        )


def _load_register(index: int, register_data: object) -> RegisterDefinition:
    """Load and validate one register definition."""
    register_mapping = _require_register_mapping(index, register_data)
    count = _validate_count(index, register_mapping)
    _validate_address(index, register_mapping, count)
    _validate_data_type(index, register_mapping, count)

    return RegisterDefinition(**register_mapping)


def _load_registers(registers_data: list[object]) -> tuple[RegisterDefinition, ...]:
    """Load all register definitions in profile order."""
    return tuple(
        _load_register(index, register_data)
        for index, register_data in enumerate(registers_data)
    )


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
