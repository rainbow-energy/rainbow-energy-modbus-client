"""Test fetching and decoding profile measurements."""

import pytest

from factories import make_profile, make_register
from rainbow_energy_client.decode import DecodeError
from rainbow_energy_client.device import (
    _decode_leaf,
    read_measurement,
    read_measurements,
    write_measurements,
)
from rainbow_energy_client.encode import EncodeError
from rainbow_energy_client.profiles import MathSource
from rainbow_energy_client.reader import RegisterData, RegisterReadError


class FakeReader:
    """Return canned register values without serial hardware."""

    def __init__(
        self,
        values: tuple[int, ...] = (),
        *,
        responses: dict[int, tuple[int, ...]] | None = None,
        errors: dict[int, Exception] | None = None,
    ) -> None:
        """Store default or per-address values for the next reads."""
        self.values = values
        self.responses = responses or {}
        self.errors = errors or {}
        self.request: tuple[str, int, int] | None = None
        self.requests: list[tuple[str, int, int]] = []
        self.writes: list[tuple[int, tuple[int, ...]]] = []

    def _values_for(self, start_address: int) -> tuple[int, ...]:
        """Return canned values for one register address."""
        return self.responses.get(start_address, self.values)

    def _read(self, function: str, start_address: int, count: int) -> RegisterData:
        """Record a request; raise or return canned values for the address."""
        self.request = (function, start_address, count)
        self.requests.append(self.request)
        if start_address in self.errors:
            raise self.errors[start_address]
        return RegisterData(
            device_id=1,
            start_address=start_address,
            values=self._values_for(start_address),
        )

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Record a holding-register request and return canned values."""
        return self._read("holding", start_address, count)

    def read_input_registers(self, start_address: int, count: int) -> RegisterData:
        """Record an input-register request and return canned values."""
        return self._read("input", start_address, count)

    def write_holding_registers(
        self, start_address: int, values: tuple[int, ...] | list[int]
    ) -> None:
        """Record a holding-register write."""
        self.writes.append((start_address, tuple(values)))


# ---------------------------------------------------------------------------
# Single-key reads
# ---------------------------------------------------------------------------


def test_read_measurement_fetches_and_decodes_holding_register():
    """Look up a profile key, read its registers, and decode a measurement."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))
    reader = FakeReader(values=(85,))

    measurement = read_measurement(reader, profile, "battery_soc")

    assert reader.request == ("holding", 184, 1)
    assert measurement.value == 85


def test_read_measurement_fetches_and_decodes_input_register():
    """Read and decode an input-register measurement from the profile."""
    profile = make_profile(
        registers=(
            make_register(key="grid_voltage", address=150, function="input", scale=0.1),
        )
    )
    reader = FakeReader(values=(2300,))

    measurement = read_measurement(reader, profile, "grid_voltage")

    assert reader.request == ("input", 150, 1)
    assert measurement.value == pytest.approx(230.0)


