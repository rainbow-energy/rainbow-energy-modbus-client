"""Encode engineering values into raw Modbus register words."""

from rainbow_energy_modbus_client.profiles import RegisterDefinition

_UINT16_MAX = 0xFFFF
_INT16_MIN = -0x8000
_INT16_MAX = 0x7FFF
_UINT16_RANGE = 0x10000


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


def encode_register(
    definition: RegisterDefinition,
    value: float | int | str | bool,
) -> tuple[int, ...]:
    """Encode one engineering value into raw register words."""
    if definition.data_type == "math":
        raise EncodeError(
            f"math register {definition.key} cannot be encoded to raw words"
        )
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
        case _:
            raise EncodeError(f"unsupported data_type: {definition.data_type}")
