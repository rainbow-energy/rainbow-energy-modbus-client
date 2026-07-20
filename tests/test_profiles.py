"""Test loading and validating YAML device profiles."""

import pytest

from rainbow.profiles import (
    DeviceProfile,
    ProfileError,
    RegisterDefinition,
    load_profile,
)


def test_load_profile_from_yaml(tmp_path):
    """Load a complete device profile from YAML."""
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
    """Wrap malformed YAML in a profile error."""
    profile_path = tmp_path / "invalid.yaml"
    profile_path.write_text("manufacturer: [invalid", encoding="utf-8")

    with pytest.raises(ProfileError, match="Invalid YAML") as error:
        load_profile(profile_path)

    assert error.value.__cause__ is not None


def test_load_profile_rejects_empty_yaml(tmp_path):
    """Reject an empty YAML document."""
    profile_path = tmp_path / "empty.yaml"
    profile_path.write_text("", encoding="utf-8")

    with pytest.raises(ProfileError, match="Profile must be a YAML mapping"):
        load_profile(profile_path)


def test_load_profile_rejects_missing_manufacturer(tmp_path):
    """Reject profiles without a manufacturer."""
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
    """Reject profiles without a model."""
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
    """Reject profiles without register definitions."""
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
    """Reject a register collection that is not a list."""
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
    """Reject a register entry that is not a mapping."""
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


def test_load_profile_supports_multi_register_value(tmp_path):
    """Load a value spanning multiple Modbus registers."""
    profile_path = tmp_path / "multi-register.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: 2
    word_order: big
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    profile = load_profile(profile_path)

    assert profile.registers[0].count == 2
    assert profile.registers[0].word_order == "big"


def test_load_profile_supports_little_word_order(tmp_path):
    """Load a multi-register value with little word order."""
    profile_path = tmp_path / "little-word-order.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: 2
    word_order: little
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    profile = load_profile(profile_path)

    assert profile.registers[0].word_order == "little"


def test_load_profile_requires_word_order_for_uint32(tmp_path):
    """Require word order for unsigned 32-bit values."""
    profile_path = tmp_path / "missing-word-order.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: 2
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint32 requires word_order",
    ):
        load_profile(profile_path)


def test_load_profile_requires_word_order_for_int32(tmp_path):
    """Require word order for signed 32-bit values."""
    profile_path = tmp_path / "missing-int32-word-order.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: signed_energy
    name: Signed Energy
    address: 200
    function: holding
    data_type: int32
    count: 2
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type int32 requires word_order",
    ):
        load_profile(profile_path)


def test_load_profile_requires_word_order_for_float32(tmp_path):
    """Require word order for 32-bit floating-point values."""
    profile_path = tmp_path / "missing-float32-word-order.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: grid_voltage
    name: Grid Voltage
    address: 200
    function: holding
    data_type: float32
    count: 2
    scale: 1
    unit: V
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type float32 requires word_order",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_non_string_word_order(tmp_path):
    """Reject a word order that is not a string."""
    profile_path = tmp_path / "non-string-word-order.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: 2
    word_order: []
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 word_order must be a string",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_unsupported_word_order(tmp_path):
    """Reject an unsupported word-order value."""
    profile_path = tmp_path / "unsupported-word-order.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: 2
    word_order: middle
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 has unsupported word_order: middle",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_zero_register_count(tmp_path):
    """Reject a register definition with a zero count."""
    profile_path = tmp_path / "zero-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: 0
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_non_integer_register_count(tmp_path):
    """Reject a non-integer register count."""
    profile_path = tmp_path / "string-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: two
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_register_count_above_modbus_limit(tmp_path):
    """Reject counts above the Modbus read limit."""
    profile_path = tmp_path / "large-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: register_dump
    name: Register Dump
    address: 200
    function: holding
    data_type: string
    count: 126
    scale: 1
    unit: text
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_boolean_register_count(tmp_path):
    """Reject a boolean register count."""
    profile_path = tmp_path / "boolean-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: true
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_uint32_with_single_register(tmp_path):
    """Require two registers for unsigned 32-bit values."""
    profile_path = tmp_path / "invalid-uint32-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint32
    count: 1
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint32 requires count 2",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_int32_with_single_register(tmp_path):
    """Require two registers for signed 32-bit values."""
    profile_path = tmp_path / "invalid-int32-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: signed_energy
    name: Signed Energy
    address: 200
    function: holding
    data_type: int32
    count: 1
    scale: 0.1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type int32 requires count 2",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_float32_with_single_register(tmp_path):
    """Require two registers for 32-bit floating-point values."""
    profile_path = tmp_path / "invalid-float32-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: grid_voltage
    name: Grid Voltage
    address: 200
    function: holding
    data_type: float32
    count: 1
    scale: 1
    unit: V
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type float32 requires count 2",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_uint16_with_multiple_registers(tmp_path):
    """Require one register for unsigned 16-bit values."""
    profile_path = tmp_path / "invalid-uint16-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: 200
    function: holding
    data_type: uint16
    count: 2
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint16 requires count 1",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_int16_with_multiple_registers(tmp_path):
    """Require one register for signed 16-bit values."""
    profile_path = tmp_path / "invalid-int16-count.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_current
    name: Battery Current
    address: 200
    function: holding
    data_type: int16
    count: 2
    scale: 0.1
    unit: A
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type int16 requires count 1",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_unsupported_data_type(tmp_path):
    """Reject an unsupported register data type."""
    profile_path = tmp_path / "unsupported-data-type.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 200
    function: holding
    data_type: uint128
    count: 1
    scale: 1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 has unsupported data_type: uint128",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_missing_data_type(tmp_path):
    """Reject a register definition without a data type."""
    profile_path = tmp_path / "missing-data-type.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: 200
    function: holding
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 missing required field: data_type",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_register_range_past_final_address(tmp_path):
    """Reject a register range beyond the Modbus address space."""
    profile_path = tmp_path / "invalid-register-range.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: total_energy
    name: Total Energy
    address: 65535
    function: holding
    data_type: uint32
    count: 2
    scale: 1
    unit: kWh
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 range exceeds address 65535",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_non_string_data_type(tmp_path):
    """Reject a register data type that is not a string."""
    profile_path = tmp_path / "non-string-data-type.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: 200
    function: holding
    data_type: []
    count: 1
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 data_type must be a string",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_missing_address(tmp_path):
    """Reject a register definition without an address."""
    profile_path = tmp_path / "missing-address.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    function: holding
    data_type: uint16
    count: 1
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 missing required field: address",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_non_integer_address(tmp_path):
    """Reject a non-integer register address."""
    profile_path = tmp_path / "non-integer-address.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: two hundred
    function: holding
    data_type: uint16
    count: 1
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_boolean_address(tmp_path):
    """Reject a boolean register address."""
    profile_path = tmp_path / "boolean-address.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: true
    function: holding
    data_type: uint16
    count: 1
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_negative_address(tmp_path):
    """Reject a negative register address."""
    profile_path = tmp_path / "negative-address.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: -1
    function: holding
    data_type: uint16
    count: 1
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_profile(profile_path)


def test_load_profile_rejects_address_above_modbus_limit(tmp_path):
    """Reject addresses beyond the Modbus address space."""
    profile_path = tmp_path / "large-address.yaml"
    profile_path.write_text(
        """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: 65536
    function: holding
    data_type: uint16
    count: 1
    scale: 1
    unit: percent
    access: read
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_profile(profile_path)
