"""Test decoding raw Modbus register values into measurements."""

import pytest

from factories import make_register
from rainbow_energy_client.decode import DecodeError, Measurement, decode_math, decode_register
from rainbow_energy_client.profiles import MathSource

# ---------------------------------------------------------------------------
# Measurement identity and shared errors
# ---------------------------------------------------------------------------


def test_decode_measurement_copies_identity_fields():
    """Copy key, name, and unit from the definition onto the measurement."""
    definition = make_register(key="battery_soc", name="Battery SOC", unit="%")

    measurement = decode_register(definition, values=(85,))

    assert measurement == Measurement(
        key="battery_soc",
        name="Battery SOC",
        value=85,
        unit="%",
    )


def test_decode_register_rejects_wrong_value_count():
    """Reject raw values that do not match the register count."""
    with pytest.raises(DecodeError, match="Expected 1 register values"):
        decode_register(make_register(), values=(85, 86))


def test_decode_rejects_unknown_data_type():
    """Reject data types that are not explicitly supported."""
    with pytest.raises(DecodeError, match="unsupported data_type: bool"):
        decode_register(make_register(data_type="bool"), values=(1,))


# ---------------------------------------------------------------------------
# uint16, scale, and offset
# ---------------------------------------------------------------------------


def test_decode_uint16_with_identity_scale():
    """Decode an unsigned 16-bit register with scale 1."""
    assert decode_register(make_register(), values=(85,)).value == 85


def test_decode_uint16_max_value():
    """Decode the largest unsigned 16-bit register value."""
    assert decode_register(make_register(), values=(0xFFFF,)).value == 65535


def test_decode_uint16_applies_scale():
    """Apply a non-1 scale to an unsigned 16-bit register."""
    definition = make_register(scale=0.1)

    assert decode_register(definition, values=(523,)).value == pytest.approx(52.3)


def test_decode_applies_offset_after_scale():
    """Subtract an engineering offset after scaling."""
    definition = make_register(scale=0.1, offset=100)

    assert decode_register(definition, values=(1250,)).value == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# int16
# ---------------------------------------------------------------------------


def test_decode_int16_signed_value():
    """Decode a signed 16-bit register as two's complement."""
    definition = make_register(data_type="int16")

    assert decode_register(definition, values=(0xFFFF,)).value == -1


def test_decode_int16_max_positive_value():
    """Decode the largest positive signed 16-bit value."""
    definition = make_register(data_type="int16")

    assert decode_register(definition, values=(0x7FFF,)).value == 32767


def test_decode_int16_min_negative_value():
    """Decode the most negative signed 16-bit value."""
    definition = make_register(data_type="int16")

    assert decode_register(definition, values=(0x8000,)).value == -32768


# ---------------------------------------------------------------------------
# uint32 / int32
# ---------------------------------------------------------------------------


def test_decode_uint32_big_endian():
    """Combine two registers into an unsigned 32-bit value, high word first."""
    definition = make_register(data_type="uint32", count=2, word_order="big")

    assert decode_register(definition, values=(1, 2)).value == 65538


def test_decode_uint32_little_endian():
    """Combine two registers into an unsigned 32-bit value, low word first."""
    definition = make_register(data_type="uint32", count=2, word_order="little")

    assert decode_register(definition, values=(1, 2)).value == 131073


def test_decode_uint32_applies_scale():
    """Apply scale after combining a 32-bit register pair."""
    definition = make_register(
        data_type="uint32",
        scale=0.1,
        count=2,
        word_order="big",
    )

    assert decode_register(definition, values=(1, 2)).value == pytest.approx(6553.8)


def test_decode_int32_signed_value():
    """Decode a signed 32-bit value from two registers."""
    definition = make_register(data_type="int32", count=2, word_order="big")

    assert decode_register(definition, values=(0xFFFF, 0xFFFF)).value == -1


# ---------------------------------------------------------------------------
# float32
# ---------------------------------------------------------------------------


def test_decode_float32_big_endian():
    """Decode an IEEE 754 float32 from two registers, high word first."""
    definition = make_register(data_type="float32", count=2, word_order="big")

    assert decode_register(definition, values=(0x3F80, 0x0000)).value == pytest.approx(1.0)


def test_decode_float32_little_endian():
    """Decode an IEEE 754 float32 from two registers, low word first."""
    definition = make_register(data_type="float32", count=2, word_order="little")

    assert decode_register(definition, values=(0x0000, 0x3F80)).value == pytest.approx(1.0)


