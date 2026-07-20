import pytest

from rainbow.profiles import (
    DeviceProfile,
    ProfileError,
    RegisterDefinition,
    load_profile,
)


def test_load_profile_from_yaml(tmp_path):
    profile_path = tmp_path / "example.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: 100
    function: holding
    data_type: uint16
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    profile = load_profile(profile_path)

    assert profile == DeviceProfile(
        manufacturer="Example Energy",
        model="Example 8K",
        registers=(
            RegisterDefinition(
                key="battery_soc",
                name="Battery SOC",
                address=100,
                function="holding",
                data_type="uint16",
                scale=1,
                unit="percent",
                access="read",
            ),
        ),
    )


def test_load_profile_wraps_invalid_yaml(tmp_path):
    profile_path = tmp_path / "invalid.yaml"
    profile_path.write_text("manufacturer: [invalid", encoding="utf-8")

    with pytest.raises(ProfileError, match="Invalid YAML") as error:
        load_profile(profile_path)

    assert error.value.__cause__ is not None


def test_load_profile_rejects_empty_yaml(tmp_path):
    profile_path = tmp_path / "empty.yaml"
    profile_path.write_text("", encoding="utf-8")

    with pytest.raises(ProfileError, match="Profile must be a YAML mapping"):
        load_profile(profile_path)


def test_load_profile_rejects_missing_manufacturer(tmp_path):
    profile_path = tmp_path / "missing-manufacturer.yaml"
    profile_path.write_text(
        """
model: Example 8K
registers: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="Missing required field: manufacturer"):
        load_profile(profile_path)


def test_load_profile_rejects_missing_model(tmp_path):
    profile_path = tmp_path / "missing-model.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
registers: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="Missing required field: model"):
        load_profile(profile_path)


def test_load_profile_rejects_missing_registers(tmp_path):
    profile_path = tmp_path / "missing-registers.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
""",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="Missing required field: registers"):
        load_profile(profile_path)


def test_load_profile_rejects_non_list_registers(tmp_path):
    profile_path = tmp_path / "invalid-registers.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="registers must be a list"):
        load_profile(profile_path)


def test_load_profile_rejects_non_mapping_register(tmp_path):
    profile_path = tmp_path / "invalid-register.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - battery_soc
""",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="register 0 must be a mapping"):
        load_profile(profile_path)
