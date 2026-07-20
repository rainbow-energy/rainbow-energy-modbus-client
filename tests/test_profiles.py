"""Test loading and validating YAML device profiles."""

from copy import deepcopy
from unittest.mock import mock_open, patch

import pytest
import yaml

from rainbow.profiles import (
    DeviceProfile,
    ProfileError,
    RegisterDefinition,
    load_profile,
)

_DELETE = object()
_VALID_PROFILE = {
    "manufacturer": "Example Energy",
    "model": "Example 8K",
    "registers": [
        {
            "key": "battery_soc",
            "name": "Battery SOC",
            "address": 100,
            "function": "holding",
            "data_type": "uint16",
            "count": 1,
            "scale": 1,
            "unit": "percent",
            "access": "read",
        }
    ],
}


def load_profile_from_yaml(yaml_text):
    """Load a profile from in-memory YAML using a fixed filename."""
    with patch("pathlib.Path.open", mock_open(read_data=yaml_text)):
        return load_profile("profile.yaml")


def load_valid_profile(*, profile_overrides=None, register_overrides=None):
    """Load a copy of the valid profile with selected values overridden."""
    profile_data = deepcopy(_VALID_PROFILE)

    for key, value in (profile_overrides or {}).items():
        if value is _DELETE:
            profile_data.pop(key, None)
        else:
            profile_data[key] = value

    if register_overrides:
        register_data = profile_data["registers"][0]
        for key, value in register_overrides.items():
            if value is _DELETE:
                register_data.pop(key, None)
            else:
                register_data[key] = value

    return load_profile_from_yaml(yaml.safe_dump(profile_data))


def test_load_profile_from_yaml():
    """Load a complete device profile from YAML."""
    profile = load_valid_profile()

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
    with pytest.raises(ProfileError, match="Missing required field: manufacturer"):
        load_valid_profile(profile_overrides={"manufacturer": _DELETE})


@pytest.mark.parametrize("manufacturer", [None, "", "   "])
def test_load_profile_rejects_invalid_manufacturer(manufacturer):
    """Reject a manufacturer that is null or blank."""
    with pytest.raises(ProfileError, match="manufacturer must be a non-empty string"):
        load_valid_profile(profile_overrides={"manufacturer": manufacturer})


def test_load_profile_rejects_missing_model():
    """Reject profiles without a model."""
    with pytest.raises(ProfileError, match="Missing required field: model"):
        load_valid_profile(profile_overrides={"model": _DELETE})


@pytest.mark.parametrize("model", [None, "", "   "])
def test_load_profile_rejects_invalid_model(model):
    """Reject a model that is null or blank."""
    with pytest.raises(ProfileError, match="model must be a non-empty string"):
        load_valid_profile(profile_overrides={"model": model})


def test_load_profile_rejects_missing_registers():
    """Reject profiles without register definitions."""
    with pytest.raises(ProfileError, match="Missing required field: registers"):
        load_valid_profile(profile_overrides={"registers": _DELETE})


@pytest.mark.parametrize("registers", [None, ""])
def test_load_profile_rejects_null_or_empty_string_registers(registers):
    """Reject null or empty-string register collections."""
    with pytest.raises(ProfileError, match="registers must be a list"):
        load_valid_profile(profile_overrides={"registers": registers})


def test_load_profile_rejects_non_list_registers():
    """Reject a register collection that is not a list."""
    with pytest.raises(ProfileError, match="registers must be a list"):
        load_valid_profile(profile_overrides={"registers": {}})


def test_load_profile_rejects_non_mapping_register():
    """Reject a register entry that is not a mapping."""
    with pytest.raises(ProfileError, match="register 0 must be a mapping"):
        load_valid_profile(profile_overrides={"registers": ["battery_soc"]})


def test_load_profile_supports_multi_register_value():
    """Load a value spanning multiple Modbus registers."""
    profile = load_valid_profile(
        register_overrides={
            "data_type": "uint32",
            "count": 2,
            "word_order": "big",
        }
    )

    assert profile.registers[0].count == 2
    assert profile.registers[0].word_order == "big"


def test_load_profile_supports_little_word_order():
    """Load a multi-register value with little word order."""
    profile = load_valid_profile(
        register_overrides={
            "data_type": "uint32",
            "count": 2,
            "word_order": "little",
        }
    )

    assert profile.registers[0].word_order == "little"


def test_load_profile_requires_word_order_for_uint32():
    """Require word order for unsigned 32-bit values."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint32 requires word_order",
    ):
        load_valid_profile(
            register_overrides={"data_type": "uint32", "count": 2}
        )


def test_load_profile_requires_word_order_for_int32():
    """Require word order for signed 32-bit values."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type int32 requires word_order",
    ):
        load_valid_profile(
            register_overrides={"data_type": "int32", "count": 2}
        )


