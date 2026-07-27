"""Poll named measurements from an inverter using a device profile."""

from collections.abc import Callable, Iterator, Sequence
from time import sleep as default_sleep

from rainbow_energy_modbus_client.decode import DecodeError, Measurement
from rainbow_energy_modbus_client.device import BatchError, RegisterReader, read_measurements
from rainbow_energy_modbus_client.profiles import DeviceProfile
from rainbow_energy_modbus_client.reader import RegisterReadError


class ClientError(RuntimeError):
    """Raised when a client poll cannot return measurements."""


class Client:
    """Read configured measurements from an inverter on demand."""

    def __init__(
        self,
        reader: RegisterReader,
        profile: DeviceProfile,
        keys: Sequence[str],
    ) -> None:
        """Bind a Modbus reader, profile, and the keys to poll."""
        keys = tuple(keys)
        if not keys:
            raise ValueError("keys must not be empty")
        self._reader = reader
        self._profile = profile
        self._keys = keys

    def poll(
        self,
        *,
        on_error: Callable[[ClientError], None] | None = None,
    ) -> tuple[Measurement, ...]:
        """Fetch and decode one reading for each configured key.

        When a Modbus batch or leaf decode fails but other measurements
        succeed, report the failure via *on_error* and still return the
        successful readings.
        """
        def report_partial_error(error: BatchError) -> None:
            assert on_error is not None
            client_error = ClientError("failed to read measurement")
            client_error.__cause__ = error
            on_error(client_error)

        try:
            return read_measurements(
                self._reader,
                self._profile,
                self._keys,
                on_error=report_partial_error if on_error is not None else None,
            )
        except (RegisterReadError, DecodeError, KeyError, LookupError) as error:
            raise ClientError("failed to poll measurements") from error

    def run(
        self,
        interval: float,
        *,
        iterations: int | None = None,
        sleep: Callable[[float], None] = default_sleep,
        on_error: Callable[[ClientError], None] | None = None,
    ) -> Iterator[tuple[Measurement, ...]]:
        """Yield successive polls, sleeping between them by interval seconds.

        When iterations is None, poll until the consumer stops iterating.
        Poll failures raise ClientError from poll(); run catches them, optionally
        reports via on_error, skips yielding that cycle, and continues.
        Partial batch or decode failures are reported via on_error without
        skipping the successful measurements from that cycle.
        """
        completed = 0
        while True:
            try:
                yield self.poll(on_error=on_error)
            except ClientError as error:
                if on_error is not None:
                    on_error(error)
            completed += 1
            if iterations is not None and completed >= iterations:
                break
            sleep(interval)
