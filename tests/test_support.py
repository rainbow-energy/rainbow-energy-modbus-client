"""Test profile support checking for unimplemented features."""

from pathlib import Path
from unittest.mock import patch

from rainbow.profiles import DeviceProfile, RegisterDefinition, build_device_profile
from rainbow.support import UnsupportedFeature, check_profile_support, main


def test_check_profile_support_reports_unsupported_data_type():
    """Report register data types the decoder cannot handle."""
    profile = DeviceProfile(
        manufacturer="Example Energy",
        model="Example 8K",
        registers=(
            RegisterDefinition(
                key="custom",
                name="Custom",
                address=0,
                function="holding",
                data_type="bool",
                scale=1,
                unit="",
                access="read",
            ),
        ),
    )

    issues = check_profile_support(profile)

    assert issues == (
        UnsupportedFeature(
            key="custom",
            reason="unsupported data_type: bool",
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


def test_check_profile_support_accepts_options_without_zero():
    """Probe an options register using a defined key, not always zero."""
    profile = build_device_profile(
        {
            "manufacturer": "Example Energy",
            "model": "Example 8K",
            "registers": [
                {
                    "key": "device_type",
                    "name": "Device Type",
                    "address": 0,
                    "function": "holding",
                    "data_type": "uint16",
                    "scale": 1,
                    "unit": "",
                    "access": "read",
                    "options": {
                        2: "Single Phase Inverter",
                        3: "Micro Inverter",
                    },
                }
            ],
        }
    )

    assert check_profile_support(profile) == ()


def test_check_profile_support_accepts_math_register():
    """Accept math registers whose sources can be decoded."""
    profile = build_device_profile(
        {
            "manufacturer": "Example Energy",
            "model": "Example 8K",
            "registers": [
                {
                    "key": "inverter_power",
                    "name": "Inverter Power",
                    "address": 175,
                    "function": "holding",
                    "data_type": "int16",
                    "scale": 1,
                    "unit": "W",
                    "access": "read",
                },
                {
                    "key": "essential_power",
                    "name": "Essential Power",
                    "data_type": "math",
                    "unit": "W",
                    "access": "read",
                    "sources": [{"key": "inverter_power", "factor": 1}],
                },
            ],
        }
    )

    assert check_profile_support(profile) == ()


def test_check_profile_support_reports_math_string_source():
    """Report math registers that source a non-numeric leaf value."""
    profile = build_device_profile(
        {
            "manufacturer": "Example Energy",
            "model": "Example 8K",
            "registers": [
                {
                    "key": "serial",
                    "name": "Serial",
                    "address": 3,
                    "function": "holding",
                    "data_type": "string",
                    "count": 1,
                    "scale": 1,
                    "unit": "",
                    "access": "read",
                },
                {
                    "key": "broken",
                    "name": "Broken",
                    "data_type": "math",
                    "unit": "",
                    "access": "read",
                    "sources": [{"key": "serial", "factor": 1}],
                },
            ],
        }
    )

    issues = check_profile_support(profile)

    assert issues == (
        UnsupportedFeature(
            key="broken",
            reason="decode failed: non-numeric source value serial for broken",
        ),
    )


def test_check_profile_script_reports_unsupported_features(tmp_path, capsys):
    """Print unsupported features and exit non-zero for a decodable profile."""
    profile_path = tmp_path / "bad.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: 184
    function: holding
    data_type: uint16
    scale: 1
    unit: "%"
    access: read
""",
        encoding="utf-8",
    )

    with patch("rainbow.support.decode_register", side_effect=RuntimeError("boom")):
        exit_code = main([str(profile_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "1 unsupported feature" in captured.err
    assert "battery_soc: decode failed: boom" in captured.err


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
