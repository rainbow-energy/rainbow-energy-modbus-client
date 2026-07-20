"""Test loading and validating YAML device profiles."""

from unittest.mock import mock_open, patch

import pytest

from rainbow.profiles import (
    DeviceProfile,
    ProfileError,
    RegisterDefinition,
    load_profile,
)


def load_profile_from_yaml(yaml_text):
    """Load a profile from in-memory YAML using a fixed filename."""
    with patch("pathlib.Path.open", mock_open(read_data=yaml_text)):
        return load_profile("profile.yaml")


def test_load_profile_from_yaml():
    """Load a complete device profile from YAML."""
    yaml_text = """
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
"""

    profile = load_profile_from_yaml(yaml_text)

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


def test_load_profile_wraps_invalid_yaml():
    """Wrap malformed YAML in a profile error."""
    yaml_text = "manufacturer: [invalid"

    with pytest.raises(ProfileError, match="Invalid YAML") as error:
        load_profile_from_yaml(yaml_text)

    assert error.value.__cause__ is not None


def test_load_profile_rejects_empty_yaml():
    """Reject an empty YAML document."""
    yaml_text = ""

    with pytest.raises(ProfileError, match="Profile must be a YAML mapping"):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_missing_manufacturer():
    """Reject profiles without a manufacturer."""
    yaml_text = """
model: Example 8K
registers: []
"""

    with pytest.raises(ProfileError, match="Missing required field: manufacturer"):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_missing_model():
    """Reject profiles without a model."""
    yaml_text = """
manufacturer: Example Energy
registers: []
"""

    with pytest.raises(ProfileError, match="Missing required field: model"):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_missing_registers():
    """Reject profiles without register definitions."""
    yaml_text = """
manufacturer: Example Energy
model: Example 8K
"""

    with pytest.raises(ProfileError, match="Missing required field: registers"):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_non_list_registers():
    """Reject a register collection that is not a list."""
    yaml_text = """
manufacturer: Example Energy
model: Example 8K
registers: {}
"""

    with pytest.raises(ProfileError, match="registers must be a list"):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_non_mapping_register():
    """Reject a register entry that is not a mapping."""
    yaml_text = """
manufacturer: Example Energy
model: Example 8K
registers:
  - battery_soc
"""

    with pytest.raises(ProfileError, match="register 0 must be a mapping"):
        load_profile_from_yaml(yaml_text)


def test_load_profile_supports_multi_register_value():
    """Load a value spanning multiple Modbus registers."""
    yaml_text = """
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
"""

    profile = load_profile_from_yaml(yaml_text)

    assert profile.registers[0].count == 2
    assert profile.registers[0].word_order == "big"


def test_load_profile_supports_little_word_order():
    """Load a multi-register value with little word order."""
    yaml_text = """
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
"""

    profile = load_profile_from_yaml(yaml_text)

    assert profile.registers[0].word_order == "little"


def test_load_profile_requires_word_order_for_uint32():
    """Require word order for unsigned 32-bit values."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint32 requires word_order",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_requires_word_order_for_int32():
    """Require word order for signed 32-bit values."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type int32 requires word_order",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_requires_word_order_for_float32():
    """Require word order for 32-bit floating-point values."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type float32 requires word_order",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_non_string_word_order():
    """Reject a word order that is not a string."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 word_order must be a string",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_unsupported_word_order():
    """Reject an unsupported word-order value."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 has unsupported word_order: middle",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_zero_register_count():
    """Reject a register definition with a zero count."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_non_integer_register_count():
    """Reject a non-integer register count."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_register_count_above_modbus_limit():
    """Reject counts above the Modbus read limit."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_boolean_register_count():
    """Reject a boolean register count."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_uint32_with_single_register():
    """Require two registers for unsigned 32-bit values."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint32 requires count 2",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_int32_with_single_register():
    """Require two registers for signed 32-bit values."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type int32 requires count 2",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_float32_with_single_register():
    """Require two registers for 32-bit floating-point values."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type float32 requires count 2",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_uint16_with_multiple_registers():
    """Require one register for unsigned 16-bit values."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint16 requires count 1",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_int16_with_multiple_registers():
    """Require one register for signed 16-bit values."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type int16 requires count 1",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_unsupported_data_type():
    """Reject an unsupported register data type."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 has unsupported data_type: uint128",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_missing_data_type():
    """Reject a register definition without a data type."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 missing required field: data_type",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_register_range_past_final_address():
    """Reject a register range beyond the Modbus address space."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 range exceeds address 65535",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_non_string_data_type():
    """Reject a register data type that is not a string."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 data_type must be a string",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_missing_address():
    """Reject a register definition without an address."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 missing required field: address",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_non_integer_address():
    """Reject a non-integer register address."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_boolean_address():
    """Reject a boolean register address."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_negative_address():
    """Reject a negative register address."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_profile_from_yaml(yaml_text)


def test_load_profile_rejects_address_above_modbus_limit():
    """Reject addresses beyond the Modbus address space."""
    yaml_text = """
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
"""

    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_profile_from_yaml(yaml_text)
