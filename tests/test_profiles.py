"""Test loading and validating YAML device profiles."""

from copy import deepcopy
from unittest.mock import mock_open, patch

import pytest

from rainbow.profiles import (
    DeviceProfile,
    ProfileError,
    build_device_profile,
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


def test_load_profile_from_yaml():
    """Load and parse profile data from a YAML file."""
    yaml_text = """
manufacturer: Example Energy
model: Example 8K
registers: []
"""
    profile_file = mock_open(read_data=yaml_text)

    with patch("pathlib.Path.open", profile_file):
        profile = load_profile("profile.yaml")

    profile_file.assert_called_once_with(encoding="utf-8")
    assert profile == DeviceProfile(
        manufacturer="Example Energy",
        model="Example 8K",
        registers=(),
    )


def test_load_profile_wraps_invalid_yaml():
    """Wrap malformed YAML in a profile error."""
    with (
        patch("pathlib.Path.open", mock_open(read_data="manufacturer: [invalid")),
        pytest.raises(ProfileError, match="Invalid YAML") as error,
    ):
        load_profile("profile.yaml")

    assert error.value.__cause__ is not None


def load_valid_profile(*, profile_overrides=None, register_overrides=None):
    """Build a copy of the valid profile with selected values overridden."""
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

    return build_device_profile(profile_data)


def test_build_device_profile_rejects_non_mapping():
    """Reject parsed profile data that is not a mapping."""
    with pytest.raises(ProfileError, match="profile: .* is not of type 'object'"):
        build_device_profile(None)


def test_build_device_profile_rejects_unknown_profile_field():
    """Reject unknown profile fields that may be misspelled."""
    with pytest.raises(
        ProfileError,
        match="profile: Additional properties are not allowed",
    ):
        load_valid_profile(profile_overrides={"manufactuer": "Example Energy"})


def test_load_profile_rejects_missing_manufacturer():
    """Reject profiles without a manufacturer."""
    with pytest.raises(ProfileError, match="profile: .*manufacturer.*required property"):
        load_valid_profile(profile_overrides={"manufacturer": _DELETE})


@pytest.mark.parametrize("manufacturer", [None, "", "   "])
def test_load_profile_rejects_invalid_manufacturer(manufacturer):
    """Reject a manufacturer that is null or blank."""
    with pytest.raises(
        ProfileError,
        match="profile manufacturer: .*(not of type 'string'|does not match)",
    ):
        load_valid_profile(profile_overrides={"manufacturer": manufacturer})


def test_load_profile_rejects_missing_model():
    """Reject profiles without a model."""
    with pytest.raises(ProfileError, match="profile: .*model.*required property"):
        load_valid_profile(profile_overrides={"model": _DELETE})


@pytest.mark.parametrize("model", [None, "", "   "])
def test_load_profile_rejects_invalid_model(model):
    """Reject a model that is null or blank."""
    with pytest.raises(
        ProfileError,
        match="profile model: .*(not of type 'string'|does not match)",
    ):
        load_valid_profile(profile_overrides={"model": model})


def test_load_profile_rejects_missing_registers():
    """Reject profiles without register definitions."""
    with pytest.raises(ProfileError, match="profile: .*registers.*required property"):
        load_valid_profile(profile_overrides={"registers": _DELETE})


@pytest.mark.parametrize("registers", [None, ""])
def test_load_profile_rejects_null_or_empty_string_registers(registers):
    """Reject null or empty-string register collections."""
    with pytest.raises(
        ProfileError,
        match="profile registers: .* is not of type 'array'",
    ):
        load_valid_profile(profile_overrides={"registers": registers})


def test_load_profile_rejects_non_list_registers():
    """Reject a register collection that is not a list."""
    with pytest.raises(
        ProfileError,
        match="profile registers: .* is not of type 'array'",
    ):
        load_valid_profile(profile_overrides={"registers": {}})


def test_load_profile_rejects_non_mapping_register():
    """Reject a register entry that is not a mapping."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0: .* is not of type 'object'",
    ):
        load_valid_profile(profile_overrides={"registers": ["battery_soc"]})


def test_build_device_profile_rejects_missing_register_key():
    """Reject a register definition without a key."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0: .*key.*required property",
    ):
        load_valid_profile(register_overrides={"key": _DELETE})


