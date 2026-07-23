"""Test Modbus register reading and transport handling."""

from unittest.mock import MagicMock

import pytest
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse

from rainbow_energy_modbus_client.reader import (
    ModbusReader,
    RegisterData,
    RegisterReadError,
    RegisterWriteError,
)


class FakeModbusResponse:
    """Provide a successful Modbus response for tests."""

    registers = [2301, 42, 875]

    def isError(self) -> bool:
        """Report that the fake response is successful."""
        return False


class FakeModbusClient:
    """Record Modbus requests without serial hardware."""

    def __init__(self) -> None:
        """Initialize request and connection state."""
        self.request: tuple[int, int, int] | None = None
        self.write_request: tuple[int, list[int], int] | None = None
        self.closed = False

    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        """Record and satisfy a holding-register request."""
        self.request = (address, count, device_id)
        return FakeModbusResponse()

    def read_input_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        """Record and satisfy an input-register request."""
        self.request = (address, count, device_id)
        return FakeModbusResponse()

    def write_registers(
        self, address: int, values: list[int], *, device_id: int
    ) -> object:
        """Record and satisfy a holding-register write."""
        self.write_request = (address, list(values), device_id)
        return FakeModbusResponse()

    def close(self) -> None:
        """Record that the fake transport was closed."""
        self.closed = True


class ErrorModbusClient(FakeModbusClient):
    """Return a Modbus exception response."""

    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        """Record and reject a holding-register request."""
        self.request = (address, count, device_id)
        return ExceptionResponse(function_code=3, exception_code=2, device_id=device_id)


class ShortResponse(FakeModbusResponse):
    """Provide fewer registers than requested."""

    registers = [2301, 42]


class ShortResponseModbusClient(FakeModbusClient):
    """Return a short Modbus response."""

    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        """Record a request and return too few registers."""
        self.request = (address, count, device_id)
        return ShortResponse()


class TimeoutModbusClient(FakeModbusClient):
    """Raise a transport timeout for every request."""

    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        """Record a request and raise a timeout."""
        self.request = (address, count, device_id)
        raise ModbusIOException("No response received after retries")


def make_reader(**overrides) -> ModbusReader:
    """Build a ModbusReader with the usual test serial port and device id."""
    values = {
        "port": "/dev/ttyUSB0",
        "device_id": 1,
        "client": FakeModbusClient(),
    }
    values.update(overrides)
    return ModbusReader.serial(**values)


def test_read_holding_registers_returns_structured_data():
    """Return structured data for a successful register read."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    result = reader.read_holding_registers(start_address=100, count=3)

    assert result == RegisterData(
        device_id=1,
        start_address=100,
        values=(2301, 42, 875),
    )
    assert client.request == (100, 3, 1)


def test_read_input_registers_returns_structured_data():
    """Return structured data for a successful input-register read."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    result = reader.read_input_registers(start_address=100, count=3)

    assert result == RegisterData(
        device_id=1,
        start_address=100,
        values=(2301, 42, 875),
    )
    assert client.request == (100, 3, 1)


def test_read_holding_registers_raises_for_modbus_error():
    """Raise an application error for a Modbus exception response."""
    reader = make_reader(client=ErrorModbusClient())

    with pytest.raises(RegisterReadError, match="Modbus error reading registers"):
        reader.read_holding_registers(start_address=100, count=3)


def test_read_holding_registers_raises_for_short_response():
    """Raise an application error when registers are missing."""
    reader = make_reader(client=ShortResponseModbusClient())

    with pytest.raises(RegisterReadError, match="Expected 3 registers, received 2"):
        reader.read_holding_registers(start_address=100, count=3)


def test_read_holding_registers_wraps_transport_error():
    """Preserve transport failures as application error causes."""
    reader = make_reader(client=TimeoutModbusClient())

    with pytest.raises(RegisterReadError, match="Failed to read registers") as error:
        reader.read_holding_registers(start_address=100, count=3)

    assert isinstance(error.value.__cause__, ModbusIOException)


def test_write_holding_registers_sends_values():
    """Write holding-register values through the Modbus client."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    reader.write_holding_registers(start_address=217, values=(20,))

    assert client.write_request == (217, [20], 1)


def test_write_holding_registers_wraps_modbus_exception():
    """Surface transport write failures as RegisterWriteError."""
    client = FakeModbusClient()

    def fail_write(address: int, values: list[int], *, device_id: int) -> object:
        raise ModbusIOException("No response received after retries")

    client.write_registers = fail_write  # type: ignore[method-assign]
    reader = make_reader(client=client)

    with pytest.raises(RegisterWriteError, match="Failed to write registers") as error:
        reader.write_holding_registers(start_address=217, values=(20,))

    assert isinstance(error.value.__cause__, ModbusIOException)


def test_write_holding_registers_rejects_out_of_range_value():
    """Reject register values outside the 16-bit range."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    with pytest.raises(ValueError, match="register values must be between 0 and 65535"):
        reader.write_holding_registers(start_address=217, values=(70000,))

    assert client.write_request is None


def test_write_holding_registers_wraps_exception_response():
    """Surface Modbus exception responses as RegisterWriteError."""
    client = FakeModbusClient()

    def error_write(address: int, values: list[int], *, device_id: int) -> object:
        return ExceptionResponse(function_code=16, exception_code=2, device_id=device_id)

    client.write_registers = error_write  # type: ignore[method-assign]
    reader = make_reader(client=client)

    with pytest.raises(RegisterWriteError, match="Modbus error writing registers"):
        reader.write_holding_registers(start_address=217, values=(20,))


