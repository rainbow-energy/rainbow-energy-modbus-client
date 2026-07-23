"""Test the polling client for point-in-time measurement reads."""

import pytest

from factories import make_profile, make_register
from rainbow_energy_client.client import Client, ClientError
from rainbow_energy_client.decode import DecodeError
from rainbow_energy_client.reader import RegisterData, RegisterReadError


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


def test_client_run_polls_repeatedly_with_interval():
    """Yield successive polls and sleep between them for the given interval."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))
    reader = FakeReader(values=(85,))
    client = Client(reader, profile, keys=("battery_soc",))
    sleeps: list[float] = []

    readings = list(client.run(interval=2.0, iterations=3, sleep=sleeps.append))

    assert len(readings) == 3
    assert all(reading[0].value == 85 for reading in readings)
    assert sleeps == [2.0, 2.0]


def test_client_run_continues_after_poll_error():
    """Skip failed polls, report them, and keep iterating on the interval."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))

    class FlakyReader(FakeReader):
        def __init__(self) -> None:
            super().__init__(values=(85,))
            self.calls = 0

        def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
            self.calls += 1
            if self.calls == 2:
                raise RegisterReadError("transient Modbus failure")
            return super().read_holding_registers(start_address, count)

    client = Client(FlakyReader(), profile, keys=("battery_soc",))
    errors: list[ClientError] = []
    sleeps: list[float] = []

    readings = list(
        client.run(
            interval=1.0,
            iterations=3,
            sleep=sleeps.append,
            on_error=errors.append,
        )
    )

    assert len(readings) == 2
    assert all(reading[0].value == 85 for reading in readings)
    assert len(errors) == 1
    assert isinstance(errors[0], ClientError)
    assert isinstance(errors[0].__cause__, RegisterReadError)
    assert sleeps == [1.0, 1.0]


def test_client_run_reports_skipped_batch_via_on_error():
    """Report a skipped Modbus batch and still yield successful measurements."""
    profile = make_profile(
        registers=(
            make_register(key="grid_power", address=100, data_type="int16"),
            make_register(key="load_power", address=200, data_type="int16"),
        )
    )
    failed = RegisterReadError("gateway rejected address 200")

    class PartialReader(FakeReader):
        def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
            self.request = ("holding", start_address, count)
            if start_address == 200:
                raise failed
            return RegisterData(
                device_id=1,
                start_address=start_address,
                values=(10,),
            )

    client = Client(PartialReader(), profile, keys=("grid_power", "load_power"))
    errors: list[ClientError] = []

    readings = list(
        client.run(
            interval=1.0,
            iterations=1,
            sleep=lambda _: None,
            on_error=errors.append,
        )
    )

    assert len(readings) == 1
    assert [item.key for item in readings[0]] == ["grid_power"]
    assert len(errors) == 1
    assert isinstance(errors[0], ClientError)
    assert errors[0].__cause__ is failed


def test_client_run_reports_decode_error_via_on_error():
    """Report a leaf decode failure and still yield successful measurements."""
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
    reader = FakeReader(values=(0, 10))
    client = Client(reader, profile, keys=("sd_status", "grid_power"))
    errors: list[ClientError] = []

    readings = list(
        client.run(
            interval=1.0,
            iterations=1,
            sleep=lambda _: None,
            on_error=errors.append,
        )
    )

    assert len(readings) == 1
    assert [item.key for item in readings[0]] == ["grid_power"]
    assert len(errors) == 1
    assert isinstance(errors[0], ClientError)
    assert isinstance(errors[0].__cause__, DecodeError)


def test_client_run_with_no_iteration_limit():
    """Poll until the consumer stops when iterations is None."""
    profile = make_profile(registers=(make_register(key="battery_soc", address=184),))
    reader = FakeReader(values=(85,))
    client = Client(reader, profile, keys=("battery_soc",))
    sleeps: list[float] = []

    readings: list[tuple] = []
    for reading in client.run(interval=1.0, iterations=None, sleep=sleeps.append):
        readings.append(reading)
        if len(readings) == 3:
            break

    assert len(readings) == 3
    assert all(reading[0].value == 85 for reading in readings)
    assert sleeps == [1.0, 1.0]
