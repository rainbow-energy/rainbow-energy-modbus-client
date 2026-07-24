"""Test encoding engineering values into raw Modbus register words."""

import pytest

from factories import make_register
from rainbow_energy_modbus_client.encode import EncodeError, encode_register
from rainbow_energy_modbus_client.profiles import MathSource


def test_encode_uint16_applies_inverse_scale():
    """Encode an engineering value back to raw words using inverse scale."""
    definition = make_register(scale=0.01, access="write")

    assert encode_register(definition, 54.32) == (5432,)


def test_encode_uint16_applies_offset_before_inverse_scale():
    """Add offset before dividing by scale when encoding."""
    definition = make_register(scale=0.1, offset=100, access="write")

    assert encode_register(definition, 25.0) == (1250,)


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
    with pytest.raises(EncodeError, match="out of uint16 range"):
        encode_register(make_register(access="write"), 70000)


def test_encode_int16_rejects_out_of_range():
    """Reject scaled values outside the signed 16-bit range."""
    with pytest.raises(EncodeError, match="out of int16 range"):
        encode_register(make_register(data_type="int16", access="write"), 40000)


def test_encode_rejects_math_register():
    """Reject encoding math registers to raw words."""
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
    with pytest.raises(EncodeError, match="uint16 requires a numeric"):
        encode_register(make_register(access="write"), "20")


def test_encode_rejects_non_numeric_int16():
    """Reject non-numeric values for int16 encodes."""
    with pytest.raises(EncodeError, match="int16 requires a numeric"):
        encode_register(make_register(data_type="int16", access="write"), "20")


def test_encode_rejects_unsupported_data_type():
    """Reject data types that have no encoder."""
    with pytest.raises(EncodeError, match="unsupported data_type"):
        encode_register(make_register(data_type="string", count=2, access="write"), "x")
