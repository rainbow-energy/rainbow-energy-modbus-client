"""Test fetching and decoding profile measurements."""

import pytest

from rainbow.decode import Measurement
from rainbow.device import read_measurement
from rainbow.profiles import DeviceProfile, RegisterDefinition
from rainbow.reader import RegisterData


class FakeReader:
    """Return canned register values without serial hardware."""

    def __init__(self, values: tuple[int, ...]) -> None:
        """Store the values that the next read should return."""
        self.values = values
        self.request: tuple[int, int] | None = None

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Record the request and return canned register values."""
        self.request = (start_address, count)
        return RegisterData(device_id=1, start_address=start_address, values=self.values)


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

    assert reader.request == (184, 1)
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


def test_read_measurement_rejects_input_registers():
    """Reject input registers until the reader supports them."""
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

    with pytest.raises(
        NotImplementedError,
        match="input registers are not supported: grid_voltage",
    ):
        read_measurement(FakeReader(values=(2300,)), profile, "grid_voltage")


