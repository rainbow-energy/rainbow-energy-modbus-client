"""Test the polling client for point-in-time measurement reads."""

import pytest

from factories import make_profile, make_register
from rainbow.client import Client, ClientError
from rainbow.decode import DecodeError
from rainbow.reader import RegisterData, RegisterReadError


class FakeReader:
    """Return canned register values without serial hardware."""

    def __init__(self, values: tuple[int, ...] = ()) -> None:
        """Store values returned by the next read."""
        self.values = values
        self.request: tuple[str, int, int] | None = None

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Record a holding-register request and return canned values."""
        self.request = ("holding", start_address, count)
        return RegisterData(
            device_id=1,
            start_address=start_address,
            values=self.values,
        )

    def read_input_registers(self, start_address: int, count: int) -> RegisterData:
        """Record an input-register request and return canned values."""
        self.request = ("input", start_address, count)
        return RegisterData(
            device_id=1,
            start_address=start_address,
            values=self.values,
        )


def test_client_poll_reads_configured_keys():
    """Poll once and return measurements for the configured keys."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))
    reader = FakeReader(values=(85,))
    client = Client(reader, profile, keys=("battery_soc",))

    measurements = client.poll()

    assert reader.request == ("holding", 184, 1)
    assert len(measurements) == 1
    assert measurements[0].key == "battery_soc"
    assert measurements[0].value == 85


def test_client_rejects_empty_keys():
    """Reject a client configured with no keys to poll."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))
    reader = FakeReader(values=(85,))

    with pytest.raises(ValueError, match="keys must not be empty"):
        Client(reader, profile, keys=())


def test_client_poll_rejects_unknown_key():
    """Surface unknown profile keys as ClientError with the cause preserved."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))
    reader = FakeReader(values=(85,))
    client = Client(reader, profile, keys=("missing_key",))

    with pytest.raises(ClientError, match="failed to poll measurements") as raised:
        client.poll()

    assert isinstance(raised.value.__cause__, KeyError)
    assert "missing_key" in str(raised.value.__cause__)


def test_client_poll_wraps_register_read_error():
    """Surface Modbus read failures as ClientError with the cause preserved."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))

    class FailingReader(FakeReader):
        def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
            raise RegisterReadError("Modbus error reading registers at address 184")

    client = Client(FailingReader(), profile, keys=("battery_soc",))

    with pytest.raises(ClientError, match="failed to poll measurements") as raised:
        client.poll()

    assert isinstance(raised.value.__cause__, RegisterReadError)


def test_client_poll_wraps_decode_error():
    """Surface decode failures as ClientError with the cause preserved."""
    profile = make_profile(
        registers=(
            make_register(
                key="prog1_time",
                address=250,
                data_type="time",
                name="Prog1 Time",
            ),
        )
    )
    reader = FakeReader(values=(60,))  # minutes == 60 is invalid
    client = Client(reader, profile, keys=("prog1_time",))

    with pytest.raises(ClientError, match="failed to poll measurements") as raised:
        client.poll()

    assert isinstance(raised.value.__cause__, DecodeError)
