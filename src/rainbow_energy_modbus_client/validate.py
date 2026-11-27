"""Validate engineering write values against profile bounds."""

from rainbow_energy_modbus_client.profiles import RegisterDefinition


class ValidationError(ValueError):
    """Raised when a write value fails profile validation."""


def validate_min(definition: RegisterDefinition, value: float | int) -> None:
    """Reject values below the optional profile min."""
    if definition.min is not None and value < definition.min:
        raise ValidationError(
            f"value {value} below min {definition.min} for {definition.key}"
        )


def validate_max(definition: RegisterDefinition, value: float | int) -> None:
    """Reject values above the optional profile max."""
    if definition.max is not None and value > definition.max:
        raise ValidationError(
            f"value {value} above max {definition.max} for {definition.key}"
        )


def validate_step(definition: RegisterDefinition, value: float | int) -> None:
    """Reject values not aligned to the optional profile step."""
    if definition.step is None:
        return
    base = definition.min if definition.min is not None else 0
    if (value - base) % definition.step != 0:
        raise ValidationError(
            f"value {value} is not aligned to step {definition.step} "
            f"from {base} for {definition.key}"
        )


def validate_numeric_bounds(
    definition: RegisterDefinition, value: float | int
) -> None:
    """Apply optional min, max, and step checks to a numeric write value."""
    validate_min(definition, value)
    validate_max(definition, value)
    validate_step(definition, value)


def validate_numeric_value(
    definition: RegisterDefinition,
    value: object,
    *,
    data_type: str,
) -> float | int:
    """Require a non-bool numeric write value for scaled integer types."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(
            f"{data_type} requires a numeric value for {definition.key}"
        )
    return value


_UINT16_MAX = 0xFFFF
_INT16_MIN = -0x8000
_INT16_MAX = 0x7FFF


def validate_uint16_raw(definition: RegisterDefinition, raw: int) -> None:
    """Reject raw words outside the unsigned 16-bit range."""
    if not 0 <= raw <= _UINT16_MAX:
        raise ValidationError(
            f"encoded value out of uint16 range for {definition.key}: {raw}"
        )


def validate_int16_raw(definition: RegisterDefinition, raw: int) -> None:
    """Reject raw words outside the signed 16-bit range."""
    if not _INT16_MIN <= raw <= _INT16_MAX:
        raise ValidationError(
            f"encoded value out of int16 range for {definition.key}: {raw}"
        )
