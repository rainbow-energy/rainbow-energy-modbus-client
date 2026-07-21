"""Decode raw Modbus register values into typed measurements."""

import math
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rainbow.profiles import RegisterDefinition


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
    return "".join(chr(word >> 8) + chr(word & 0xFF) for word in values).rstrip("\x00")


def _decode_fault(
    definition: RegisterDefinition, values: Sequence[int]
) -> str:
    """Decode set bits across words as comma-separated F-codes."""
    labels = definition.bits or {}
    faults: list[str] = []
    offset = 0
    for word in values:
        for bit in range(16):
            if word & (1 << bit):
                number = bit + offset + 1
                label = labels.get(number, "")
                faults.append(f"F{number:02d} {label}".strip())
        offset += 16
    return ", ".join(faults)


def _raw_value(definition: RegisterDefinition, values: Sequence[int]) -> float | int | str:
    """Interpret raw register words according to the data type."""
    if definition.data_type == "string":
        return _decode_string(values)
    if definition.data_type == "fault":
        return _decode_fault(definition, values)
    if definition.data_type == "float32":
        high, low = _ordered_words(definition, values)
        value = struct.unpack(">f", struct.pack(">HH", high, low))[0]
        if not math.isfinite(value):
            raise DecodeError(
                f"non-finite float32 value for {definition.key}: {value}"
            )
        return value
    if definition.data_type in {"uint32", "int32"}:
        high, low = _ordered_words(definition, values)
        raw = (high << 16) | low
        if definition.data_type == "int32" and raw >= 0x8000_0000:
            return raw - 0x1_0000_0000
        return raw
    if definition.data_type == "int16":
        raw = values[0]
        if raw >= 0x8000:
            return raw - 0x10000
        return raw
    if definition.data_type == "uint16":
        return values[0]
    if definition.data_type == "protocol":
        raw = values[0]
        return f"{raw >> 8}.{raw & 0xFF}"
    if definition.data_type == "time":
        raw = values[0]
        hours, minutes = divmod(raw, 100)
        if minutes >= 60:
            raise DecodeError(
                f"invalid time minutes for {definition.key}: {raw}"
            )
        return f"{hours % 24}:{minutes:02d}"
    if definition.data_type == "datetime":
        year = ((values[0] & 0xFF00) >> 8) + 2000
        month = values[0] & 0xFF
        day = (values[1] & 0xFF00) >> 8
        hour = values[1] & 0xFF
        minute = (values[2] & 0xFF00) >> 8
        second = values[2] & 0xFF
        if not (
            1 <= month <= 12
            and 1 <= day <= 31
            and 0 <= hour <= 23
            and 0 <= minute <= 59
            and 0 <= second <= 59
        ):
            raise DecodeError(f"invalid datetime for {definition.key}")
        return f"{year}-{month:02d}-{day:02d} {hour}:{minute:02d}:{second:02d}"
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
