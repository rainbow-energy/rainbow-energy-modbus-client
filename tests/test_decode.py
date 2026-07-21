"""Test decoding raw Modbus register values into measurements."""

import pytest

from rainbow.decode import DecodeError, Measurement, decode_register
from rainbow.profiles import RegisterDefinition


def test_decode_uint16_with_identity_scale():
    """Decode an unsigned 16-bit register with scale 1."""
    definition = RegisterDefinition(
        key="battery_soc",
        name="Battery SOC",
        address=184,
        function="holding",
        data_type="uint16",
        scale=1,
        unit="%",
        access="read",
    )

    measurement = decode_register(definition, values=(85,))

    assert measurement == Measurement(
        key="battery_soc",
        name="Battery SOC",
        value=85,
        unit="%",
    )


def test_decode_uint16_max_value():
    """Decode the largest unsigned 16-bit register value."""
    definition = RegisterDefinition(
        key="battery_soc",
        name="Battery SOC",
        address=184,
        function="holding",
        data_type="uint16",
        scale=1,
        unit="%",
        access="read",
    )

    measurement = decode_register(definition, values=(0xFFFF,))

    assert measurement.value == 65535


def test_decode_uint16_applies_scale():
    """Apply a non-1 scale to an unsigned 16-bit register."""
    definition = RegisterDefinition(
        key="battery_voltage",
        name="Battery Voltage",
        address=183,
        function="holding",
        data_type="uint16",
        scale=0.1,
        unit="V",
        access="read",
    )

    measurement = decode_register(definition, values=(523,))

    assert measurement.key == "battery_voltage"
    assert measurement.name == "Battery Voltage"
    assert measurement.value == pytest.approx(52.3)
    assert measurement.unit == "V"


def test_decode_applies_offset_after_scale():
    """Subtract an engineering offset after scaling."""
    definition = RegisterDefinition(
        key="battery_temperature",
        name="Battery Temperature",
        address=182,
        function="holding",
        data_type="uint16",
        scale=0.1,
        unit="°C",
        access="read",
        offset=100,
    )

    measurement = decode_register(definition, values=(1250,))

    assert measurement.key == "battery_temperature"
    assert measurement.name == "Battery Temperature"
    assert measurement.value == pytest.approx(25.0)
    assert measurement.unit == "°C"


def test_decode_applies_options():
    """Map a decoded integer to its options label."""
    definition = RegisterDefinition(
        key="prog1_charge",
        name="Prog1 Charge",
        address=172,
        function="holding",
        data_type="uint16",
        scale=1,
        unit="",
        access="read",
        bitmask=0x03,
        options={
            0: "No Grid or Gen",
            1: "Allow Grid",
            2: "Allow Gen",
            3: "Allow Grid & Gen",
        },
    )

    measurement = decode_register(definition, values=(0x11,))

    assert measurement == Measurement(
        key="prog1_charge",
        name="Prog1 Charge",
        value="Allow Grid",
        unit="",
    )


def test_decode_rejects_unknown_option():
    """Reject a decoded value that is not in the options map."""
    definition = RegisterDefinition(
        key="prog1_charge",
        name="Prog1 Charge",
        address=172,
        function="holding",
        data_type="uint16",
        scale=1,
        unit="",
        access="read",
        options={
            0: "No Grid or Gen",
            1: "Allow Grid",
        },
    )

    with pytest.raises(DecodeError, match="unknown option 2 for prog1_charge"):
        decode_register(definition, values=(2,))


def test_decode_rejects_options_on_non_integer_value():
    """Reject options when the decoded raw value is not an integer."""
    definition = RegisterDefinition(
        key="status",
        name="Status",
        address=10,
        function="holding",
        data_type="float32",
        scale=1,
        unit="",
        access="read",
        count=2,
        word_order="big",
        options={0: "off", 1: "on"},
    )

    with pytest.raises(
        DecodeError,
        match="options require an integer value for status",
    ):
        decode_register(definition, values=(16256, 0))


def test_decode_applies_binary():
    """Map a nonzero masked register to True."""
    definition = RegisterDefinition(
        key="grid_charge_enabled",
        name="Grid Charge Enabled",
        address=232,
        function="holding",
        data_type="uint16",
        scale=1,
        unit="",
        access="write",
        bitmask=0x1,
        binary=True,
    )

    measurement = decode_register(definition, values=(0x5,))

    assert measurement == Measurement(
        key="grid_charge_enabled",
        name="Grid Charge Enabled",
        value=True,
        unit="",
    )


