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


def validate_binary_value(
    definition: RegisterDefinition, value: object
) -> bool:
    """Require a boolean for binary writes."""
    if not isinstance(value, bool):
        raise ValidationError(f"binary requires a bool for {definition.key}")
    return value


def validate_options_value(
    definition: RegisterDefinition, value: object
) -> int:
    """Resolve an options label or raw integer to a register word."""
    assert definition.options is not None
    if isinstance(value, bool) or not isinstance(value, int):
        if not isinstance(value, str):
            raise ValidationError(
                f"options require a label or integer for {definition.key}"
            )
        for raw, label in definition.options.items():
            if label == value:
                return raw
        raise ValidationError(f"unknown option {value!r} for {definition.key}")
    if value not in definition.options:
        raise ValidationError(f"unknown option {value} for {definition.key}")
    return value


_BYTE_MASK = 0xFF
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


def validate_time_value(
    definition: RegisterDefinition, value: object
) -> tuple[int, int]:
    """Parse and range-check an H:MM or HH:MM clock string."""
    if not isinstance(value, str):
        raise ValidationError(f"time requires a string for {definition.key}")
    try:
        hour_text, minute_text = value.split(":", 1)
        hours = int(hour_text)
        minutes = int(minute_text)
    except ValueError as error:
        raise ValidationError(
            f"invalid time for {definition.key}: {value!r}"
        ) from error
    if not (0 <= hours < _HOURS_PER_DAY and 0 <= minutes < _MINUTES_PER_HOUR):
        raise ValidationError(f"invalid time for {definition.key}: {value!r}")
    return hours, minutes


def validate_datetime_value(
    definition: RegisterDefinition, value: object
) -> tuple[int, int, int, int, int, int]:
    """Parse and range-check an ISO-like datetime string."""
    if not isinstance(value, str):
        raise ValidationError(
            f"datetime requires a string for {definition.key}"
        )
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
        raise ValidationError(
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
        raise ValidationError(
            f"invalid datetime for {definition.key}: {value!r}"
        )
    year_offset = year - _DATETIME_YEAR_BASE
    if year_offset > _BYTE_MASK:
        raise ValidationError(
            f"invalid datetime for {definition.key}: {value!r}"
        )
    return year, month, day, hour, minute, second