def test_decode_float32_rejects_nan():
    """Reject IEEE 754 float32 NaN rather than returning it as a measurement."""
    definition = make_register(data_type="float32", count=2, word_order="big")

    with pytest.raises(DecodeError, match="non-finite float32"):
        decode_register(definition, values=(0x7FC0, 0x0000))


# ---------------------------------------------------------------------------
# string
# ---------------------------------------------------------------------------


def test_decode_string_register():
    """Decode multi-register ASCII string values (two chars per word)."""
    definition = make_register(data_type="string", count=5)

    assert (
        decode_register(
            definition,
            values=(0x3132, 0x3334, 0x3536, 0x3738, 0x3930),
        ).value
        == "1234567890"
    )


def test_decode_string_strips_trailing_null_padding():
    """Drop null bytes used to pad short serial numbers."""
    definition = make_register(data_type="string", count=5)

    assert (
        decode_register(
            definition,
            values=(0x4142, 0x4344, 0x0000, 0x0000, 0x0000),
        ).value
        == "ABCD"
    )


# ---------------------------------------------------------------------------
# protocol
# ---------------------------------------------------------------------------


def test_decode_protocol_version_string():
    """Decode a protocol register as major.minor from one word."""
    definition = make_register(data_type="protocol")

    assert decode_register(definition, values=(0x0105,)).value == "1.5"


def test_decode_protocol_version_bounds():
    """Decode the lowest and highest protocol version words."""
    definition = make_register(data_type="protocol")

    assert decode_register(definition, values=(0x0000,)).value == "0.0"
    assert decode_register(definition, values=(0xFFFF,)).value == "255.255"


# ---------------------------------------------------------------------------
# time
# ---------------------------------------------------------------------------


def test_decode_time_as_clock_string():
    """Decode a packed time register as H:MM."""
    definition = make_register(data_type="time")

    assert decode_register(definition, values=(830,)).value == "8:30"


def test_decode_time_rejects_invalid_minutes():
    """Reject packed times whose minute field is 60 or greater."""
    definition = make_register(data_type="time")

    with pytest.raises(DecodeError, match="invalid time minutes"):
        decode_register(definition, values=(899,))


# ---------------------------------------------------------------------------
# datetime
# ---------------------------------------------------------------------------


def test_decode_datetime_as_string():
    """Decode three packed words as a SunSynk-style datetime string."""
    definition = make_register(data_type="datetime", count=3)

    assert (
        decode_register(
            definition,
            values=((24 << 8) + 3, (15 << 8) + 8, (30 << 8) + 5),
        ).value
        == "2024-03-15 8:30:05"
    )


def test_decode_datetime_rejects_invalid_fields():
    """Reject datetime words with out-of-range calendar fields."""
    definition = make_register(data_type="datetime", count=3)

    with pytest.raises(DecodeError, match="invalid datetime"):
        decode_register(
            definition,
            values=((24 << 8) + 13, (15 << 8) + 8, (30 << 8) + 5),
        )


# ---------------------------------------------------------------------------
# fault
# ---------------------------------------------------------------------------


def test_decode_fault_labeled_bit():
    """Decode a set fault bit as an F-code with its label."""
    definition = make_register(
        data_type="fault",
        count=4,
        bits={13: "Working mode change"},
    )

    assert decode_register(definition, values=(1 << 12, 0, 0, 0)).value == "F13 Working mode change"


def test_decode_fault_unlabeled_empty_and_multiple():
    """Decode unlabeled bits, clear registers, and multiple set bits."""
    definition = make_register(
        data_type="fault",
        count=4,
        bits={13: "Working mode change"},
    )

    assert decode_register(definition, values=(0, 0, 0, 0)).value == ""
    assert decode_register(definition, values=(0, 1 << 9, 0, 0)).value == "F26"
    assert (
        decode_register(definition, values=(1 << 12, 1 << 9, 0, 0)).value
        == "F13 Working mode change, F26"
    )


# ---------------------------------------------------------------------------
# bitmask
# ---------------------------------------------------------------------------


def test_decode_applies_bitmask():
    """Keep only the selected bits before scaling."""
    definition = make_register(bitmask=0x03)

    assert decode_register(definition, values=(0x1D,)).value == 1


def test_decode_applies_bitmask_before_int16_sign():
    """Apply bitmask before interpreting a signed 16-bit value."""
    definition = make_register(data_type="int16", bitmask=0x00FF)

    assert decode_register(definition, values=(0xFFFF,)).value == 255


# ---------------------------------------------------------------------------
# options
# ---------------------------------------------------------------------------