def test_decode_binary_zero_is_false():
    """Map a zero masked register to False."""
    definition = RegisterDefinition(
        key="grid_charge_enabled",
        name="Grid Charge Enabled",
        address=232,
        function="holding",
        data_type="uint16",
        scale=1,
        unit="",
        access="write",
        bitmask=0x1,
        binary=True,
    )

    measurement = decode_register(definition, values=(0x4,))

    assert measurement.value is False


def test_decode_rejects_binary_on_non_integer_value():
    """Reject binary when the decoded raw value is not an integer."""
    definition = RegisterDefinition(
        key="status",
        name="Status",
        address=10,
        function="holding",
        data_type="float32",
        scale=1,
        unit="",
        access="read",
        count=2,
        word_order="big",
        binary=True,
    )

    with pytest.raises(
        DecodeError,
        match="binary requires an integer value for status",
    ):
        decode_register(definition, values=(16256, 0))


def test_decode_math_applies_weighted_sum():
    """Combine source engineering values with per-source factors."""
    from rainbow.decode import decode_math
    from rainbow.profiles import MathSource

    definition = RegisterDefinition(
        key="essential_power",
        name="Essential Power",
        data_type="math",
        unit="W",
        access="read",
        sources=(
            MathSource(key="inverter_power", factor=1),
            MathSource(key="grid_power", factor=1),
            MathSource(key="aux_power", factor=-1),
        ),
    )

    measurement = decode_math(
        definition,
        {"inverter_power": 1000, "grid_power": 200, "aux_power": 50},
    )

    assert measurement == Measurement(
        key="essential_power",
        name="Essential Power",
        value=1150,
        unit="W",
    )


def test_decode_math_applies_no_negative():
    """Clamp negative math results to zero when requested."""
    from rainbow.decode import decode_math
    from rainbow.profiles import MathSource

    definition = RegisterDefinition(
        key="non_essential_power",
        name="Non Essential Power",
        data_type="math",
        unit="W",
        access="read",
        sources=(
            MathSource(key="grid_ct_power", factor=1),
            MathSource(key="grid_ld_power", factor=-1),
        ),
        no_negative=True,
    )

    measurement = decode_math(
        definition,
        {"grid_ct_power": 100, "grid_ld_power": 250},
    )

    assert measurement.value == 0


def test_decode_math_applies_absolute():
    """Take the absolute value of a math result when requested."""
    from rainbow.decode import decode_math
    from rainbow.profiles import MathSource

    definition = RegisterDefinition(
        key="essential_2_power",
        name="Essential 2 Power",
        data_type="math",
        unit="W",
        access="read",
        sources=(
            MathSource(key="inverter_power", factor=1),
            MathSource(key="grid_power", factor=1),
            MathSource(key="aux_power", factor=-1),
        ),
        absolute=True,
    )

    measurement = decode_math(
        definition,
        {"inverter_power": 100, "grid_power": 50, "aux_power": 200},
    )

    assert measurement.value == 50


def test_decode_math_rejects_missing_source_value():
    """Reject math decode when a required source value is absent."""
    from rainbow.decode import decode_math
    from rainbow.profiles import MathSource

    definition = RegisterDefinition(
        key="essential_power",
        name="Essential Power",
        data_type="math",
        unit="W",
        access="read",
        sources=(MathSource(key="inverter_power", factor=1),),
    )

    with pytest.raises(
        DecodeError,
        match="missing source value inverter_power for essential_power",
    ):
        decode_math(definition, {})


def test_decode_math_rejects_non_numeric_source_value():
    """Reject math decode when a source value is not numeric."""
    from rainbow.decode import decode_math
    from rainbow.profiles import MathSource

    definition = RegisterDefinition(
        key="essential_power",
        name="Essential Power",
        data_type="math",
        unit="W",
        access="read",
        sources=(MathSource(key="serial", factor=1),),
    )

    with pytest.raises(
        DecodeError,
        match="non-numeric source value serial for essential_power",
    ):
        decode_math(definition, {"serial": "ABC"})