def test_read_measurement_rejects_unknown_key():
    """Reject a measurement key that is not in the profile."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))

    with pytest.raises(KeyError, match="unknown register key: grid_power"):
        read_measurement(FakeReader(values=(85,)), profile, "grid_power")


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def test_read_measurements_batches_adjacent_registers():
    """Merge adjacent registers into one Modbus read, preserve key order."""
    profile = make_profile(
        registers=(
            make_register(key="battery_soc", address=184),
            make_register(key="battery_voltage", address=183, scale=0.1),
        )
    )
    reader = FakeReader(responses={183: (523, 85)})

    measurements = read_measurements(
        reader,
        profile,
        ("battery_soc", "battery_voltage"),
    )

    assert reader.requests == [("holding", 183, 2)]
    assert measurements[0].value == 85
    assert measurements[1].value == pytest.approx(52.3)


def test_read_measurements_batches_registers_within_gap():
    """Merge same-function registers when the unused gap is small."""
    profile = make_profile(
        registers=(
            make_register(key="grid_power", address=100, data_type="int16"),
            make_register(key="load_power", address=110, data_type="int16"),
        )
    )
    reader = FakeReader(responses={100: (10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 20)})

    measurements = read_measurements(
        reader,
        profile,
        ("grid_power", "load_power"),
    )

    assert reader.requests == [("holding", 100, 11)]
    assert [item.value for item in measurements] == [10, 20]


def test_read_measurements_keeps_large_gaps_separate():
    """Do not merge registers when the unused gap exceeds the batch limit."""
    profile = make_profile(
        registers=(
            make_register(key="grid_power", address=100, data_type="int16"),
            make_register(key="load_power", address=118, data_type="int16"),
        )
    )
    reader = FakeReader(responses={100: (10,), 118: (20,)})

    measurements = read_measurements(
        reader,
        profile,
        ("grid_power", "load_power"),
    )

    assert reader.requests == [("holding", 100, 1), ("holding", 118, 1)]
    assert [item.value for item in measurements] == [10, 20]


def test_read_measurements_skips_failed_batch():
    """Skip a failed Modbus batch and still return other measurements."""
    profile = make_profile(
        registers=(
            make_register(key="grid_power", address=100, data_type="int16"),
            make_register(key="load_power", address=200, data_type="int16"),
        )
    )
    reader = FakeReader(
        responses={100: (10,)},
        errors={200: RegisterReadError("gateway rejected address 200")},
    )

    measurements = read_measurements(
        reader,
        profile,
        ("grid_power", "load_power"),
    )

    assert reader.requests == [("holding", 100, 1), ("holding", 200, 1)]
    assert [item.key for item in measurements] == ["grid_power"]
    assert measurements[0].value == 10


def test_read_measurements_reports_skipped_batch_via_on_error():
    """Call on_error for a failed batch while still returning other measurements."""
    profile = make_profile(
        registers=(
            make_register(key="grid_power", address=100, data_type="int16"),
            make_register(key="load_power", address=200, data_type="int16"),
        )
    )
    failed = RegisterReadError("gateway rejected address 200")
    reader = FakeReader(responses={100: (10,)}, errors={200: failed})
    errors: list[RegisterReadError] = []

    measurements = read_measurements(
        reader,
        profile,
        ("grid_power", "load_power"),
        on_error=errors.append,
    )

    assert errors == [failed]
    assert [item.key for item in measurements] == ["grid_power"]


def test_read_measurements_skips_decode_error():
    """Skip a leaf that fails to decode and still return other measurements."""
    profile = make_profile(
        registers=(
            make_register(
                key="sd_status",
                address=100,
                options={1000: "fault", 2000: "ok"},
            ),
            make_register(key="grid_power", address=101, data_type="int16"),
        )
    )
    reader = FakeReader(responses={100: (0, 10)})
    errors: list[Exception] = []

    measurements = read_measurements(
        reader,
        profile,
        ("sd_status", "grid_power"),
        on_error=errors.append,
    )

    assert [item.key for item in measurements] == ["grid_power"]
    assert measurements[0].value == 10
    assert len(errors) == 1
    assert isinstance(errors[0], DecodeError)
    assert "unknown option 0" in str(errors[0])


# ---------------------------------------------------------------------------
# Math expansion
# ---------------------------------------------------------------------------


def test_read_measurements_expands_math_sources():
    """Read leaf sources for a math key and return the combined value."""
    profile = make_profile(
        registers=(
            make_register(key="aux_power", address=166, data_type="int16"),
            make_register(key="grid_power", address=169, data_type="int16"),
            make_register(key="inverter_power", address=175, data_type="int16"),
            make_register(
                key="essential_power",
                data_type="math",
                sources=(
                    MathSource(key="inverter_power", factor=1),
                    MathSource(key="grid_power", factor=1),
                    MathSource(key="aux_power", factor=-1),
                ),
            ),
        )
    )
    reader = FakeReader(responses={166: (50, 0, 0, 200, 0, 0, 0, 0, 0, 1000)})

    measurements = read_measurements(reader, profile, ("essential_power",))

    assert reader.requests == [("holding", 166, 10)]
    assert measurements[0].value == 1150


def test_read_measurements_returns_math_and_source_without_reread():
    """Return both math and source keys while reading each leaf once."""
    profile = make_profile(
        registers=(
            make_register(key="aux_power", address=166, data_type="int16"),
            make_register(key="grid_power", address=169, data_type="int16"),
            make_register(key="inverter_power", address=175, data_type="int16"),
            make_register(
                key="essential_power",
                data_type="math",
                sources=(
                    MathSource(key="inverter_power", factor=1),
                    MathSource(key="grid_power", factor=1),
                    MathSource(key="aux_power", factor=-1),
                ),
            ),
        )
    )
    reader = FakeReader(responses={166: (50, 0, 0, 200, 0, 0, 0, 0, 0, 1000)})

    measurements = read_measurements(
        reader,
        profile,
        ("essential_power", "inverter_power"),
    )

    assert reader.requests == [("holding", 166, 10)]
    assert [item.value for item in measurements] == [1150, 1000]


# ---------------------------------------------------------------------------
# Leaf decode helpers
# ---------------------------------------------------------------------------


def test_decode_leaf_rejects_uncovered_register():
    """Reject leaf decode when no Modbus batch covers the register."""
    definition = make_register(key="battery_soc", address=184)

    with pytest.raises(LookupError, match="no batch covered register battery_soc"):
        _decode_leaf(definition, {})


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def test_write_measurements_encodes_and_writes_uint16():
    """Encode a writable uint16 value and write its holding register."""
    profile = make_profile(
        registers=(
            make_register(
                key="battery_shutdown_capacity",
                address=217,
                access="write",
                unit="%",
            ),
        )
    )
    reader = FakeReader()

    write_measurements(reader, profile, {"battery_shutdown_capacity": 20})

    assert reader.writes == [(217, (20,))]


def test_write_measurements_rejects_read_only_key():
    """Reject writes to registers marked access read."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))

    with pytest.raises(EncodeError, match="not writable"):
        write_measurements(FakeReader(), profile, {"battery_soc": 50})


