"""Encode engineering values into raw Modbus register words."""

from rainbow_energy_modbus_client.profiles import RegisterDefinition
from rainbow_energy_modbus_client.validate import (
    ValidationError,
    validate_binary_value,
    validate_datetime_value,
    validate_int16_raw,
    validate_numeric_bounds,
    validate_numeric_value,
    validate_options_value,
    validate_time_value,
    validate_uint16_raw,
)

_BITS_PER_BYTE = 8
_UINT16_RANGE = 0x10000
_HHMM_FACTOR = 100
_DATETIME_YEAR_BASE = 2000


class EncodeError(ValueError):
    """Raised when an engineering value cannot be encoded."""


def _round_raw(value: float) -> int:
    """Round a scaled raw value to the nearest integer register word."""
    return int(round(value))


def _encode_scaled_uint16(definition: RegisterDefinition, value: float | int) -> int:
    """Invert scale/offset into one unsigned 16-bit register word."""
    assert definition.scale is not None
    raw_float = float(value)
    if definition.offset is not None:
        raw_float += definition.offset
    raw_float /= definition.scale
    raw = _round_raw(raw_float)
    try:
        validate_uint16_raw(definition, raw)
    except ValidationError as error:
        raise EncodeError(str(error)) from error
    return raw


def _encode_scaled_int16(definition: RegisterDefinition, value: float | int) -> int:
    """Invert scale/offset into one signed 16-bit register word."""
    assert definition.scale is not None
    raw_float = float(value)
    if definition.offset is not None:
        raw_float += definition.offset
    raw_float /= definition.scale
    raw = _round_raw(raw_float)
    try:
        validate_int16_raw(definition, raw)
    except ValidationError as error:
        raise EncodeError(str(error)) from error
    if raw < 0:
        return raw + _UINT16_RANGE
    return raw


def _encode_options(definition: RegisterDefinition, value: object) -> int:
    """Map an options label or raw integer to a register word."""
    try:
        return validate_options_value(definition, value)
    except ValidationError as error:
        raise EncodeError(str(error)) from error


def _encode_binary(definition: RegisterDefinition, value: object) -> int:
    """Map a boolean to a non-zero or zero masked contribution."""
    try:
        flag = validate_binary_value(definition, value)
    except ValidationError as error:
        raise EncodeError(str(error)) from error
    if definition.bitmask is not None:
        return definition.bitmask if flag else 0
    return 1 if flag else 0


def _encode_time(definition: RegisterDefinition, value: object) -> int:
    """Encode an H:MM or HH:MM clock string as HHMM-packed minutes."""
    try:
        hours, minutes = validate_time_value(definition, value)
    except ValidationError as error:
        raise EncodeError(str(error)) from error
    return hours * _HHMM_FACTOR + minutes


def _encode_datetime(definition: RegisterDefinition, value: object) -> tuple[int, int, int]:
    """Encode an ISO-like datetime string into three SunSynk register words."""
    try:
        year, month, day, hour, minute, second = validate_datetime_value(
            definition, value
        )
    except ValidationError as error:
        raise EncodeError(str(error)) from error
    year_offset = year - _DATETIME_YEAR_BASE
    return (
        (year_offset << _BITS_PER_BYTE) | month,
        (day << _BITS_PER_BYTE) | hour,
        (minute << _BITS_PER_BYTE) | second,
    )


def _enforce_numeric_bounds(
    definition: RegisterDefinition, value: float | int
) -> None:
    """Reject engineering values outside optional profile min/max/step."""
    try:
        validate_numeric_bounds(definition, value)
    except ValidationError as error:
        raise EncodeError(str(error)) from error


def encode_register(
    definition: RegisterDefinition,
    value: float | int | str | bool,
) -> tuple[int, ...]:
    """Encode one engineering value into raw register words."""
    if definition.data_type == "math":
        raise EncodeError(
            f"math register {definition.key} cannot be encoded to raw words"
        )
    if definition.binary:
        return (_encode_binary(definition, value),)
    if definition.options is not None:
        return (_encode_options(definition, value),)
    match definition.data_type:
        case "uint16":
            try:
                numeric = validate_numeric_value(
                    definition, value, data_type="uint16"
                )
            except ValidationError as error:
                raise EncodeError(str(error)) from error
            _enforce_numeric_bounds(definition, numeric)
            return (_encode_scaled_uint16(definition, numeric),)
        case "int16":
            try:
                numeric = validate_numeric_value(
                    definition, value, data_type="int16"
                )
            except ValidationError as error:
                raise EncodeError(str(error)) from error
            _enforce_numeric_bounds(definition, numeric)
            return (_encode_scaled_int16(definition, numeric),)
        case "time":
            return (_encode_time(definition, value),)
        case "datetime":
            return _encode_datetime(definition, value)
        case _:
            raise EncodeError(f"unsupported data_type: {definition.data_type}")