def test_decode_math_rejects_missing_sources():
    """Reject math decode when the definition has no sources."""
    from rainbow.decode import decode_math

    definition = RegisterDefinition(
        key="essential_power",
        name="Essential Power",
        data_type="math",
        unit="W",
        access="read",
    )

    with pytest.raises(
        DecodeError,
        match="math register essential_power has no sources",
    ):
        decode_math(definition, {})


def test_decode_register_rejects_math_definition():
    """Reject decoding a math register from raw Modbus words."""
    from rainbow.profiles import MathSource

    definition = RegisterDefinition(
        key="essential_power",
        name="Essential Power",
        data_type="math",
        unit="W",
        access="read",
        sources=(MathSource(key="inverter_power", factor=1),),
    )

    with pytest.raises(
        DecodeError,
        match="math register essential_power cannot be decoded from raw words",
    ):
        decode_register(definition, values=(1,))


def test_decode_int16_signed_value():
    """Decode a signed 16-bit register as two's complement."""
    definition = RegisterDefinition(
        key="battery_power",
        name="Battery Power",
        address=190,
        function="holding",
        data_type="int16",
        scale=1,
        unit="W",
        access="read",
    )

    measurement = decode_register(definition, values=(0xFFFF,))

    assert measurement == Measurement(
        key="battery_power",
        name="Battery Power",
        value=-1,
        unit="W",
    )


def test_decode_int16_max_positive_value():
    """Decode the largest positive signed 16-bit value."""
    definition = RegisterDefinition(
        key="battery_power",
        name="Battery Power",
        address=190,
        function="holding",
        data_type="int16",
        scale=1,
        unit="W",
        access="read",
    )

    measurement = decode_register(definition, values=(0x7FFF,))

    assert measurement.value == 32767


def test_decode_int16_min_negative_value():
    """Decode the most negative signed 16-bit value."""
    definition = RegisterDefinition(
        key="battery_power",
        name="Battery Power",
        address=190,
        function="holding",
        data_type="int16",
        scale=1,
        unit="W",
        access="read",
    )

    measurement = decode_register(definition, values=(0x8000,))

    assert measurement.value == -32768


def test_decode_string_register():
    """Decode multi-register ASCII string values (two chars per word)."""
    definition = RegisterDefinition(
        key="serial",
        name="Serial",
        address=3,
        function="holding",
        data_type="string",
        scale=1,
        unit="",
        access="read",
        count=5,
    )

    measurement = decode_register(
        definition,
        values=(0x3132, 0x3334, 0x3536, 0x3738, 0x3930),
    )

    assert measurement == Measurement(
        key="serial",
        name="Serial",
        value="1234567890",
        unit="",
    )


def test_decode_string_strips_trailing_null_padding():
    """Drop null bytes used to pad short serial numbers."""
    definition = RegisterDefinition(
        key="serial",
        name="Serial",
        address=3,
        function="holding",
        data_type="string",
        scale=1,
        unit="",
        access="read",
        count=5,
    )

    measurement = decode_register(
        definition,
        values=(0x4142, 0x4344, 0x0000, 0x0000, 0x0000),
    )

    assert measurement == Measurement(
        key="serial",
        name="Serial",
        value="ABCD",
        unit="",
    )


def test_decode_applies_bitmask():
    """Keep only the selected bits before scaling."""
    definition = RegisterDefinition(
        key="prog1_charge",
        name="Prog1 Charge",
        address=274,
        function="holding",
        data_type="uint16",
        scale=1,
        unit="",
        access="read",
        bitmask=0x03,
    )

    measurement = decode_register(definition, values=(0x1D,))

    assert measurement == Measurement(
        key="prog1_charge",
        name="Prog1 Charge",
        value=1,
        unit="",
    )


def test_decode_applies_bitmask_before_int16_sign():
    """Apply bitmask before interpreting a signed 16-bit value."""
    definition = RegisterDefinition(
        key="signed_flags",
        name="Signed Flags",
        address=100,
        function="holding",
        data_type="int16",
        scale=1,
        unit="",
        access="read",
        bitmask=0x00FF,
    )

    measurement = decode_register(definition, values=(0xFFFF,))

    assert measurement.value == 255


def test_decode_register_rejects_wrong_value_count():
    """Reject raw values that do not match the register count."""
    definition = RegisterDefinition(
        key="battery_soc",
        name="Battery SOC",
        address=184,
        function="holding",
        data_type="uint16",
        scale=1,
        unit="%",
        access="read",
    )

    with pytest.raises(
        DecodeError,
        match="Expected 1 register values for battery_soc, received 2",
    ):
        decode_register(definition, values=(85, 86))


