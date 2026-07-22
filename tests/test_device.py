"""Test fetching and decoding profile measurements."""

import pytest

from factories import make_profile, make_register
from rainbow_energy_client.device import _decode_leaf, read_measurement, read_measurements
from rainbow_energy_client.profiles import MathSource
from rainbow_energy_client.reader import RegisterData


class FakeReader:
    """Return canned register values without serial hardware."""

    def __init__(
        self,
        values: tuple[int, ...] = (),
        *,
        responses: dict[int, tuple[int, ...]] | None = None,
    ) -> None:
        """Store default or per-address values for the next reads."""
        self.values = values
        self.responses = responses or {}
        self.request: tuple[str, int, int] | None = None
        self.requests: list[tuple[str, int, int]] = []

    def _values_for(self, start_address: int) -> tuple[int, ...]:
        """Return canned values for one register address."""
        return self.responses.get(start_address, self.values)

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Record a holding-register request and return canned values."""
        self.request = ("holding", start_address, count)
        self.requests.append(self.request)
        return RegisterData(
            device_id=1,
            start_address=start_address,
            values=self._values_for(start_address),
        )

    def read_input_registers(self, start_address: int, count: int) -> RegisterData:
        """Record an input-register request and return canned values."""
        self.request = ("input", start_address, count)
        self.requests.append(self.request)
        return RegisterData(
            device_id=1,
            start_address=start_address,
            values=self._values_for(start_address),
        )


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
