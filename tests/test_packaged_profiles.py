"""Test packaged device profiles load and decode successfully."""

from pathlib import Path

import pytest

from rainbow.profiles import DeviceProfile, load_profile
from rainbow.support import check_profile_support

_PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
_PROFILE_PATHS = sorted(_PROFILES_DIR.glob("*.yaml"))

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
def test_all_profile_registers_are_supported(profile_path: Path):
    """Reject repository profiles that use unsupported features."""
    profile = load_profile(profile_path)

    assert check_profile_support(profile) == ()