def test_decode_uint32_big_endian():
    """Combine two registers into an unsigned 32-bit value, high word first."""
    definition = RegisterDefinition(
        key="total_pv_energy",
        name="Total PV Energy",
        address=96,
        function="holding",
        data_type="uint32",
        scale=1,
        unit="kWh",
        access="read",
        count=2,
        word_order="big",
    )

    measurement = decode_register(definition, values=(1, 2))

    assert measurement == Measurement(
        key="total_pv_energy",
        name="Total PV Energy",
        value=65538,
        unit="kWh",
    )


def test_decode_uint32_little_endian():
    """Combine two registers into an unsigned 32-bit value, low word first."""
    definition = RegisterDefinition(
        key="total_pv_energy",
        name="Total PV Energy",
        address=96,
        function="holding",
        data_type="uint32",
        scale=1,
        unit="kWh",
        access="read",
        count=2,
        word_order="little",
    )

    measurement = decode_register(definition, values=(1, 2))

    assert measurement == Measurement(
        key="total_pv_energy",
        name="Total PV Energy",
        value=131073,
        unit="kWh",
    )


def test_decode_int32_signed_value():
    """Decode a signed 32-bit value from two registers."""
    definition = RegisterDefinition(
        key="day_active_energy",
        name="Day Active Energy",
        address=60,
        function="holding",
        data_type="int32",
        scale=1,
        unit="kWh",
        access="read",
        count=2,
        word_order="big",
    )

    measurement = decode_register(definition, values=(0xFFFF, 0xFFFF))

    assert measurement == Measurement(
        key="day_active_energy",
        name="Day Active Energy",
        value=-1,
        unit="kWh",
    )


def test_decode_uint32_applies_scale():
    """Apply scale after combining a 32-bit register pair."""
    definition = RegisterDefinition(
        key="total_pv_energy",
        name="Total PV Energy",
        address=96,
        function="holding",
        data_type="uint32",
        scale=0.1,
        unit="kWh",
        access="read",
        count=2,
        word_order="big",
    )

    measurement = decode_register(definition, values=(1, 2))

    assert measurement.key == "total_pv_energy"
    assert measurement.name == "Total PV Energy"
    assert measurement.value == pytest.approx(6553.8)
    assert measurement.unit == "kWh"


def test_decode_float32_big_endian():
    """Decode an IEEE 754 float32 from two registers, high word first."""
    definition = RegisterDefinition(
        key="example_float",
        name="Example Float",
        address=200,
        function="holding",
        data_type="float32",
        scale=1,
        unit="",
        access="read",
        count=2,
        word_order="big",
    )

    measurement = decode_register(definition, values=(0x3F80, 0x0000))

    assert measurement.key == "example_float"
    assert measurement.name == "Example Float"
    assert measurement.value == pytest.approx(1.0)
    assert measurement.unit == ""


def test_decode_float32_little_endian():
    """Decode an IEEE 754 float32 from two registers, low word first."""
    definition = RegisterDefinition(
        key="example_float",
        name="Example Float",
        address=200,
        function="holding",
        data_type="float32",
        scale=1,
        unit="",
        access="read",
        count=2,
        word_order="little",
    )

    measurement = decode_register(definition, values=(0x0000, 0x3F80))

    assert measurement.value == pytest.approx(1.0)


def test_decode_float32_rejects_nan():
    """Reject IEEE 754 float32 NaN rather than returning it as a measurement."""
    definition = RegisterDefinition(
        key="example_float",
        name="Example Float",
        address=200,
        function="holding",
        data_type="float32",
        scale=1,
        unit="",
        access="read",
        count=2,
        word_order="big",
    )

    with pytest.raises(DecodeError, match="non-finite float32"):
        decode_register(definition, values=(0x7FC0, 0x0000))


def test_decode_rejects_unknown_data_type():
    """Reject data types that are not explicitly supported."""
    definition = RegisterDefinition(
        key="custom",
        name="Custom",
        address=0,
        function="holding",
        data_type="bool",
        scale=1,
        unit="",
        access="read",
    )

    with pytest.raises(DecodeError, match="unsupported data_type: bool"):
        decode_register(definition, values=(1,))
