"""Test packaged device profiles load and decode successfully."""

from pathlib import Path

import pytest

from rainbow_energy_client.profiles import (
    DeviceProfile,
    ProfileError,
    list_packaged_profiles,
    load_packaged_profile,
    load_profile,
)
from rainbow_energy_client.support import check_profile_support

_PACKAGED_NAMES = list_packaged_profiles()
_DRAFT_DIR = Path(__file__).resolve().parents[1] / "profiles" / "draft"
_DRAFT_PROFILE_PATHS = sorted(_DRAFT_DIR.glob("*.yaml"))

assert _PACKAGED_NAMES, "expected packaged profile YAML files in package data"


def test_load_packaged_profile_by_name():
    """Load a production profile shipped inside the package by stem name."""
    profile = load_packaged_profile("sunsynk_8k_sg05lp1")

    assert profile.manufacturer == "Sunsynk"
    assert profile.model == "SYNK-8K-SG05LP1"
    assert {register.key for register in profile.registers} >= {"battery_soc"}


def test_load_packaged_profile_rejects_unknown_name():
    """Reject packaged profile names that are not shipped with the package."""
    with pytest.raises(ProfileError, match="Unknown packaged profile: missing_device"):
        load_packaged_profile("missing_device")


def test_packaged_profiles_exclude_draft_directory():
    """Draft maps live under profiles/draft/ and are not package data."""
    assert _DRAFT_PROFILE_PATHS, f"expected draft profiles in {_DRAFT_DIR}"
    assert "draft" not in _PACKAGED_NAMES


@pytest.mark.parametrize(
    "name",
    _PACKAGED_NAMES,
)
def test_all_profiles_load_successfully(name: str):
    """Load every packaged profile without validation errors."""
    profile = load_packaged_profile(name)

    assert isinstance(profile, DeviceProfile)
    assert profile.manufacturer
    assert profile.model
    assert profile.registers


@pytest.mark.parametrize(
    "name",
    _PACKAGED_NAMES,
)
def test_all_profile_registers_are_supported(name: str):
    """Reject packaged profiles that use unsupported features."""
    profile = load_packaged_profile(name)

    assert check_profile_support(profile) == ()


@pytest.mark.parametrize(
    "profile_path",
    _DRAFT_PROFILE_PATHS,
    ids=[path.name for path in _DRAFT_PROFILE_PATHS],
)
def test_draft_profiles_can_be_analyzed(profile_path: Path):
    """Draft profiles may fail to load or report unsupported features."""
    try:
        profile = load_profile(profile_path)
    except ProfileError:
        return

    issues = check_profile_support(profile)
    assert isinstance(issues, tuple)
