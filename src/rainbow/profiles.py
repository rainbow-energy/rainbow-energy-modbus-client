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
    "protocol": 1,
    "time": 1,
    "string": None,
    "math": None,
    "fault": None,
}
_NON_EMPTY_STRING_SCHEMA = {"type": "string", "pattern": r"\S"}
_SOURCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["key", "factor"],
    "properties": {
        "key": _NON_EMPTY_STRING_SCHEMA,
        "factor": {
            "type": "number",
            "not": {"const": 0},
        },
    },
}
_BITS_SCHEMA = {
    "type": "object",
    "minProperties": 1,
    "additionalProperties": _NON_EMPTY_STRING_SCHEMA,
}
_REGISTER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "key",
        "name",
        "data_type",
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
        "offset": {
            "type": "number",
        },
        "options": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": _NON_EMPTY_STRING_SCHEMA,
        },
        "binary": {
            "type": "boolean",
            "const": True,
        },
        "bits": _BITS_SCHEMA,
        "sources": {
            "type": "array",
            "minItems": 1,
            "items": _SOURCE_SCHEMA,
        },
        "no_negative": {"type": "boolean"},
        "absolute": {"type": "boolean"},
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
                **(
                    {"not": {"required": ["bitmask"]}}
                    if required_count == 2
                    else {"not": {"required": ["word_order"]}}
                ),
            },
        }
        for data_type, required_count in _DATA_TYPE_COUNTS.items()
        if required_count is not None
    ]
    + [
        {
            "if": {
                "properties": {"data_type": {"not": {"const": "math"}}},
                "required": ["data_type"],
            },
            "then": {
                "required": ["address", "function", "scale"],
                "not": {
                    "anyOf": [
                        {"required": ["sources"]},
                        {"required": ["no_negative"]},
                        {"required": ["absolute"]},
                    ]
                },
            },
        },
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
                "not": {
                    "anyOf": [
                        {"required": ["bitmask"]},
                        {"required": ["word_order"]},
                        {"required": ["offset"]},
                        {"required": ["options"]},
                        {"required": ["binary"]},
                        {"required": ["bits"]},
                    ]
                },
            },
        },
        {
            "if": {
                "properties": {"data_type": {"const": "fault"}},
                "required": ["data_type"],
            },
            "then": {
                "required": ["count", "bits"],
                "properties": {
                    "count": {"type": "integer", "minimum": 1, "maximum": 125},
                    "scale": {"const": 1},
                },
                "not": {
                    "anyOf": [
                        {"required": ["bitmask"]},
                        {"required": ["word_order"]},
                        {"required": ["offset"]},
                        {"required": ["options"]},
                        {"required": ["binary"]},
                    ]
                },
            },
        },
        {
            "if": {
                "properties": {"data_type": {"const": "protocol"}},
                "required": ["data_type"],
            },
            "then": {
                "properties": {"scale": {"const": 1}},
                "not": {
                    "anyOf": [
                        {"required": ["bitmask"]},
                        {"required": ["offset"]},
                        {"required": ["options"]},
                        {"required": ["binary"]},
                        {"required": ["bits"]},
                    ]
                },
            },
        },
        {
            "if": {
                "properties": {"data_type": {"const": "time"}},
                "required": ["data_type"],
            },
            "then": {
                "properties": {"scale": {"const": 1}},
                "not": {
                    "anyOf": [
                        {"required": ["bitmask"]},
                        {"required": ["offset"]},
                        {"required": ["options"]},
                        {"required": ["binary"]},
                        {"required": ["bits"]},
                    ]
                },
            },
        },
        {
            "if": {
                "properties": {"data_type": {"const": "math"}},
                "required": ["data_type"],
            },
            "then": {
                "required": ["sources"],
                "not": {
                    "anyOf": [
                        {"required": ["address"]},
                        {"required": ["function"]},
                        {"required": ["scale"]},
                        {"required": ["count"]},
                        {"required": ["word_order"]},
                        {"required": ["bitmask"]},
                        {"required": ["offset"]},
                        {"required": ["options"]},
                        {"required": ["binary"]},
                        {"required": ["bits"]},
                    ]
                },
            },
        },
        {
            "if": {"required": ["options"]},
            "then": {
                "properties": {"scale": {"const": 1}},
                "not": {
                    "anyOf": [
                        {"required": ["offset"]},
                        {"required": ["binary"]},
                        {"required": ["bits"]},
                    ]
                },
            },
        },
        {
            "if": {"required": ["binary"]},
            "then": {
                "properties": {"scale": {"const": 1}},
                "not": {
                    "anyOf": [
                        {"required": ["offset"]},
                        {"required": ["options"]},
                        {"required": ["bits"]},
                    ]
                },
            },
        },
        {
            "if": {"required": ["bits"]},
            "then": {
                "properties": {"data_type": {"const": "fault"}},
            },
        },
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
                "minItems": 1,
                "items": _REGISTER_SCHEMA,
            },
        },
    }
)


