"""Test encoding engineering values into raw Modbus register words."""

import pytest

from factories import make_register
from rainbow_energy_client.encode import encode_register


def test_encode_uint16_applies_inverse_scale():
    """Encode an engineering value back to raw words using inverse scale."""
    definition = make_register(scale=0.01, access="write")

    assert encode_register(definition, 54.32) == (5432,)


def test_encode_uint16_applies_offset_before_inverse_scale():
    """Add offset before dividing by scale when encoding."""
    definition = make_register(scale=0.1, offset=100, access="write")

    assert encode_register(definition, 25.0) == (1250,)


def test_encode_options_from_label():
    """Encode an options label into its raw integer."""
    definition = make_register(
        access="write",
        options={0: "Disable", 1: "Smartload", 2: "Generator"},
    )

    assert encode_register(definition, "Smartload") == (1,)


def test_encode_binary_true_without_bitmask():
    """Encode True as a single non-zero register word."""
    definition = make_register(access="write", binary=True)

    assert encode_register(definition, True) == (1,)


def test_encode_binary_false_with_bitmask():
    """Encode False under a bitmask as a zero contribution."""
    definition = make_register(access="write", binary=True, bitmask=0x1)

    assert encode_register(definition, False) == (0,)


def test_encode_binary_true_with_bitmask():
    """Encode True under a bitmask as the mask bits set."""
    definition = make_register(access="write", binary=True, bitmask=0x1)

    assert encode_register(definition, True) == (0x1,)


def test_encode_time_hhmm():
    """Encode an H:MM clock string as HHMM-packed minutes."""
    definition = make_register(data_type="time", access="write")

    assert encode_register(definition, "1:30") == (130,)


def test_encode_datetime_three_words():
    """Encode an ISO-like datetime into three SunSynk register words."""
    definition = make_register(data_type="datetime", count=3, access="write")

    assert encode_register(definition, "2024-07-23 14:05:09") == (
        (24 << 8) | 7,
        (23 << 8) | 14,
        (5 << 8) | 9,
    )


def test_encode_int16_negative_value():
    """Encode a negative int16 as two's complement."""
    definition = make_register(data_type="int16", access="write")

    assert encode_register(definition, -1) == (0xFFFF,)


def test_encode_int16_with_offset():
    """Add offset before inverse scale for signed registers."""
    definition = make_register(data_type="int16", scale=0.1, offset=100, access="write")

    assert encode_register(definition, -90.0) == (100,)


def test_encode_uint16_rejects_out_of_range():
    """Reject scaled values outside the unsigned 16-bit range."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="out of uint16 range"):
        encode_register(make_register(access="write"), 70000)


def test_encode_int16_rejects_out_of_range():
    """Reject scaled values outside the signed 16-bit range."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="out of int16 range"):
        encode_register(make_register(data_type="int16", access="write"), 40000)


def test_encode_options_from_raw_integer():
    """Encode a raw options integer when it is a known key."""
    definition = make_register(
        access="write",
        options={0: "Disable", 1: "Smartload"},
    )

    assert encode_register(definition, 0) == (0,)


def test_encode_options_rejects_unknown_label():
    """Reject an options label that is not defined."""
    from rainbow_energy_client.encode import EncodeError

    definition = make_register(access="write", options={0: "Disable"})
    with pytest.raises(EncodeError, match="unknown option"):
        encode_register(definition, "Missing")


def test_encode_options_rejects_unknown_integer():
    """Reject a raw options integer that is not defined."""
    from rainbow_energy_client.encode import EncodeError

    definition = make_register(access="write", options={0: "Disable"})
    with pytest.raises(EncodeError, match="unknown option"):
        encode_register(definition, 9)


def test_encode_options_rejects_non_label_non_int():
    """Reject option values that are neither labels nor integers."""
    from rainbow_energy_client.encode import EncodeError

    definition = make_register(access="write", options={0: "Disable"})
    with pytest.raises(EncodeError, match="options require a label or integer"):
        encode_register(definition, 1.5)  # type: ignore[arg-type]


def test_encode_binary_rejects_non_bool():
    """Reject binary encodes that are not booleans."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="binary requires a bool"):
        encode_register(make_register(access="write", binary=True), 1)


def test_encode_time_rejects_non_string():
    """Reject time encodes that are not strings."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="time requires a string"):
        encode_register(make_register(data_type="time", access="write"), 130)


def test_encode_time_rejects_invalid_format():
    """Reject malformed time strings."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="invalid time"):
        encode_register(make_register(data_type="time", access="write"), "nope")


def test_encode_time_rejects_out_of_range():
    """Reject time strings with invalid hour or minute."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="invalid time"):
        encode_register(make_register(data_type="time", access="write"), "25:00")


def test_encode_datetime_rejects_non_string():
    """Reject datetime encodes that are not strings."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="datetime requires a string"):
        encode_register(
            make_register(data_type="datetime", count=3, access="write"),
            1,
        )


def test_encode_datetime_rejects_invalid_format():
    """Reject malformed datetime strings."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="invalid datetime"):
        encode_register(
            make_register(data_type="datetime", count=3, access="write"),
            "not-a-datetime",
        )


def test_encode_datetime_rejects_out_of_range_fields():
    """Reject datetime strings with impossible calendar fields."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="invalid datetime"):
        encode_register(
            make_register(data_type="datetime", count=3, access="write"),
            "2024-13-01 0:00:00",
        )


def test_encode_datetime_rejects_year_before_base():
    """Reject datetime years before the SunSynk 2000 base."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="invalid datetime"):
        encode_register(
            make_register(data_type="datetime", count=3, access="write"),
            "1999-01-01 0:00:00",
        )


def test_encode_datetime_rejects_year_past_byte_offset():
    """Reject datetime years that do not fit the single-byte year offset."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="invalid datetime"):
        encode_register(
            make_register(data_type="datetime", count=3, access="write"),
            "2256-01-01 0:00:00",
        )


def test_encode_rejects_math_register():
    """Reject encoding math registers to raw words."""
    from rainbow_energy_client.encode import EncodeError
    from rainbow_energy_client.profiles import MathSource

    definition = make_register(
        data_type="math",
        address=None,
        function=None,
        scale=None,
        count=1,
        sources=(MathSource(key="a", factor=1.0),),
    )
    with pytest.raises(EncodeError, match="cannot be encoded"):
        encode_register(definition, 1)


def test_encode_rejects_non_numeric_uint16():
    """Reject non-numeric values for uint16 encodes."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="uint16 requires a numeric"):
        encode_register(make_register(access="write"), "20")


def test_encode_rejects_non_numeric_int16():
    """Reject non-numeric values for int16 encodes."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="int16 requires a numeric"):
        encode_register(make_register(data_type="int16", access="write"), "20")


def test_encode_rejects_unsupported_data_type():
    """Reject data types that have no encoder."""
    from rainbow_energy_client.encode import EncodeError

    with pytest.raises(EncodeError, match="unsupported data_type"):
        encode_register(make_register(data_type="string", count=2, access="write"), "x")