def test_write_measurements_options_label():
    """Encode an options label and write the raw integer."""
    profile = make_profile(
        registers=(
            make_register(
                key="aux_port_usage",
                address=235,
                access="write",
                options={0: "Disable", 1: "Smartload", 2: "Generator"},
            ),
        )
    )
    reader = FakeReader()

    write_measurements(reader, profile, {"aux_port_usage": "Smartload"})

    assert reader.writes == [(235, (1,))]


def test_write_measurements_binary_without_bitmask():
    """Write a binary register as 0 or 1."""
    profile = make_profile(
        registers=(
            make_register(
                key="inverter_enabled",
                address=43,
                access="write",
                binary=True,
            ),
        )
    )
    reader = FakeReader()

    write_measurements(reader, profile, {"inverter_enabled": True})

    assert reader.writes == [(43, (1,))]


def test_write_measurements_bitmask_read_modify_write():
    """Merge bitmasked writes into the current holding register word."""
    profile = make_profile(
        registers=(
            make_register(
                key="grid_charge_enabled",
                address=232,
                access="write",
                binary=True,
                bitmask=0x1,
            ),
        )
    )
    reader = FakeReader(responses={232: (0x00F0,)})

    write_measurements(reader, profile, {"grid_charge_enabled": True})

    assert reader.requests == [("holding", 232, 1)]
    assert reader.writes == [(232, (0x00F1,))]


def test_write_measurements_time():
    """Encode a time string and write one holding register."""
    profile = make_profile(
        registers=(
            make_register(
                key="prog1_time",
                address=250,
                data_type="time",
                access="write",
            ),
        )
    )
    reader = FakeReader()

    write_measurements(reader, profile, {"prog1_time": "1:30"})

    assert reader.writes == [(250, (130,))]


def test_write_measurements_datetime():
    """Encode a datetime string and write three holding registers."""
    profile = make_profile(
        registers=(
            make_register(
                key="date_time",
                address=22,
                data_type="datetime",
                count=3,
                access="write",
            ),
        )
    )
    reader = FakeReader()

    write_measurements(reader, profile, {"date_time": "2024-07-23 14:05:09"})

    assert reader.writes == [
        (22, ((24 << 8) | 7, (23 << 8) | 14, (5 << 8) | 9)),
    ]


def test_write_measurements_rejects_empty_values():
    """Reject an empty write mapping before touching the transport."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))

    with pytest.raises(ValueError, match="values must not be empty"):
        write_measurements(FakeReader(), profile, {})


def test_write_measurements_rejects_math_register():
    """Reject writes to math registers."""
    profile = make_profile(
        registers=(
            make_register(key="a", address=1),
            make_register(
                key="total",
                data_type="math",
                access="write",
                address=None,
                function=None,
                scale=None,
                sources=(MathSource(key="a", factor=1.0),),
            ),
        )
    )

    with pytest.raises(EncodeError, match="math register"):
        write_measurements(FakeReader(), profile, {"total": 1})


def test_write_measurements_rejects_input_function():
    """Reject writes that target input registers."""
    profile = make_profile(
        registers=(
            make_register(
                key="setting",
                address=10,
                function="input",
                access="write",
            ),
        )
    )

    with pytest.raises(EncodeError, match="holding registers"):
        write_measurements(FakeReader(), profile, {"setting": 1})


def test_write_measurements_rejects_multiword_bitmask(monkeypatch):
    """Reject bitmasked writes that encode to more than one register."""
    profile = make_profile(
        registers=(
            make_register(
                key="flag",
                address=232,
                access="write",
                binary=True,
                bitmask=0x1,
            ),
        )
    )

    monkeypatch.setattr(
        "rainbow_energy_client.device.encode_register",
        lambda definition, value: (1, 2),
    )

    with pytest.raises(EncodeError, match="single register"):
        write_measurements(FakeReader(responses={232: (0,)}), profile, {"flag": True})
