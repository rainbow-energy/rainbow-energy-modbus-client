import pytest
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse

from rainbow.reader import RegisterData, RegisterReadError, Rs485Reader


class FakeModbusResponse:
    registers = [2301, 42, 875]

    def isError(self) -> bool:
        return False


class FakeModbusClient:
    def __init__(self) -> None:
        self.request: tuple[int, int, int] | None = None
        self.closed = False

    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        self.request = (address, count, device_id)
        return FakeModbusResponse()

    def close(self) -> None:
        self.closed = True


class ErrorModbusClient(FakeModbusClient):
    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        self.request = (address, count, device_id)
        return ExceptionResponse(function_code=3, exception_code=2, device_id=device_id)


class ShortResponse(FakeModbusResponse):
    registers = [2301, 42]


class ShortResponseModbusClient(FakeModbusClient):
    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        self.request = (address, count, device_id)
        return ShortResponse()


class TimeoutModbusClient(FakeModbusClient):
    def read_holding_registers(
        self, address: int, *, count: int, device_id: int
    ) -> object:
        self.request = (address, count, device_id)
        raise ModbusIOException("No response received after retries")


def test_read_holding_registers_returns_structured_data():
    client = FakeModbusClient()
    reader = Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client)

    result = reader.read_holding_registers(start_address=100, count=3)

    assert result == RegisterData(
        device_id=1,
        start_address=100,
        values=(2301, 42, 875),
    )
    assert client.request == (100, 3, 1)


def test_read_holding_registers_raises_for_modbus_error():
    client = ErrorModbusClient()
    reader = Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client)

    with pytest.raises(RegisterReadError, match="Modbus error reading registers"):
        reader.read_holding_registers(start_address=100, count=3)


def test_read_holding_registers_raises_for_short_response():
    reader = Rs485Reader(
        port="/dev/ttyUSB0",
        device_id=1,
        client=ShortResponseModbusClient(),
    )

    with pytest.raises(RegisterReadError, match="Expected 3 registers, received 2"):
        reader.read_holding_registers(start_address=100, count=3)


def test_read_holding_registers_wraps_transport_error():
    reader = Rs485Reader(
        port="/dev/ttyUSB0",
        device_id=1,
        client=TimeoutModbusClient(),
    )

    with pytest.raises(RegisterReadError, match="Failed to read registers") as error:
        reader.read_holding_registers(start_address=100, count=3)

    assert isinstance(error.value.__cause__, ModbusIOException)


def test_read_holding_registers_rejects_zero_count():
    client = FakeModbusClient()
    reader = Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client)

    with pytest.raises(ValueError, match="count must be between 1 and 125"):
        reader.read_holding_registers(start_address=100, count=0)

    assert client.request is None


def test_read_holding_registers_rejects_count_above_modbus_limit():
    client = FakeModbusClient()
    reader = Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client)

    with pytest.raises(ValueError, match="count must be between 1 and 125"):
        reader.read_holding_registers(start_address=100, count=126)

    assert client.request is None


def test_read_holding_registers_rejects_negative_address():
    client = FakeModbusClient()
    reader = Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client)

    with pytest.raises(ValueError, match="start_address must be between 0 and 65535"):
        reader.read_holding_registers(start_address=-1, count=3)

    assert client.request is None


def test_read_holding_registers_rejects_address_above_modbus_limit():
    client = FakeModbusClient()
    reader = Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client)

    with pytest.raises(ValueError, match="start_address must be between 0 and 65535"):
        reader.read_holding_registers(start_address=65536, count=1)

    assert client.request is None


def test_read_holding_registers_rejects_range_past_final_address():
    client = FakeModbusClient()
    reader = Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client)

    with pytest.raises(ValueError, match="register range exceeds address 65535"):
        reader.read_holding_registers(start_address=65535, count=2)

    assert client.request is None


def test_reader_rejects_broadcast_device_id():
    with pytest.raises(ValueError, match="device_id must be between 1 and 247"):
        Rs485Reader(port="/dev/ttyUSB0", device_id=0, client=FakeModbusClient())


def test_reader_rejects_reserved_device_id():
    with pytest.raises(ValueError, match="device_id must be between 1 and 247"):
        Rs485Reader(port="/dev/ttyUSB0", device_id=248, client=FakeModbusClient())


def test_reader_closes_serial_client():
    client = FakeModbusClient()
    reader = Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client)

    reader.close()

    assert client.closed is True


def test_reader_context_manager_closes_serial_client():
    client = FakeModbusClient()

    with Rs485Reader(port="/dev/ttyUSB0", device_id=1, client=client):
        pass

    assert client.closed is True


def test_reader_rejects_empty_serial_port():
    with pytest.raises(ValueError, match="port must not be empty"):
        Rs485Reader(port="", device_id=1, client=FakeModbusClient())
