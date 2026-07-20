"""Fetch and decode measurements using a device profile."""

from typing import Protocol

from rainbow.decode import Measurement, decode_register
from rainbow.profiles import DeviceProfile
from rainbow.reader import RegisterData


class RegisterReader(Protocol):
    """Describe the reader behavior used to fetch Modbus registers."""

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Read a contiguous range of holding registers."""
        ...

    def read_input_registers(self, start_address: int, count: int) -> RegisterData:
        """Read a contiguous range of input registers."""
        ...


def read_measurement(
    reader: RegisterReader,
    profile: DeviceProfile,
    key: str,
) -> Measurement:
    """Read one named register from the device and decode it."""
    definition = next(
        (register for register in profile.registers if register.key == key),
        None,
    )
    if definition is None:
        raise KeyError(f"unknown register key: {key}")
    if definition.function == "input":
        data = reader.read_input_registers(definition.address, definition.count)
    else:
        data = reader.read_holding_registers(definition.address, definition.count)
    return decode_register(definition, data.values)
