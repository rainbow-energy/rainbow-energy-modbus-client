"""Test profile write validation helpers."""

import pytest

from factories import make_register
from rainbow_energy_modbus_client.validate import (
    ValidationError,
    validate_binary_value,
    validate_int16_raw,
    validate_max,
    validate_min,
    validate_numeric_bounds,
    validate_numeric_value,
    validate_options_value,
    validate_step,
    validate_uint16_raw,
)


def test_validate_min_rejects_below():
    """Reject values below the profile min."""
    definition = make_register(min=10)

    with pytest.raises(ValidationError, match="below min"):
        validate_min(definition, 9)


def test_validate_min_allows_exact_and_above():
    """Accept values at or above the profile min."""
    definition = make_register(min=10)

    validate_min(definition, 10)
    validate_min(definition, 11)


def test_validate_max_rejects_above():
    """Reject values above the profile max."""
    definition = make_register(max=8000)

    with pytest.raises(ValidationError, match="above max"):
        validate_max(definition, 8001)


def test_validate_max_allows_exact_and_below():
    """Accept values at or below the profile max."""
    definition = make_register(max=8000)

    validate_max(definition, 8000)
    validate_max(definition, 7999)


def test_validate_step_rejects_off_step():
    """Reject values that are not aligned to profile step."""
    definition = make_register(min=0, step=10)

    with pytest.raises(ValidationError, match="step"):
        validate_step(definition, 15)


def test_validate_step_allows_on_step():
    """Accept values that land on the profile step grid."""
    definition = make_register(min=0, step=10)

    validate_step(definition, 20)


def test_validate_numeric_bounds_runs_all_checks():
    """Apply min, max, and step together."""
    definition = make_register(min=0, max=100, step=10)

    validate_numeric_bounds(definition, 50)
    with pytest.raises(ValidationError, match="below min"):
        validate_numeric_bounds(definition, -1)
    with pytest.raises(ValidationError, match="above max"):
        validate_numeric_bounds(definition, 110)
    with pytest.raises(ValidationError, match="step"):
        validate_numeric_bounds(definition, 15)


def test_validate_numeric_value_rejects_non_numeric():
    """Reject non-numeric values for scaled integer types."""
    with pytest.raises(ValidationError, match="uint16 requires a numeric"):
        validate_numeric_value(make_register(), "20", data_type="uint16")


def test_validate_uint16_raw_rejects_out_of_range():
    """Reject raw words outside the unsigned 16-bit range."""
    with pytest.raises(ValidationError, match="out of uint16 range"):
        validate_uint16_raw(make_register(), 70000)


def test_validate_int16_raw_rejects_out_of_range():
    """Reject raw words outside the signed 16-bit range."""
    with pytest.raises(ValidationError, match="out of int16 range"):
        validate_int16_raw(make_register(data_type="int16"), 40000)


def test_validate_binary_value_rejects_non_bool():
    """Reject non-bool values for binary writes."""
    with pytest.raises(ValidationError, match="binary requires a bool"):
        validate_binary_value(make_register(binary=True), 1)


def test_validate_options_value_rejects_unknown_label():
    """Reject labels that are not in the options map."""
    definition = make_register(options={0: "Disable"})

    with pytest.raises(ValidationError, match="unknown option"):
        validate_options_value(definition, "Nope")
