"""Decode raw Modbus register values into typed measurements."""

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass

from rainbow.profiles import RegisterDefinition


class DecodeError(ValueError):
    """Raised when raw register values cannot be decoded."""


@dataclass(frozen=True, slots=True)
class Measurement:
    """A named engineering value decoded from Modbus registers."""

    key: str
    name: str
    value: float | int | str
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


def _raw_value(definition: RegisterDefinition, values: Sequence[int]) -> float | int | str:
    """Interpret raw register words according to the data type."""
    if definition.data_type == "string":
        return _decode_string(values)
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
    raw = values[0]
    if definition.data_type == "int16" and raw >= 0x8000:
        return raw - 0x10000
    return raw


def decode_register(
    definition: RegisterDefinition,
    values: Sequence[int],
) -> Measurement:
    """Decode raw register words for one profile definition."""
    if len(values) != definition.count:
        raise DecodeError(
            f"Expected {definition.count} register values for {definition.key}, "
            f"received {len(values)}"
        )
    if definition.bitmask is not None:
        values = tuple(value & definition.bitmask for value in values)
    raw = _raw_value(definition, values)
    value = raw if isinstance(raw, str) else raw * definition.scale
    return Measurement(
        key=definition.key,
        name=definition.name,
        value=value,
        unit=definition.unit,
    )
