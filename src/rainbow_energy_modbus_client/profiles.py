"""Load generic Modbus device profiles from YAML files."""

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

_MAX_MODBUS_ADDRESS = 65535
_MAX_BATCH_COUNT = 125
_BITS_PER_REGISTER = 16
_DATA_TYPE_COUNTS: dict[str, int | None] = {
    "uint16": 1,
    "int16": 1,
    "uint32": 2,
    "int32": 2,
    "float32": 2,
    "protocol": 1,
    "time": 1,
    "datetime": 3,
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
_VARIABLE_COUNT = {
    "type": "integer",
    "minimum": 1,
    "maximum": _MAX_BATCH_COUNT,
}


def _forbid(*fields: str) -> dict[str, Any]:
    """Build a JSON Schema clause that rejects the given fields."""
    if len(fields) == 1:
        return {"not": {"required": [fields[0]]}}
    return {
        "not": {
            "anyOf": [{"required": [field]} for field in fields],
        }
    }


def _if_data_type(data_type: str | Mapping[str, Any], then: Mapping[str, Any]) -> dict[str, Any]:
    """Build an if/then rule keyed on data_type."""
    data_type_schema: Mapping[str, Any]
    if isinstance(data_type, str):
        data_type_schema = {"const": data_type}
    else:
        data_type_schema = data_type
    return {
        "if": {
            "properties": {"data_type": data_type_schema},
            "required": ["data_type"],
        },
        "then": dict(then),
    }


def _scale_one(**extra: Any) -> dict[str, Any]:
    """Require scale == 1, optionally merging extra then-clause fields."""
    properties = {"scale": {"const": 1}, **extra.pop("properties", {})}
    return {"properties": properties, **extra}


def _fixed_count_rule(data_type: str, required_count: int) -> dict[str, Any]:
    """Constrain count (and word_order) for fixed-width data types."""
    properties: dict[str, Any] = {"count": {"const": required_count}}
    if required_count == 2:
        properties["word_order"] = {
            "type": "string",
            "enum": ["big", "little"],
        }
        then: dict[str, Any] = {
            "properties": properties,
            "required": ["count", "word_order"],
            **_forbid("bitmask"),
        }
    elif required_count == 1:
        then = {
            "properties": properties,
            **_forbid("word_order"),
        }
    else:
        then = {
            "properties": properties,
            "required": ["count"],
            **_forbid("bitmask", "word_order"),
        }
    return _if_data_type(data_type, then)


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
            "maximum": _MAX_MODBUS_ADDRESS,
        },
        "data_type": {
            "type": "string",
            "enum": list(_DATA_TYPE_COUNTS),
        },
        "count": _VARIABLE_COUNT,
        "bitmask": {
            "type": "integer",
            "minimum": 1,
            "maximum": _MAX_MODBUS_ADDRESS,
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
        *(_fixed_count_rule(data_type, count)
          for data_type, count in _DATA_TYPE_COUNTS.items()
          if count is not None),
        _if_data_type(
            {"not": {"const": "math"}},
            {
                "required": ["address", "function", "scale"],
                **_forbid("sources", "no_negative", "absolute"),
            },
        ),
        _if_data_type(
            "string",
            {
                "required": ["count"],
                **_scale_one(
                    properties={"count": _VARIABLE_COUNT},
                    **_forbid(
                        "bitmask",
                        "word_order",
                        "offset",
                        "options",
                        "binary",
                        "bits",
                    ),
                ),
            },
        ),
        _if_data_type(
            "fault",
            {
                "required": ["count", "bits"],
                **_scale_one(
                    properties={"count": _VARIABLE_COUNT},
                    **_forbid(
                        "bitmask",
                        "word_order",
                        "offset",
                        "options",
                        "binary",
                    ),
                ),
            },
        ),
        *(
            _if_data_type(
                data_type,
                _scale_one(
                    **_forbid("bitmask", "offset", "options", "binary", "bits"),
                ),
            )
            for data_type in ("protocol", "time")
        ),
        _if_data_type(
            "datetime",
            _scale_one(**_forbid("offset", "options", "binary", "bits")),
        ),
        _if_data_type(
            "math",
            {
                "required": ["sources"],
                **_forbid(
                    "address",
                    "function",
                    "scale",
                    "count",
                    "word_order",
                    "bitmask",
                    "offset",
                    "options",
                    "binary",
                    "bits",
                ),
            },
        ),
        {
            "if": {"required": ["options"]},
            "then": _scale_one(**_forbid("offset", "binary", "bits")),
        },
        {
            "if": {"required": ["binary"]},
            "then": _scale_one(**_forbid("offset", "options", "bits")),
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
    if address + count - 1 > _MAX_MODBUS_ADDRESS:
        raise ProfileError(
            f"register {index} range exceeds address {_MAX_MODBUS_ADDRESS}"
        )


def _normalize_options(register_data: dict[str, Any]) -> None:
    """Convert option map keys from YAML strings to integers."""
    if "options" not in register_data:
        return
    register_data["options"] = {
        int(key): value for key, value in register_data["options"].items()
    }


def _normalize_bits(index: int, register_data: dict[str, Any]) -> None:
    """Convert bit labels and reject numbers outside the register width."""
    if "bits" not in register_data:
        return
    bits = {int(key): value for key, value in register_data["bits"].items()}
    count = cast(int, register_data["count"])
    max_bit = count * _BITS_PER_REGISTER
    for bit in bits:
        if bit < 1 or bit > max_bit:
            raise ProfileError(
                f"register {index} bit {bit} out of range 1..{max_bit}"
            )
    register_data["bits"] = bits


def _normalize_sources(register_data: dict[str, Any]) -> None:
    """Convert math source mappings into MathSource values."""
    if "sources" not in register_data:
        return
    register_data["sources"] = tuple(
        MathSource(key=source["key"], factor=source["factor"])
        for source in register_data["sources"]
    )


def _load_register(index: int, register_data: Mapping) -> RegisterDefinition:
    """Load and validate one register definition."""
    _validate_register_range(index, register_data)
    data = dict(register_data)
    _normalize_options(data)
    _normalize_bits(index, data)
    _normalize_sources(data)
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


def _validate_unique_keys(registers: tuple[RegisterDefinition, ...]) -> None:
    """Reject duplicate register keys, ignoring letter case."""
    seen_keys: set[str] = set()
    for register in registers:
        normalized_key = register.key.casefold()
        if normalized_key in seen_keys:
            raise ProfileError(f"duplicate register key: {register.key}")
        seen_keys.add(normalized_key)


def _validate_no_address_overlap(
    registers: tuple[RegisterDefinition, ...],
) -> None:
    """Reject overlapping same-function address claims."""
    occupied: dict[tuple[str, int], list[tuple[str, int | None]]] = {}
    for register in registers:
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


def _validate_registers(registers: tuple[RegisterDefinition, ...]) -> None:
    """Run cross-register checks that need the full profile set."""
    _validate_unique_keys(registers)
    _validate_no_address_overlap(registers)
    _validate_math_sources(registers)


def _load_registers(registers_data: list[Mapping]) -> tuple[RegisterDefinition, ...]:
    """Load all register definitions in profile order."""
    registers = tuple(
        _load_register(index, register_data)
        for index, register_data in enumerate(registers_data)
    )
    _validate_registers(registers)
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


def load_packaged_profile(name: str) -> DeviceProfile:
    """Load a device profile shipped with the package by stem name."""
    resource = files(__package__).joinpath("data", f"{name}.yaml")
    if not resource.is_file():
        raise ProfileError(f"Unknown packaged profile: {name}")
    with as_file(resource) as path:
        return load_profile(path)


def list_packaged_profiles() -> tuple[str, ...]:
    """Return sorted stem names for profiles shipped with the package."""
    data_dir = files(__package__).joinpath("data")
    return tuple(
        sorted(
            path.name.removesuffix(".yaml")
            for path in data_dir.iterdir()
            if path.name.endswith(".yaml")
        )
    )
