"""Test fetching and decoding profile measurements."""

import pytest

from rainbow.decode import Measurement
from rainbow.device import read_measurement, read_measurements
from rainbow.profiles import DeviceProfile, RegisterDefinition
from rainbow.reader import RegisterData


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


def test_read_measurement_fetches_and_decodes_holding_register():
    """Look up a profile key, read its registers, and decode a measurement."""
    profile = DeviceProfile(
        manufacturer="Example Energy",
        model="Example 8K",
        registers=(
            RegisterDefinition(
                key="battery_soc",
                name="Battery SOC",
                address=184,
                function="holding",
                data_type="uint16",
                scale=1,
                unit="%",
                access="read",
            ),
        ),
    )
    reader = FakeReader(values=(85,))

    measurement = read_measurement(reader, profile, "battery_soc")

    assert reader.request == ("holding", 184, 1)
    assert measurement == Measurement(
        key="battery_soc",
        name="Battery SOC",
        value=85,
        unit="%",
    )


def test_read_measurement_rejects_unknown_key():
    """Reject a measurement key that is not in the profile."""
    profile = DeviceProfile(
        manufacturer="Example Energy",
        model="Example 8K",
        registers=(
            RegisterDefinition(
                key="battery_soc",
                name="Battery SOC",
                address=184,
                function="holding",
                data_type="uint16",
                scale=1,
                unit="%",
                access="read",
            ),
        ),
    )

    with pytest.raises(KeyError, match="unknown register key: grid_power"):
        read_measurement(FakeReader(values=(85,)), profile, "grid_power")


def test_read_measurement_fetches_and_decodes_input_register():
    """Read and decode an input-register measurement from the profile."""
    profile = DeviceProfile(
        manufacturer="Example Energy",
        model="Example 8K",
        registers=(
            RegisterDefinition(
                key="grid_voltage",
                name="Grid Voltage",
                address=150,
                function="input",
                data_type="uint16",
                scale=0.1,
                unit="V",
                access="read",
            ),
        ),
    )
    reader = FakeReader(values=(2300,))

    measurement = read_measurement(reader, profile, "grid_voltage")

    assert reader.request == ("input", 150, 1)
    assert measurement.key == "grid_voltage"
    assert measurement.name == "Grid Voltage"
    assert measurement.value == pytest.approx(230.0)
    assert measurement.unit == "V"


def test_read_measurements_fetches_keys_in_order():
    """Read several profile keys and return measurements in request order."""
    profile = DeviceProfile(
        manufacturer="Example Energy",
        model="Example 8K",
        registers=(
            RegisterDefinition(
                key="battery_soc",
                name="Battery SOC",
                address=184,
                function="holding",
                data_type="uint16",
                scale=1,
                unit="%",
                access="read",
            ),
            RegisterDefinition(
                key="battery_voltage",
                name="Battery Voltage",
                address=183,
                function="holding",
                data_type="uint16",
                scale=0.1,
                unit="V",
                access="read",
            ),
        ),
    )
    reader = FakeReader(responses={184: (85,), 183: (523,)})

    measurements = read_measurements(
        reader,
        profile,
        ("battery_soc", "battery_voltage"),
    )

    assert reader.requests == [("holding", 184, 1), ("holding", 183, 1)]
    assert measurements[0] == Measurement(
        key="battery_soc",
        name="Battery SOC",
        value=85,
        unit="%",
    )
    assert measurements[1].key == "battery_voltage"
    assert measurements[1].value == pytest.approx(52.3)

