"""Read raw Modbus registers through a USB-RS485 adapter."""

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException


class ModbusResponse(Protocol):
    """Describe the Modbus response behavior used by the reader."""

    registers: list[int]

    def isError(self) -> bool:
        """Return whether the response represents a Modbus error."""
        ...


class ModbusClient(Protocol):
    """Describe the Modbus client behavior used by the reader."""

    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> ModbusResponse:
        """Read holding registers from one Modbus device."""
        ...

    def read_input_registers(
        self, address: int, *, count: int, device_id: int
    ) -> ModbusResponse:
        """Read input registers from one Modbus device."""
        ...

    def close(self) -> None:
        """Close the Modbus transport."""
        ...


@dataclass(frozen=True, slots=True)
class RegisterData:
    """Contain raw register values returned by one read."""

    device_id: int
    start_address: int
    values: tuple[int, ...]


class RegisterReadError(RuntimeError):
    """Raised when the inverter rejects a register read."""


class Rs485Reader:
    """Read holding and input registers from a Modbus RTU device."""

    def __init__(
        self,
        port: str,
        device_id: int = 1,
        client: ModbusClient | None = None,
    ) -> None:
        """Configure a reader for one serial port and Modbus device."""
        if not port.strip():
            raise ValueError("port must not be empty")
        if not 1 <= device_id <= 247:
            raise ValueError("device_id must be between 1 and 247")
        self._device_id = device_id
        self._client = client or ModbusSerialClient(port=port, baudrate=9600)

    def __enter__(self) -> Self:
        """Return the reader for context-managed use."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the Modbus transport when leaving a context."""
        self.close()

    def close(self) -> None:
        """Close the underlying Modbus transport."""
        self._client.close()

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Read and return a contiguous range of holding registers."""
        return self._read_registers(
            self._client.read_holding_registers,
            start_address,
            count,
        )

    def read_input_registers(self, start_address: int, count: int) -> RegisterData:
        """Read and return a contiguous range of input registers."""
        return self._read_registers(
            self._client.read_input_registers,
            start_address,
            count,
        )

    def _read_registers(
        self,
        read: Callable[..., ModbusResponse],
        start_address: int,
        count: int,
    ) -> RegisterData:
        """Validate and execute one contiguous register read."""
        if not 0 <= start_address <= 65535:
            raise ValueError("start_address must be between 0 and 65535")
        if not 1 <= count <= 125:
            raise ValueError("count must be between 1 and 125")
        if start_address + count - 1 > 65535:
            raise ValueError("register range exceeds address 65535")
        try:
            response = read(
                start_address,
                count=count,
                device_id=self._device_id,
            )
        except ModbusException as error:
            raise RegisterReadError(
                f"Failed to read registers at address {start_address}: {error}"
            ) from error
        if response.isError():
            raise RegisterReadError(
                f"Modbus error reading registers at address {start_address}: {response}"
            )
        values = tuple(response.registers)
        if len(values) != count:
            raise RegisterReadError(
                f"Expected {count} registers, received {len(values)} "
                f"at address {start_address}"
            )
        return RegisterData(
            device_id=self._device_id,
            start_address=start_address,
            values=values,
        )
