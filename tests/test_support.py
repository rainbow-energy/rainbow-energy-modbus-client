"""Test profile support checking for unimplemented features."""

from pathlib import Path
from unittest.mock import patch

from rainbow.profiles import DeviceProfile, RegisterDefinition, build_device_profile
from rainbow.support import UnsupportedFeature, check_profile_support, main


def test_check_profile_support_reports_unsupported_data_type():
    """Report register data types the decoder cannot handle."""
    profile = build_device_profile(
        {
            "manufacturer": "Example Energy",
            "model": "Example 8K",
            "registers": [
                {
                    "key": "serial",
                    "name": "Serial",
                    "address": 0,
                    "function": "holding",
                    "data_type": "string",
                    "count": 5,
                    "scale": 1,
                    "unit": "",
                    "access": "read",
                }
            ],
        }
    )

    issues = check_profile_support(profile)

    assert issues == (
        UnsupportedFeature(
            key="serial",
            reason="unsupported data_type: string",
        ),
    )


def test_check_profile_support_reports_unsupported_function():
    """Report Modbus functions the reader cannot fetch."""
    profile = DeviceProfile(
        manufacturer="Example Energy",
        model="Example 8K",
        registers=(
            RegisterDefinition(
                key="status",
                name="Status",
                address=1,
                function="coil",
                data_type="uint16",
                scale=1,
                unit="",
                access="read",
            ),
        ),
    )

    issues = check_profile_support(profile)

    assert issues == (
        UnsupportedFeature(key="status", reason="unsupported function: coil"),
    )


def test_check_profile_support_reports_decode_failure():
    """Report registers that fail during synthetic decoding."""
    profile = build_device_profile(
        {
            "manufacturer": "Example Energy",
            "model": "Example 8K",
            "registers": [
                {
                    "key": "battery_soc",
                    "name": "Battery SOC",
                    "address": 184,
                    "function": "holding",
                    "data_type": "uint16",
                    "scale": 1,
                    "unit": "%",
                    "access": "read",
                }
            ],
        }
    )

    with patch(
        "rainbow.support.decode_register",
        side_effect=RuntimeError("boom"),
    ):
        issues = check_profile_support(profile)

    assert issues == (
        UnsupportedFeature(key="battery_soc", reason="decode failed: boom"),
    )


def test_check_profile_support_accepts_supported_registers():
    """Return no issues for registers the stack can decode."""
    profile = build_device_profile(
        {
            "manufacturer": "Example Energy",
            "model": "Example 8K",
            "registers": [
                {
                    "key": "battery_soc",
                    "name": "Battery SOC",
                    "address": 184,
                    "function": "holding",
                    "data_type": "uint16",
                    "scale": 1,
                    "unit": "%",
                    "access": "read",
                }
            ],
        }
    )

    assert check_profile_support(profile) == ()


def test_check_profile_script_reports_unsupported_features(tmp_path, capsys):
    """Print unsupported features and exit non-zero for a bad profile."""
    profile_path = tmp_path / "bad.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: serial
    name: Serial
    address: 0
    function: holding
    data_type: string
    count: 5
    scale: 1
    unit: ""
    access: read
""",
        encoding="utf-8",
    )

    exit_code = main([str(profile_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "serial: unsupported data_type: string" in captured.err


def test_check_profile_script_accepts_supported_profile(capsys):
    """Exit zero when every register in the profile is supported."""
    profile_path = (
        Path(__file__).resolve().parents[1] / "profiles" / "sunsynk_8k_sg05lp1.yaml"
    )
    exit_code = main([str(profile_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "registers are supported" in captured.out


def test_check_profile_script_reports_invalid_profile(tmp_path, capsys):
    """Exit with a profile error when the YAML fails validation."""
    profile_path = tmp_path / "invalid.yaml"
    profile_path.write_text("manufacturer: Example Energy\n", encoding="utf-8")

    exit_code = main([str(profile_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "profile error:" in captured.err
