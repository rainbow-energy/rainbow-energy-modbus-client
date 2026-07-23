"""Encode engineering values into raw Modbus register words."""

from rainbow_energy_client.profiles import RegisterDefinition

_BITS_PER_BYTE = 8
_BYTE_MASK = 0xFF
_UINT16_MAX = 0xFFFF
_INT16_MIN = -0x8000
_INT16_MAX = 0x7FFF
_UINT16_RANGE = 0x10000
_HHMM_FACTOR = 100
_MINUTES_PER_HOUR = 60
_HOURS_PER_DAY = 24
_DATETIME_YEAR_BASE = 2000
_MIN_MONTH = 1
_MAX_MONTH = 12
_MIN_DAY = 1
_MAX_DAY = 31
_MAX_HOUR = 23
_MAX_MINUTE = 59
_MAX_SECOND = 59


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
    if not 0 <= raw <= _UINT16_MAX:
        raise EncodeError(
            f"encoded value out of uint16 range for {definition.key}: {raw}"
        )
    return raw


def _encode_scaled_int16(definition: RegisterDefinition, value: float | int) -> int:
    """Invert scale/offset into one signed 16-bit register word."""
    assert definition.scale is not None
    raw_float = float(value)
    if definition.offset is not None:
        raw_float += definition.offset
    raw_float /= definition.scale
    raw = _round_raw(raw_float)
    if not _INT16_MIN <= raw <= _INT16_MAX:
        raise EncodeError(
            f"encoded value out of int16 range for {definition.key}: {raw}"
        )
    if raw < 0:
        return raw + _UINT16_RANGE
    return raw


def _encode_options(definition: RegisterDefinition, value: object) -> int:
    """Map an options label or raw integer to a register word."""
    assert definition.options is not None
    if isinstance(value, bool) or not isinstance(value, int):
        if not isinstance(value, str):
            raise EncodeError(
                f"options require a label or integer for {definition.key}"
            )
        for raw, label in definition.options.items():
            if label == value:
                return raw
        raise EncodeError(f"unknown option {value!r} for {definition.key}")
    if value not in definition.options:
        raise EncodeError(f"unknown option {value} for {definition.key}")
    return value


def _encode_binary(definition: RegisterDefinition, value: object) -> int:
    """Map a boolean to a non-zero or zero masked contribution."""
    if not isinstance(value, bool):
        raise EncodeError(f"binary requires a bool for {definition.key}")
    if definition.bitmask is not None:
        return definition.bitmask if value else 0
    return 1 if value else 0


def _encode_time(definition: RegisterDefinition, value: object) -> int:
    """Encode an H:MM or HH:MM clock string as HHMM-packed minutes."""
    if not isinstance(value, str):
        raise EncodeError(f"time requires a string for {definition.key}")
    try:
        hour_text, minute_text = value.split(":", 1)
        hours = int(hour_text)
        minutes = int(minute_text)
    except ValueError as error:
        raise EncodeError(f"invalid time for {definition.key}: {value!r}") from error
    if not (0 <= hours < _HOURS_PER_DAY and 0 <= minutes < _MINUTES_PER_HOUR):
        raise EncodeError(f"invalid time for {definition.key}: {value!r}")
    return hours * _HHMM_FACTOR + minutes


def _encode_datetime(definition: RegisterDefinition, value: object) -> tuple[int, int, int]:
    """Encode an ISO-like datetime string into three SunSynk register words."""
    if not isinstance(value, str):
        raise EncodeError(f"datetime requires a string for {definition.key}")
    try:
        date_text, time_text = value.split(" ", 1)
        year_text, month_text, day_text = date_text.split("-", 2)
        hour_text, minute_text, second_text = time_text.split(":", 2)
        year = int(year_text)
        month = int(month_text)
        day = int(day_text)
        hour = int(hour_text)
        minute = int(minute_text)
        second = int(second_text)
    except ValueError as error:
        raise EncodeError(
            f"invalid datetime for {definition.key}: {value!r}"
        ) from error
    if not (
        year >= _DATETIME_YEAR_BASE
        and _MIN_MONTH <= month <= _MAX_MONTH
        and _MIN_DAY <= day <= _MAX_DAY
        and 0 <= hour <= _MAX_HOUR
        and 0 <= minute <= _MAX_MINUTE
        and 0 <= second <= _MAX_SECOND
    ):
        raise EncodeError(f"invalid datetime for {definition.key}: {value!r}")
    year_offset = year - _DATETIME_YEAR_BASE
    if year_offset > _BYTE_MASK:
        raise EncodeError(f"invalid datetime for {definition.key}: {value!r}")
    return (
        (year_offset << _BITS_PER_BYTE) | month,
        (day << _BITS_PER_BYTE) | hour,
        (minute << _BITS_PER_BYTE) | second,
    )


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
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EncodeError(
                    f"uint16 requires a numeric value for {definition.key}"
                )
            return (_encode_scaled_uint16(definition, value),)
        case "int16":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EncodeError(
                    f"int16 requires a numeric value for {definition.key}"
                )
            return (_encode_scaled_int16(definition, value),)
        case "time":
            return (_encode_time(definition, value),)
        case "datetime":
            return _encode_datetime(definition, value)
        case _:
            raise EncodeError(f"unsupported data_type: {definition.data_type}")
