"""Test packaged device profiles load and decode successfully."""

from pathlib import Path

import pytest

from rainbow_energy_client.profiles import DeviceProfile, ProfileError, load_profile
from rainbow_energy_client.support import check_profile_support

_PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
_DRAFT_DIR = _PROFILES_DIR / "draft"
_PROFILE_PATHS = sorted(_PROFILES_DIR.glob("*.yaml"))
_DRAFT_PROFILE_PATHS = sorted(_DRAFT_DIR.glob("*.yaml"))

assert _PROFILE_PATHS, f"expected profile YAML files in {_PROFILES_DIR}"


def test_packaged_profile_paths_exclude_draft_directory():
    """Production checks only use top-level profiles, never profiles/draft/."""
    assert _DRAFT_PROFILE_PATHS, f"expected draft profiles in {_DRAFT_DIR}"
    assert all(path.parent == _PROFILES_DIR for path in _PROFILE_PATHS)
    assert not any(path in _PROFILE_PATHS for path in _DRAFT_PROFILE_PATHS)


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