def test_read_holding_registers_rejects_zero_count():
    """Reject an empty register range before transport access."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    with pytest.raises(ValueError, match="count must be between 1 and 125"):
        reader.read_holding_registers(start_address=100, count=0)

    assert client.request is None


def test_read_holding_registers_rejects_count_above_modbus_limit():
    """Reject reads above the Modbus register-count limit."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    with pytest.raises(ValueError, match="count must be between 1 and 125"):
        reader.read_holding_registers(start_address=100, count=126)

    assert client.request is None


def test_read_holding_registers_rejects_negative_address():
    """Reject negative Modbus register addresses."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    with pytest.raises(ValueError, match="start_address must be between 0 and 65535"):
        reader.read_holding_registers(start_address=-1, count=3)

    assert client.request is None


def test_read_holding_registers_rejects_address_above_modbus_limit():
    """Reject addresses beyond the Modbus address space."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    with pytest.raises(ValueError, match="start_address must be between 0 and 65535"):
        reader.read_holding_registers(start_address=65536, count=1)

    assert client.request is None


def test_read_holding_registers_rejects_range_past_final_address():
    """Reject ranges extending beyond the Modbus address space."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    with pytest.raises(ValueError, match="register range exceeds address 65535"):
        reader.read_holding_registers(start_address=65535, count=2)

    assert client.request is None


def test_reader_rejects_broadcast_device_id():
    """Reject the broadcast device ID for register reads."""
    with pytest.raises(ValueError, match="device_id must be between 1 and 247"):
        make_reader(device_id=0)


def test_reader_rejects_reserved_device_id():
    """Reject reserved Modbus device IDs."""
    with pytest.raises(ValueError, match="device_id must be between 1 and 247"):
        make_reader(device_id=248)


def test_reader_closes_serial_client():
    """Close the underlying client explicitly."""
    client = FakeModbusClient()
    reader = make_reader(client=client)

    reader.close()

    assert client.closed is True


def test_reader_context_manager_closes_serial_client():
    """Close the underlying client after context-managed use."""
    client = FakeModbusClient()

    with make_reader(client=client):
        pass

    assert client.closed is True


def test_reader_rejects_empty_serial_port():
    """Reject an empty serial-port path."""
    with pytest.raises(ValueError, match="port must not be empty"):
        make_reader(port="")


def test_reader_rejects_whitespace_only_serial_port():
    """Reject a serial-port path that contains only whitespace."""
    with pytest.raises(ValueError, match="port must not be empty"):
        make_reader(port="   ")


# ---------------------------------------------------------------------------
# TCP transport
# ---------------------------------------------------------------------------


def test_tcp_reader_builds_modbus_tcp_client(monkeypatch):
    """Build a TCP reader with the given host and port."""
    created: dict[str, object] = {}

    def fake_tcp_client(host: str, port: int = 502) -> MagicMock:
        created["host"] = host
        created["port"] = port
        return MagicMock(name="ModbusTcpClient")

    monkeypatch.setattr("rainbow_energy_modbus_client.reader.ModbusTcpClient", fake_tcp_client)

    ModbusReader.tcp(host="modbus-gateway.example", port=1502, device_id=1)

    assert created == {"host": "modbus-gateway.example", "port": 1502}


def test_tcp_reader_defaults_to_modbus_port(monkeypatch):
    """Use Modbus TCP port 502 when no port is given."""
    created: dict[str, object] = {}

    def fake_tcp_client(host: str, port: int = 502) -> MagicMock:
        created["host"] = host
        created["port"] = port
        return MagicMock(name="ModbusTcpClient")

    monkeypatch.setattr("rainbow_energy_modbus_client.reader.ModbusTcpClient", fake_tcp_client)

    ModbusReader.tcp(host="modbus-gateway.example")

    assert created == {"host": "modbus-gateway.example", "port": 502}


def test_tcp_reader_rejects_empty_host():
    """Reject an empty TCP host."""
    with pytest.raises(ValueError, match="host must not be empty"):
        ModbusReader.tcp(host="")


def test_tcp_reader_rejects_whitespace_only_host():
    """Reject a TCP host that contains only whitespace."""
    with pytest.raises(ValueError, match="host must not be empty"):
        ModbusReader.tcp(host="   ")


def test_tcp_reader_rejects_broadcast_device_id():
    """Reject the broadcast device ID for TCP readers."""
    with pytest.raises(ValueError, match="device_id must be between 1 and 247"):
        ModbusReader.tcp(host="modbus-gateway.example", device_id=0)


def test_serial_factory_builds_modbus_serial_client(monkeypatch):
    """Build a serial reader with the given port."""
    created: dict[str, object] = {}

    def fake_serial_client(port: str, baudrate: int = 9600) -> MagicMock:
        created["port"] = port
        created["baudrate"] = baudrate
        return MagicMock(name="ModbusSerialClient")

    monkeypatch.setattr("rainbow_energy_modbus_client.reader.ModbusSerialClient", fake_serial_client)

    ModbusReader.serial(port="/dev/ttyUSB0", device_id=1)

    assert created == {"port": "/dev/ttyUSB0", "baudrate": 9600}