@pytest.mark.parametrize("key", [None, 42, "", "   "])
def test_build_device_profile_rejects_invalid_register_key(key):
    """Reject a register definition with a null, non-string, or blank key."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.key: .*(not of type 'string'|does not match)",
    ):
        load_valid_profile(register_overrides={"key": key})


@pytest.mark.parametrize(
    "name",
    [_DELETE, None, 42, "", "   "],
)
def test_build_device_profile_rejects_invalid_register_name(name):
    """Reject a register definition with a missing or invalid name."""
    with pytest.raises(
        ProfileError,
        match=(
            "profile registers.0.*name.*"
            "(required property|not of type 'string'|does not match)"
        ),
    ):
        load_valid_profile(register_overrides={"name": name})


@pytest.mark.parametrize(
    ("function", "message"),
    [
        (_DELETE, "profile registers.0: .*function.*required property"),
        (None, "profile registers.0.function: .*not of type 'string'"),
        (42, "profile registers.0.function: .*not of type 'string'"),
        ("", "profile registers.0.function: .*is not one of"),
        ("coils", "profile registers.0.function: .*is not one of"),
    ],
)
def test_build_device_profile_rejects_invalid_register_function(
    function,
    message,
):
    """Reject a missing or unsupported Modbus register function."""
    with pytest.raises(ProfileError, match=message):
        load_valid_profile(register_overrides={"function": function})


def test_build_device_profile_supports_input_register_function():
    """Allow profiles to define input registers."""
    profile = load_valid_profile(register_overrides={"function": "input"})

    assert profile.registers[0].function == "input"


@pytest.mark.parametrize(
    ("scale", "message"),
    [
        (_DELETE, "profile registers.0: .*scale.*required property"),
        (None, "profile registers.0.scale: .*not of type 'number'"),
        ("one", "profile registers.0.scale: .*not of type 'number'"),
        (True, "profile registers.0.scale: .*not of type 'number'"),
        (0, "profile registers.0.scale: .*should not be valid"),
    ],
)
def test_build_device_profile_rejects_invalid_register_scale(scale, message):
    """Reject a missing, non-numeric, boolean, or zero scale."""
    with pytest.raises(ProfileError, match=message):
        load_valid_profile(register_overrides={"scale": scale})


@pytest.mark.parametrize("scale", [0.1, -1])
def test_build_device_profile_supports_nonzero_register_scale(scale):
    """Allow positive decimal and negative register scales."""
    profile = load_valid_profile(register_overrides={"scale": scale})

    assert profile.registers[0].scale == scale


@pytest.mark.parametrize(
    ("unit", "message"),
    [
        (_DELETE, "profile registers.0: .*unit.*required property"),
        (None, "profile registers.0.unit: .*not of type 'string'"),
        (42, "profile registers.0.unit: .*not of type 'string'"),
        ("   ", "profile registers.0.unit: .*is not valid"),
    ],
)
def test_build_device_profile_rejects_invalid_register_unit(unit, message):
    """Reject a missing, non-string, or whitespace-only unit."""
    with pytest.raises(ProfileError, match=message):
        load_valid_profile(register_overrides={"unit": unit})


def test_build_device_profile_supports_dimensionless_register():
    """Allow an empty unit for a dimensionless register value."""
    profile = load_valid_profile(register_overrides={"unit": ""})

    assert profile.registers[0].unit == ""


@pytest.mark.parametrize(
    ("access", "message"),
    [
        (_DELETE, "profile registers.0: .*access.*required property"),
        (None, "profile registers.0.access: .*not of type 'string'"),
        (42, "profile registers.0.access: .*not of type 'string'"),
        ("", "profile registers.0.access: .*is not one of"),
        ("execute", "profile registers.0.access: .*is not one of"),
    ],
)
def test_build_device_profile_rejects_invalid_register_access(access, message):
    """Reject a missing or unsupported register access mode."""
    with pytest.raises(ProfileError, match=message):
        load_valid_profile(register_overrides={"access": access})


def test_build_device_profile_supports_write_register_access():
    """Allow profiles to define writable registers."""
    profile = load_valid_profile(register_overrides={"access": "write"})

    assert profile.registers[0].access == "write"


def test_build_device_profile_rejects_duplicate_register_keys():
    """Reject profiles that define the same register key twice."""
    second_register = deepcopy(_VALID_PROFILE["registers"][0])
    second_register["address"] = 101

    with pytest.raises(
        ProfileError,
        match="duplicate register key: battery_soc",
    ):
        load_valid_profile(
            profile_overrides={
                "registers": [
                    deepcopy(_VALID_PROFILE["registers"][0]),
                    second_register,
                ]
            }
        )


def test_build_device_profile_rejects_duplicate_register_keys_ignoring_case():
    """Reject register keys that differ only by letter case."""
    second_register = deepcopy(_VALID_PROFILE["registers"][0])
    second_register["key"] = "Battery_SOC"
    second_register["address"] = 101

    with pytest.raises(
        ProfileError,
        match="duplicate register key: Battery_SOC",
    ):
        load_valid_profile(
            profile_overrides={
                "registers": [
                    deepcopy(_VALID_PROFILE["registers"][0]),
                    second_register,
                ]
            }
        )


def test_build_device_profile_rejects_overlapping_register_addresses():
    """Reject registers that claim the same address in the same function."""
    second_register = deepcopy(_VALID_PROFILE["registers"][0])
    second_register["key"] = "battery_voltage"
    second_register["name"] = "Battery Voltage"

    with pytest.raises(
        ProfileError,
        match="overlapping register addresses: battery_soc and battery_voltage",
    ):
        load_valid_profile(
            profile_overrides={
                "registers": [
                    deepcopy(_VALID_PROFILE["registers"][0]),
                    second_register,
                ]
            }
        )


def test_build_device_profile_allows_same_address_with_disjoint_bitmasks():
    """Allow two metrics to share an address when their bitmasks do not overlap."""
    first = deepcopy(_VALID_PROFILE["registers"][0])
    first["key"] = "prog1_charge"
    first["name"] = "Prog1 Charge"
    first["bitmask"] = 0x03
    first["unit"] = ""
    second = deepcopy(_VALID_PROFILE["registers"][0])
    second["key"] = "prog1_mode"
    second["name"] = "Prog1 Mode"
    second["bitmask"] = 0x1C
    second["unit"] = ""

    profile = load_valid_profile(profile_overrides={"registers": [first, second]})

    assert [register.key for register in profile.registers] == [
        "prog1_charge",
        "prog1_mode",
    ]


def test_build_device_profile_rejects_overlapping_bitmasks():
    """Reject shared addresses when bitmasks claim the same bits."""
    first = deepcopy(_VALID_PROFILE["registers"][0])
    first["key"] = "prog1_charge"
    first["name"] = "Prog1 Charge"
    first["bitmask"] = 0x03
    first["unit"] = ""
    second = deepcopy(_VALID_PROFILE["registers"][0])
    second["key"] = "prog1_mode"
    second["name"] = "Prog1 Mode"
    second["bitmask"] = 0x01
    second["unit"] = ""

    with pytest.raises(
        ProfileError,
        match="overlapping register addresses: prog1_charge and prog1_mode",
    ):
        load_valid_profile(profile_overrides={"registers": [first, second]})


def test_build_device_profile_supports_bitmask():
    """Allow a register definition to select bits within a word."""
    profile = load_valid_profile(register_overrides={"bitmask": 0x03})

    assert profile.registers[0].bitmask == 0x03


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
        match="profile registers.0: .*word_order.*required property",
    ):
        load_valid_profile(
            register_overrides={"data_type": "uint32", "count": 2}
        )


def test_load_profile_requires_word_order_for_int32():
    """Require word order for signed 32-bit values."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0: .*word_order.*required property",
    ):
        load_valid_profile(
            register_overrides={"data_type": "int32", "count": 2}
        )