def test_load_profile_requires_word_order_for_float32():
    """Require word order for 32-bit floating-point values."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type float32 requires word_order",
    ):
        load_valid_profile(
            register_overrides={"data_type": "float32", "count": 2}
        )


def test_load_profile_rejects_non_string_word_order():
    """Reject a word order that is not a string."""
    with pytest.raises(
        ProfileError,
        match="register 0 word_order must be a string",
    ):
        load_valid_profile(
            register_overrides={
                "data_type": "uint32",
                "count": 2,
                "word_order": [],
            }
        )


def test_load_profile_rejects_unsupported_word_order():
    """Reject an unsupported word-order value."""
    with pytest.raises(
        ProfileError,
        match="register 0 has unsupported word_order: middle",
    ):
        load_valid_profile(
            register_overrides={
                "data_type": "uint32",
                "count": 2,
                "word_order": "middle",
            }
        )


def test_load_profile_rejects_zero_register_count():
    """Reject a register definition with a zero count."""
    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_valid_profile(register_overrides={"count": 0})


def test_load_profile_rejects_non_integer_register_count():
    """Reject a non-integer register count."""
    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_valid_profile(register_overrides={"count": "two"})


def test_load_profile_rejects_register_count_above_modbus_limit():
    """Reject counts above the Modbus read limit."""
    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_valid_profile(register_overrides={"count": 126})


def test_load_profile_rejects_boolean_register_count():
    """Reject a boolean register count."""
    with pytest.raises(
        ProfileError,
        match="register 0 count must be an integer between 1 and 125",
    ):
        load_valid_profile(register_overrides={"count": True})


def test_load_profile_rejects_uint32_with_single_register():
    """Require two registers for unsigned 32-bit values."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint32 requires count 2",
    ):
        load_valid_profile(register_overrides={"data_type": "uint32"})


def test_load_profile_rejects_int32_with_single_register():
    """Require two registers for signed 32-bit values."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type int32 requires count 2",
    ):
        load_valid_profile(register_overrides={"data_type": "int32"})


def test_load_profile_rejects_float32_with_single_register():
    """Require two registers for 32-bit floating-point values."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type float32 requires count 2",
    ):
        load_valid_profile(register_overrides={"data_type": "float32"})


def test_load_profile_rejects_uint16_with_multiple_registers():
    """Require one register for unsigned 16-bit values."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type uint16 requires count 1",
    ):
        load_valid_profile(register_overrides={"count": 2})


def test_load_profile_rejects_int16_with_multiple_registers():
    """Require one register for signed 16-bit values."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type int16 requires count 1",
    ):
        load_valid_profile(
            register_overrides={"data_type": "int16", "count": 2}
        )


def test_load_profile_rejects_unsupported_data_type():
    """Reject an unsupported register data type."""
    with pytest.raises(
        ProfileError,
        match="register 0 has unsupported data_type: uint128",
    ):
        load_valid_profile(register_overrides={"data_type": "uint128"})


def test_load_profile_rejects_missing_data_type():
    """Reject a register definition without a data type."""
    with pytest.raises(
        ProfileError,
        match="register 0 missing required field: data_type",
    ):
        load_valid_profile(register_overrides={"data_type": _DELETE})


def test_load_profile_rejects_null_data_type():
    """Reject a null register data type."""
    with pytest.raises(ProfileError, match="register 0 data_type must be a string"):
        load_valid_profile(register_overrides={"data_type": None})


def test_load_profile_rejects_empty_data_type():
    """Reject an empty register data type."""
    with pytest.raises(ProfileError, match="register 0 has unsupported data_type"):
        load_valid_profile(register_overrides={"data_type": ""})


def test_load_profile_rejects_register_range_past_final_address():
    """Reject a register range beyond the Modbus address space."""
    with pytest.raises(
        ProfileError,
        match="register 0 range exceeds address 65535",
    ):
        load_valid_profile(
            register_overrides={
                "address": 65535,
                "count": 2,
            }
        )


def test_load_profile_rejects_non_string_data_type():
    """Reject a register data type that is not a string."""
    with pytest.raises(
        ProfileError,
        match="register 0 data_type must be a string",
    ):
        load_valid_profile(register_overrides={"data_type": []})


def test_load_profile_rejects_missing_address():
    """Reject a register definition without an address."""
    with pytest.raises(
        ProfileError,
        match="register 0 missing required field: address",
    ):
        load_valid_profile(register_overrides={"address": _DELETE})


@pytest.mark.parametrize("address", [None, ""])
def test_load_profile_rejects_null_or_empty_string_address(address):
    """Reject null or empty-string register addresses."""
    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_valid_profile(register_overrides={"address": address})


def test_load_profile_rejects_non_integer_address():
    """Reject a non-integer register address."""
    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_valid_profile(register_overrides={"address": "two hundred"})


def test_load_profile_rejects_boolean_address():
    """Reject a boolean register address."""
    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_valid_profile(register_overrides={"address": True})


def test_load_profile_rejects_negative_address():
    """Reject a negative register address."""
    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_valid_profile(register_overrides={"address": -1})


def test_load_profile_rejects_address_above_modbus_limit():
    """Reject addresses beyond the Modbus address space."""
    with pytest.raises(
        ProfileError,
        match="register 0 address must be an integer between 0 and 65535",
    ):
        load_valid_profile(register_overrides={"address": 65536})
