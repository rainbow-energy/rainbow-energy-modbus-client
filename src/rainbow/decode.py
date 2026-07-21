"""Decode raw Modbus register values into typed measurements."""

import math
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rainbow.profiles import RegisterDefinition

_BITS_PER_BYTE = 8
_BITS_PER_REGISTER = 16
_BYTE_MASK = 0xFF
_HIGH_BYTE_MASK = 0xFF00
_INT16_SIGN = 0x8000
_UINT16_RANGE = 0x10000
_INT32_SIGN = 0x8000_0000
_UINT32_RANGE = 0x1_0000_0000
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


class DecodeError(ValueError):
    """Raised when raw register values cannot be decoded."""


@dataclass(frozen=True, slots=True)
class Measurement:
    """A named engineering value decoded from Modbus registers."""

    key: str
    name: str
    value: float | int | str | bool
    unit: str


def _ordered_words(definition: RegisterDefinition, values: Sequence[int]) -> tuple[int, int]:
    """Return a 32-bit register pair in high-word-first order."""
    first, second = values
    if definition.word_order == "little":
        return second, first
    return first, second


def _decode_string(values: Sequence[int]) -> str:
    """Decode ASCII characters packed two per 16-bit register."""
    return "".join(
        chr(word >> _BITS_PER_BYTE) + chr(word & _BYTE_MASK) for word in values
    ).rstrip("\x00")


def _decode_fault(
    definition: RegisterDefinition, values: Sequence[int]
) -> str:
    """Decode set bits across words as comma-separated F-codes."""
    labels = definition.bits or {}
    faults: list[str] = []
    offset = 0
    for word in values:
        for bit in range(_BITS_PER_REGISTER):
            if word & (1 << bit):
                number = bit + offset + 1
                label = labels.get(number, "")
                faults.append(f"F{number:02d} {label}".strip())
        offset += _BITS_PER_REGISTER
    return ", ".join(faults)


def _decode_float32(
    definition: RegisterDefinition, values: Sequence[int]
) -> float:
    """Decode a 32-bit IEEE float from two register words."""
    high, low = _ordered_words(definition, values)
    value = struct.unpack(">f", struct.pack(">HH", high, low))[0]
    if not math.isfinite(value):
        raise DecodeError(
            f"non-finite float32 value for {definition.key}: {value}"
        )
    return value


def _decode_int32(
    definition: RegisterDefinition, values: Sequence[int]
) -> int:
    """Decode a signed or unsigned 32-bit integer from two words."""
    high, low = _ordered_words(definition, values)
    raw = (high << _BITS_PER_REGISTER) | low
    if definition.data_type == "int32" and raw >= _INT32_SIGN:
        return raw - _UINT32_RANGE
    return raw


def _decode_int16(values: Sequence[int]) -> int:
    """Decode a signed 16-bit integer from one register word."""
    raw = values[0]
    if raw >= _INT16_SIGN:
        return raw - _UINT16_RANGE
    return raw


def _decode_protocol(values: Sequence[int]) -> str:
    """Decode a major.minor protocol version from one register."""
    raw = values[0]
    return f"{raw >> _BITS_PER_BYTE}.{raw & _BYTE_MASK}"


def _decode_time(definition: RegisterDefinition, values: Sequence[int]) -> str:
    """Decode HHMM-packed minutes into a clock string."""
    raw = values[0]
    hours, minutes = divmod(raw, _HHMM_FACTOR)
    if minutes >= _MINUTES_PER_HOUR:
        raise DecodeError(
            f"invalid time minutes for {definition.key}: {raw}"
        )
    return f"{hours % _HOURS_PER_DAY}:{minutes:02d}"


def _decode_datetime(
    definition: RegisterDefinition, values: Sequence[int]
) -> str:
    """Decode SunSynk three-word datetime into an ISO-like string."""
    year = ((values[0] & _HIGH_BYTE_MASK) >> _BITS_PER_BYTE) + _DATETIME_YEAR_BASE
    month = values[0] & _BYTE_MASK
    day = (values[1] & _HIGH_BYTE_MASK) >> _BITS_PER_BYTE
    hour = values[1] & _BYTE_MASK
    minute = (values[2] & _HIGH_BYTE_MASK) >> _BITS_PER_BYTE
    second = values[2] & _BYTE_MASK
    if not (
        _MIN_MONTH <= month <= _MAX_MONTH
        and _MIN_DAY <= day <= _MAX_DAY
        and 0 <= hour <= _MAX_HOUR
        and 0 <= minute <= _MAX_MINUTE
        and 0 <= second <= _MAX_SECOND
    ):
        raise DecodeError(f"invalid datetime for {definition.key}")
    return f"{year}-{month:02d}-{day:02d} {hour}:{minute:02d}:{second:02d}"


def _raw_value(definition: RegisterDefinition, values: Sequence[int]) -> float | int | str:
    """Interpret raw register words according to the data type."""
    match definition.data_type:
        case "string":
            return _decode_string(values)
        case "fault":
            return _decode_fault(definition, values)
        case "float32":
            return _decode_float32(definition, values)
        case "uint32" | "int32":
            return _decode_int32(definition, values)
        case "int16":
            return _decode_int16(values)
        case "uint16":
            return values[0]
        case "protocol":
            return _decode_protocol(values)
        case "time":
            return _decode_time(definition, values)
        case "datetime":
            return _decode_datetime(definition, values)
        case _:
            raise DecodeError(f"unsupported data_type: {definition.data_type}")


def decode_math(
    definition: RegisterDefinition,
    source_values: Mapping[str, float | int],
) -> Measurement:
    """Combine decoded source values into one math measurement."""
    if definition.sources is None:
        raise DecodeError(f"math register {definition.key} has no sources")
    total = 0.0
    for source in definition.sources:
        try:
            raw = source_values[source.key]
        except KeyError as error:
            raise DecodeError(
                f"missing source value {source.key} for {definition.key}"
            ) from error
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise DecodeError(
                f"non-numeric source value {source.key} for {definition.key}"
            )
        total += raw * source.factor
    if definition.absolute and total < 0:
        total = -total
    if definition.no_negative and total < 0:
        total = 0
    value: float | int = int(total) if total == int(total) else total
    return Measurement(
        key=definition.key,
        name=definition.name,
        value=value,
        unit=definition.unit,
    )


def decode_register(
    definition: RegisterDefinition,
    values: Sequence[int],
) -> Measurement:
    """Decode raw register words for one profile definition."""
    if definition.data_type == "math":
        raise DecodeError(
            f"math register {definition.key} cannot be decoded from raw words"
        )
    if len(values) != definition.count:
        raise DecodeError(
            f"Expected {definition.count} register values for {definition.key}, "
            f"received {len(values)}"
        )
    if definition.bitmask is not None:
        values = tuple(value & definition.bitmask for value in values)
    raw = _raw_value(definition, values)
    if definition.binary:
        if not isinstance(raw, int):
            raise DecodeError(
                f"binary requires an integer value for {definition.key}"
            )
        value: float | int | str | bool = raw != 0
    elif definition.options is not None:
        if not isinstance(raw, int):
            raise DecodeError(
                f"options require an integer value for {definition.key}"
            )
        try:
            value = definition.options[raw]
        except KeyError as error:
            raise DecodeError(
                f"unknown option {raw} for {definition.key}"
            ) from error
    elif isinstance(raw, str):
        value = raw
    else:
        assert definition.scale is not None
        value = raw * definition.scale
        if definition.offset is not None:
            value -= definition.offset
    return Measurement(
        key=definition.key,
        name=definition.name,
        value=value,
        unit=definition.unit,
    )