def test_load_profile_requires_word_order_for_float32():
    """Require word order for 32-bit floating-point values."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0: .*word_order.*required property",
    ):
        load_valid_profile(
            register_overrides={"data_type": "float32", "count": 2}
        )


def test_load_profile_rejects_non_string_word_order():
    """Reject a word order that is not a string."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.word_order: .*not of type 'string'",
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
        match="profile registers.0.word_order: .*is not one of",
    ):
        load_valid_profile(
            register_overrides={
                "data_type": "uint32",
                "count": 2,
                "word_order": "middle",
            }
        )


def test_build_device_profile_rejects_word_order_on_uint16():
    """Reject word_order on single-register types where it has no meaning."""
    with pytest.raises(ProfileError):
        load_valid_profile(register_overrides={"word_order": "big"})


def test_build_device_profile_defaults_register_count():
    """Default an omitted register count to one."""
    profile = load_valid_profile(register_overrides={"count": _DELETE})

    assert profile.registers[0].count == 1


def test_build_device_profile_supports_variable_length_string():
    """Allow string values to span a variable number of registers."""
    profile = load_valid_profile(
        register_overrides={"data_type": "string", "count": 10}
    )

    assert profile.registers[0].count == 10


def test_build_device_profile_rejects_string_without_count():
    """Require an explicit count for string registers."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0: .*count.*required property",
    ):
        load_valid_profile(
            register_overrides={"data_type": "string", "count": _DELETE}
        )


def test_build_device_profile_rejects_string_with_non_unit_scale():
    """Reject string registers with a scale other than 1."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.scale: ",
    ):
        load_valid_profile(
            register_overrides={"data_type": "string", "count": 5, "scale": 0.1}
        )


def test_build_device_profile_rejects_bitmask_on_string():
    """Reject bitmask on string registers where it has no meaning."""
    with pytest.raises(ProfileError):
        load_valid_profile(
            register_overrides={
                "data_type": "string",
                "count": 5,
                "bitmask": 0xFF,
            }
        )


