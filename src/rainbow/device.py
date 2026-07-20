"""Fetch and decode measurements using a device profile."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from rainbow.decode import Measurement, decode_register
from rainbow.profiles import DeviceProfile, RegisterDefinition
from rainbow.reader import RegisterData

_MAX_BATCH_COUNT = 125
_MAX_BATCH_GAP = 16


class RegisterReader(Protocol):
    """Describe the reader behavior used to fetch Modbus registers."""

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Read a contiguous range of holding registers."""
        ...

    def read_input_registers(self, start_address: int, count: int) -> RegisterData:
        """Read a contiguous range of input registers."""
        ...


@dataclass(frozen=True, slots=True)
class _RegisterBatch:
    """A contiguous Modbus read covering one or more register definitions."""

    function: str
    start_address: int
    count: int


def _lookup_register(profile: DeviceProfile, key: str) -> RegisterDefinition:
    """Find one register definition by key."""
    definition = next(
        (register for register in profile.registers if register.key == key),
        None,
    )
    if definition is None:
        raise KeyError(f"unknown register key: {key}")
    return definition


def _read_register_range(
    reader: RegisterReader,
    function: str,
    start_address: int,
    count: int,
) -> RegisterData:
    """Read one contiguous register range for the given Modbus function."""
    if function == "input":
        return reader.read_input_registers(start_address, count)
    return reader.read_holding_registers(start_address, count)


def _plan_batches(definitions: Sequence[RegisterDefinition]) -> tuple[_RegisterBatch, ...]:
    """Merge nearby same-function registers into contiguous read batches."""
    ordered = sorted(
        definitions,
        key=lambda definition: (definition.function, definition.address),
    )
    batches: list[_RegisterBatch] = []
    for definition in ordered:
        end_address = definition.address + definition.count - 1
        if batches:
            current = batches[-1]
            current_end = current.start_address + current.count - 1
            merged_count = end_address - current.start_address + 1
            if (
                definition.function == current.function
                and definition.address <= current_end + 1 + _MAX_BATCH_GAP
                and merged_count <= _MAX_BATCH_COUNT
            ):
                batches[-1] = _RegisterBatch(
                    function=current.function,
                    start_address=current.start_address,
                    count=merged_count,
                )
                continue
        batches.append(
            _RegisterBatch(
                function=definition.function,
                start_address=definition.address,
                count=definition.count,
            )
        )
    return tuple(batches)


def read_measurement(
    reader: RegisterReader,
    profile: DeviceProfile,
    key: str,
) -> Measurement:
    """Read one named register from the device and decode it."""
    return read_measurements(reader, profile, (key,))[0]


def read_measurements(
    reader: RegisterReader,
    profile: DeviceProfile,
    keys: Sequence[str],
) -> tuple[Measurement, ...]:
    """Read several named registers, batching adjacent Modbus ranges."""
    definitions = tuple(_lookup_register(profile, key) for key in keys)
    batch_values = {
        (batch.function, batch.start_address): _read_register_range(
            reader,
            batch.function,
            batch.start_address,
            batch.count,
        ).values
        for batch in _plan_batches(definitions)
    }

    measurements: list[Measurement] = []
    for definition in definitions:
        end_address = definition.address + definition.count - 1
        for (function, start_address), values in batch_values.items():
            batch_end = start_address + len(values) - 1
            if (
                function == definition.function
                and start_address <= definition.address
                and end_address <= batch_end
            ):
                offset = definition.address - start_address
                slice_values = values[offset : offset + definition.count]
                measurements.append(decode_register(definition, slice_values))
                break
    return tuple(measurements)
