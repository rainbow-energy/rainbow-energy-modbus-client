"""Load generic Modbus device profiles from YAML files."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


_DATA_TYPE_COUNTS: dict[str, int | None] = {
    "uint16": 1,
    "int16": 1,
    "uint32": 2,
    "int32": 2,
    "float32": 2,
    "string": None,
}
_NON_EMPTY_STRING_SCHEMA = {"type": "string", "pattern": r"\S"}
_REGISTER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "key",
        "name",
        "address",
        "function",
        "data_type",
        "scale",
        "unit",
        "access",
    ],
    "properties": {
        "key": _NON_EMPTY_STRING_SCHEMA,
        "name": _NON_EMPTY_STRING_SCHEMA,
        "function": {
            "type": "string",
            "enum": ["holding", "input"],
        },
        "scale": {
            "type": "number",
            "not": {"const": 0},
        },
        "unit": {
            "type": "string",
            "anyOf": [
                {"const": ""},
                {"pattern": r"\S"},
            ],
        },
        "access": {
            "type": "string",
            "enum": ["read", "write"],
        },
        "word_order": {},
        "address": {
            "type": "integer",
            "minimum": 0,
            "maximum": 65535,
        },
        "data_type": {
            "type": "string",
            "enum": list(_DATA_TYPE_COUNTS),
        },
        "count": {
            "type": "integer",
            "minimum": 1,
            "maximum": 125,
        },
        "bitmask": {
            "type": "integer",
            "minimum": 1,
            "maximum": 65535,
        },
    },
    "allOf": [
        {
            "if": {
                "properties": {"data_type": {"const": data_type}},
                "required": ["data_type"],
            },
            "then": {
                "properties": {
                    "count": {"const": required_count},
                    **(
                        {
                            "word_order": {
                                "type": "string",
                                "enum": ["big", "little"],
                            }
                        }
                        if required_count == 2
                        else {}
                    ),
                },
                **(
                    {"required": ["count", "word_order"]}
                    if required_count == 2
                    else {}
                ),
            },
        }
        for data_type, required_count in _DATA_TYPE_COUNTS.items()
        if required_count is not None
    ]
    + [
        {
            "if": {
                "properties": {"data_type": {"const": "string"}},
                "required": ["data_type"],
            },
            "then": {
                "required": ["count"],
                "properties": {
                    "count": {"type": "integer", "minimum": 1, "maximum": 125},
                    "scale": {"const": 1},
                },
                "not": {"required": ["bitmask"]},
            },
        }
    ],
}
_PROFILE_VALIDATOR = Draft202012Validator(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["manufacturer", "model", "registers"],
        "properties": {
            "manufacturer": _NON_EMPTY_STRING_SCHEMA,
            "model": _NON_EMPTY_STRING_SCHEMA,
            "registers": {
                "type": "array",
                "items": _REGISTER_SCHEMA,
            },
        },
    }
)


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
    word_order: str | None = None
    bitmask: int | None = None


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """Describe a device model and its available Modbus registers."""

    manufacturer: str
    model: str
    registers: tuple[RegisterDefinition, ...]


def _schema_error(scope: str, error: ValidationError) -> ProfileError:
    """Add profile context to a JSON Schema validation error."""
    path = [str(part) for part in error.path]
    location = f" {'.'.join(path)}" if path else ""
    return ProfileError(f"{scope}{location}: {error.message}")


def _validate_register_range(index: int, register_data: Mapping) -> None:
    """Validate a register range that JSON Schema cannot express."""
    address = cast(int, register_data["address"])
    count = cast(int, register_data.get("count", 1))
    if address + count - 1 > 65535:
        raise ProfileError(f"register {index} range exceeds address 65535")


def _load_register(index: int, register_data: Mapping) -> RegisterDefinition:
    """Load and validate one register definition."""
    _validate_register_range(index, register_data)
    return RegisterDefinition(**register_data)


def _load_registers(registers_data: list[Mapping]) -> tuple[RegisterDefinition, ...]:
    """Load all register definitions in profile order."""
    registers = tuple(
        _load_register(index, register_data)
        for index, register_data in enumerate(registers_data)
    )
    seen_keys: set[str] = set()
    occupied: dict[tuple[str, int], list[tuple[str, int | None]]] = {}
    for register in registers:
        if register.key in seen_keys:
            raise ProfileError(f"duplicate register key: {register.key}")
        seen_keys.add(register.key)
        for offset in range(register.count):
            address = register.address + offset
            space = (register.function, address)
            claims = occupied.setdefault(space, [])
            for existing_key, existing_mask in claims:
                if (
                    register.bitmask is None
                    or existing_mask is None
                    or register.bitmask & existing_mask
                ):
                    raise ProfileError(
                        "overlapping register addresses: "
                        f"{existing_key} and {register.key}"
                    )
            claims.append((register.key, register.bitmask))
    return registers


def build_device_profile(profile_data: object) -> DeviceProfile:
    """Validate parsed profile data and build a device profile."""
    try:
        _PROFILE_VALIDATOR.validate(profile_data)
    except ValidationError as error:
        raise _schema_error("profile", error) from error
    profile_mapping = cast(Mapping, profile_data)

    return DeviceProfile(
        manufacturer=profile_mapping["manufacturer"],
        model=profile_mapping["model"],
        registers=_load_registers(cast(list[Mapping], profile_mapping["registers"])),
    )


def load_profile(path: str | Path) -> DeviceProfile:
    """Load and parse a YAML file into a device profile."""
    try:
        with Path(path).open(encoding="utf-8") as profile_file:
            profile_data = yaml.safe_load(profile_file)
    except yaml.YAMLError as error:
        raise ProfileError(f"Invalid YAML: {error}") from error

    return build_device_profile(profile_data)
