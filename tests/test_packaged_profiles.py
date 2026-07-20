"""Test packaged device profiles load and decode successfully."""

from pathlib import Path

import pytest

from rainbow.decode import decode_register
from rainbow.profiles import DeviceProfile, load_profile

_PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
_PROFILE_PATHS = sorted(_PROFILES_DIR.glob("*.yaml"))
_SUPPORTED_FUNCTIONS = frozenset({"holding", "input"})
_SUPPORTED_DATA_TYPES = frozenset({"uint16", "int16", "uint32", "int32", "float32"})

assert _PROFILE_PATHS, f"expected profile YAML files in {_PROFILES_DIR}"


@pytest.mark.parametrize(
    "profile_path",
    _PROFILE_PATHS,
    ids=[path.name for path in _PROFILE_PATHS],
)
def test_all_profiles_load_successfully(profile_path: Path):
    """Load every repository profile without validation errors."""
    profile = load_profile(profile_path)

    assert isinstance(profile, DeviceProfile)
    assert profile.manufacturer
    assert profile.model
    assert profile.registers


@pytest.mark.parametrize(
    "profile_path",
    _PROFILE_PATHS,
    ids=[path.name for path in _PROFILE_PATHS],
)
def test_all_profile_registers_can_be_decoded(profile_path: Path):
    """Decode every register in every profile with synthetic Modbus words."""
    profile = load_profile(profile_path)

    for register in profile.registers:
        assert register.function in _SUPPORTED_FUNCTIONS, register.key
        assert register.data_type in _SUPPORTED_DATA_TYPES, register.key
        measurement = decode_register(register, (0,) * register.count)
        assert measurement.key == register.key
        assert measurement.name == register.name
        assert measurement.unit == register.unit