def test_decode_applies_options():
    """Map a decoded integer to its options label."""
    definition = make_register(
        bitmask=0x03,
        options={
            0: "No Grid or Gen",
            1: "Allow Grid",
            2: "Allow Gen",
            3: "Allow Grid & Gen",
        },
    )

    assert decode_register(definition, values=(0x11,)).value == "Allow Grid"


def test_decode_rejects_unknown_option():
    """Reject a decoded value that is not in the options map."""
    definition = make_register(
        options={
            0: "No Grid or Gen",
            1: "Allow Grid",
        },
    )

    with pytest.raises(DecodeError, match="unknown option 2"):
        decode_register(definition, values=(2,))


def test_decode_rejects_options_on_non_integer_value():
    """Reject options when the decoded raw value is not an integer."""
    definition = make_register(
        data_type="float32",
        count=2,
        word_order="big",
        options={0: "off", 1: "on"},
    )

    with pytest.raises(DecodeError, match="options require an integer value"):
        decode_register(definition, values=(16256, 0))


# ---------------------------------------------------------------------------
# binary
# ---------------------------------------------------------------------------


def test_decode_applies_binary():
    """Map a nonzero masked register to True."""
    definition = make_register(bitmask=0x1, binary=True)

    assert decode_register(definition, values=(0x5,)).value is True


def test_decode_binary_zero_is_false():
    """Map a zero masked register to False."""
    definition = make_register(bitmask=0x1, binary=True)

    assert decode_register(definition, values=(0x4,)).value is False


def test_decode_rejects_binary_on_non_integer_value():
    """Reject binary when the decoded raw value is not an integer."""
    definition = make_register(
        data_type="float32",
        count=2,
        word_order="big",
        binary=True,
    )

    with pytest.raises(DecodeError, match="binary requires an integer value"):
        decode_register(definition, values=(16256, 0))


# ---------------------------------------------------------------------------
# math
# ---------------------------------------------------------------------------


def test_decode_math_applies_weighted_sum():
    """Combine source engineering values with per-source factors."""
    definition = make_register(
        data_type="math",
        sources=(
            MathSource(key="inverter_power", factor=1),
            MathSource(key="grid_power", factor=1),
            MathSource(key="aux_power", factor=-1),
        ),
    )

    assert (
        decode_math(
            definition,
            {"inverter_power": 1000, "grid_power": 200, "aux_power": 50},
        ).value
        == 1150
    )


def test_decode_math_applies_no_negative():
    """Clamp negative math results to zero when requested."""
    definition = make_register(
        data_type="math",
        sources=(
            MathSource(key="grid_ct_power", factor=1),
            MathSource(key="grid_ld_power", factor=-1),
        ),
        no_negative=True,
    )

    assert (
        decode_math(
            definition,
            {"grid_ct_power": 100, "grid_ld_power": 250},
        ).value
        == 0
    )


def test_decode_math_applies_absolute():
    """Take the absolute value of a math result when requested."""
    definition = make_register(
        data_type="math",
        sources=(
            MathSource(key="inverter_power", factor=1),
            MathSource(key="grid_power", factor=1),
            MathSource(key="aux_power", factor=-1),
        ),
        absolute=True,
    )

    assert (
        decode_math(
            definition,
            {"inverter_power": 100, "grid_power": 50, "aux_power": 200},
        ).value
        == 50
    )


def test_decode_math_rejects_missing_source_value():
    """Reject math decode when a required source value is absent."""
    definition = make_register(
        data_type="math",
        sources=(MathSource(key="inverter_power", factor=1),),
    )

    with pytest.raises(DecodeError, match="missing source value inverter_power"):
        decode_math(definition, {})


def test_decode_math_rejects_non_numeric_source_value():
    """Reject math decode when a source value is not numeric."""
    definition = make_register(
        data_type="math",
        sources=(MathSource(key="serial", factor=1),),
    )

    with pytest.raises(DecodeError, match="non-numeric source value serial"):
        decode_math(definition, {"serial": "ABC"})


def test_decode_math_rejects_missing_sources():
    """Reject math decode when the definition has no sources."""
    definition = make_register(data_type="math")

    with pytest.raises(DecodeError, match="has no sources"):
        decode_math(definition, {})


def test_decode_register_rejects_math_definition():
    """Reject decoding a math register from raw Modbus words."""
    definition = make_register(
        data_type="math",
        sources=(MathSource(key="inverter_power", factor=1),),
    )

    with pytest.raises(DecodeError, match="cannot be decoded from raw words"):
        decode_register(definition, values=(1,))