class ProfileError(ValueError):
    """Raised when a device profile is invalid."""


@dataclass(frozen=True, slots=True)
class MathSource:
    """One weighted input to a math register."""

    key: str
    factor: float


@dataclass(frozen=True, slots=True)
class RegisterDefinition:
    """Describe how one named value is stored in a Modbus register."""

    key: str
    name: str
    data_type: str
    unit: str
    access: str
    address: int | None = None
    function: str | None = None
    scale: float | None = None
    count: int = 1
    word_order: str | None = None
    bitmask: int | None = None
    offset: float | None = None
    options: dict[int, str] | None = None
    binary: bool = False
    bits: dict[int, str] | None = None
    sources: tuple[MathSource, ...] | None = None
    no_negative: bool = False
    absolute: bool = False


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
    if register_data["data_type"] == "math":
        return
    address = cast(int, register_data["address"])
    count = cast(int, register_data.get("count", 1))
    if address + count - 1 > 65535:
        raise ProfileError(f"register {index} range exceeds address 65535")


def _load_register(index: int, register_data: Mapping) -> RegisterDefinition:
    """Load and validate one register definition."""
    _validate_register_range(index, register_data)
    data = dict(register_data)
    if "options" in data:
        data["options"] = {
            int(key): value for key, value in data["options"].items()
        }
    if "bits" in data:
        bits = {int(key): value for key, value in data["bits"].items()}
        count = cast(int, data["count"])
        max_bit = count * 16
        for bit in bits:
            if bit < 1 or bit > max_bit:
                raise ProfileError(
                    f"register {index} bit {bit} out of range 1..{max_bit}"
                )
        data["bits"] = bits
    if "sources" in data:
        data["sources"] = tuple(
            MathSource(key=source["key"], factor=source["factor"])
            for source in data["sources"]
        )
    return RegisterDefinition(**data)


def _validate_math_sources(registers: tuple[RegisterDefinition, ...]) -> None:
    """Ensure math sources reference existing non-math registers."""
    by_key = {register.key: register for register in registers}
    for register in registers:
        if register.sources is None:
            continue
        for source in register.sources:
            target = by_key.get(source.key)
            if target is None:
                raise ProfileError(
                    f"math register {register.key} references unknown "
                    f"source key: {source.key}"
                )
            if target.data_type == "math":
                raise ProfileError(
                    f"math register {register.key} cannot source math "
                    f"register: {source.key}"
                )


def _load_registers(registers_data: list[Mapping]) -> tuple[RegisterDefinition, ...]:
    """Load all register definitions in profile order."""
    registers = tuple(
        _load_register(index, register_data)
        for index, register_data in enumerate(registers_data)
    )
    seen_keys: set[str] = set()
    occupied: dict[tuple[str, int], list[tuple[str, int | None]]] = {}
    for register in registers:
        normalized_key = register.key.casefold()
        if normalized_key in seen_keys:
            raise ProfileError(f"duplicate register key: {register.key}")
        seen_keys.add(normalized_key)
        if register.data_type == "math":
            continue
        assert register.address is not None
        assert register.function is not None
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
    _validate_math_sources(registers)
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
