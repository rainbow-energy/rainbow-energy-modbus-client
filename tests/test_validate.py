"""Test profile write validation helpers."""

import pytest

from factories import make_register
from rainbow_energy_modbus_client.validate import (
    ValidationError,
    validate_max,
    validate_min,
    validate_numeric_bounds,
    validate_numeric_value,
    validate_step,
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