def test_build_device_profile_rejects_bitmask_on_uint32():
    """Reject bitmask on multi-register types where per-word masking is wrong."""
    with pytest.raises(ProfileError):
        load_valid_profile(
            register_overrides={
                "data_type": "uint32",
                "count": 2,
                "word_order": "big",
                "bitmask": 0xFF,
            }
        )


def test_build_device_profile_rejects_unknown_register_field():
    """Reject unknown register fields that may be misspelled."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0: Additional properties are not allowed",
    ):
        load_valid_profile(register_overrides={"adress": 100})


def test_load_profile_rejects_zero_register_count():
    """Reject a register definition with a zero count."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: .*less than the minimum",
    ):
        load_valid_profile(register_overrides={"count": 0})


def test_load_profile_rejects_non_integer_register_count():
    """Reject a non-integer register count."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: .*not of type 'integer'",
    ):
        load_valid_profile(register_overrides={"count": "two"})


def test_load_profile_rejects_register_count_above_modbus_limit():
    """Reject counts above the Modbus read limit."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: .*greater than the maximum",
    ):
        load_valid_profile(register_overrides={"count": 126})


def test_load_profile_rejects_boolean_register_count():
    """Reject a boolean register count."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: .*not of type 'integer'",
    ):
        load_valid_profile(register_overrides={"count": True})


def test_load_profile_rejects_uint32_with_single_register():
    """Require two registers for unsigned 32-bit values."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: 2 was expected",
    ):
        load_valid_profile(register_overrides={"data_type": "uint32"})


def test_load_profile_rejects_int32_with_single_register():
    """Require two registers for signed 32-bit values."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: 2 was expected",
    ):
        load_valid_profile(register_overrides={"data_type": "int32"})


def test_load_profile_rejects_float32_with_single_register():
    """Require two registers for 32-bit floating-point values."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: 2 was expected",
    ):
        load_valid_profile(register_overrides={"data_type": "float32"})


def test_load_profile_rejects_uint16_with_multiple_registers():
    """Require one register for unsigned 16-bit values."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: 1 was expected",
    ):
        load_valid_profile(register_overrides={"count": 2})


def test_load_profile_rejects_int16_with_multiple_registers():
    """Require one register for signed 16-bit values."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.count: 1 was expected",
    ):
        load_valid_profile(
            register_overrides={"data_type": "int16", "count": 2}
        )


def test_load_profile_rejects_unsupported_data_type():
    """Reject an unsupported register data type."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.data_type: .*is not one of",
    ):
        load_valid_profile(register_overrides={"data_type": "uint128"})


def test_load_profile_rejects_missing_data_type():
    """Reject a register definition without a data type."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0: .*data_type.*required property",
    ):
        load_valid_profile(register_overrides={"data_type": _DELETE})


def test_load_profile_rejects_null_data_type():
    """Reject a null register data type."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.data_type: .*not of type 'string'",
    ):
        load_valid_profile(register_overrides={"data_type": None})


def test_load_profile_rejects_empty_data_type():
    """Reject an empty register data type."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.data_type: .*is not one of",
    ):
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
                "data_type": "string",
            }
        )


def test_load_profile_rejects_non_string_data_type():
    """Reject a register data type that is not a string."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.data_type: .*not of type 'string'",
    ):
        load_valid_profile(register_overrides={"data_type": []})


def test_load_profile_rejects_missing_address():
    """Reject a register definition without an address."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0: .*address.*required property",
    ):
        load_valid_profile(register_overrides={"address": _DELETE})


@pytest.mark.parametrize("address", [None, ""])
def test_load_profile_rejects_null_or_empty_string_address(address):
    """Reject null or empty-string register addresses."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.address: .*not of type 'integer'",
    ):
        load_valid_profile(register_overrides={"address": address})


def test_load_profile_rejects_non_integer_address():
    """Reject a non-integer register address."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.address: .*not of type 'integer'",
    ):
        load_valid_profile(register_overrides={"address": "two hundred"})


def test_load_profile_rejects_boolean_address():
    """Reject a boolean register address."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.address: .*not of type 'integer'",
    ):
        load_valid_profile(register_overrides={"address": True})


def test_load_profile_rejects_negative_address():
    """Reject a negative register address."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.address: .*less than the minimum",
    ):
        load_valid_profile(register_overrides={"address": -1})


def test_load_profile_rejects_address_above_modbus_limit():
    """Reject addresses beyond the Modbus address space."""
    with pytest.raises(
        ProfileError,
        match="profile registers.0.address: .*greater than the maximum",
    ):
        load_valid_profile(register_overrides={"address": 65536})
