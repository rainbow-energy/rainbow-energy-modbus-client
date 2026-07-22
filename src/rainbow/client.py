"""Poll named measurements from an inverter using a device profile."""

from collections.abc import Callable, Iterator, Sequence
from time import sleep as default_sleep

from rainbow.decode import DecodeError, Measurement
from rainbow.device import RegisterReader, read_measurements
from rainbow.profiles import DeviceProfile
from rainbow.reader import RegisterReadError


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

    def poll(self) -> tuple[Measurement, ...]:
        """Fetch and decode one reading for each configured key."""
        try:
            return read_measurements(self._reader, self._profile, self._keys)
        except (RegisterReadError, DecodeError, KeyError, LookupError) as error:
            raise ClientError("failed to poll measurements") from error

    def run(
        self,
        interval: float,
        *,
        iterations: int,
        sleep: Callable[[float], None] = default_sleep,
    ) -> Iterator[tuple[Measurement, ...]]:
        """Yield successive polls, sleeping between them by interval seconds."""
        for index in range(iterations):
            yield self.poll()
            if index + 1 < iterations:
                sleep(interval)
