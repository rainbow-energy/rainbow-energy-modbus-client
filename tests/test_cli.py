"""Test the packaged rainbow-energy-client CLI."""

from rainbow_energy_client.cli import main
from rainbow_energy_client.profiles import list_packaged_profiles


def test_cli_without_subcommand_prints_usage_and_exits_2(capsys):
    """Require a subcommand when the CLI is invoked with no arguments."""
    exit_code = main([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "usage:" in captured.err.lower()


def test_list_packaged_profiles_returns_sorted_stems():
    """Discover packaged profile YAML stems from package data."""
    names = list_packaged_profiles()

    assert names == tuple(sorted(names))
    assert "sunsynk_8k_sg05lp1" in names


def test_cli_list_profiles_prints_packaged_names(capsys):
    """Print one packaged profile stem per line."""
    exit_code = main(["list-profiles"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.splitlines() == list(list_packaged_profiles())


def test_cli_check_profile_accepts_packaged_name(capsys):
    """Validate a packaged profile by stem name."""
    exit_code = main(["check-profile", "sunsynk_8k_sg05lp1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "registers are supported" in captured.out


def test_cli_check_profile_rejects_unknown_profile(capsys):
    """Exit with a profile error when the name or path cannot be loaded."""
    exit_code = main(["check-profile", "missing_device"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "profile error:" in captured.err
