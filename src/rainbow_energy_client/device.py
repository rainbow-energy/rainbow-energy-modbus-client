"""Fetch and decode measurements using a device profile."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from rainbow_energy_client.decode import Measurement, decode_math, decode_register
from rainbow_energy_client.profiles import DeviceProfile, RegisterDefinition
from rainbow_energy_client.reader import RegisterData, RegisterReadError

_MAX_BATCH_COUNT = 32
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

    @property
    def end_address(self) -> int:
        """Return the last Modbus address covered by this batch."""
        return self.start_address + self.count - 1


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


def _leaf_definitions(
    profile: DeviceProfile,
    definitions: Sequence[RegisterDefinition],
) -> tuple[RegisterDefinition, ...]:
    """Expand math sources into unique leaf register definitions."""
    leaves: dict[str, RegisterDefinition] = {}
    for definition in definitions:
        if definition.sources is None:
            leaves[definition.key] = definition
            continue
        for source in definition.sources:
            leaves[source.key] = _lookup_register(profile, source.key)
    return tuple(leaves.values())


def _definition_end(definition: RegisterDefinition) -> int:
    """Return the last address covered by one leaf definition."""
    assert definition.address is not None
    return definition.address + definition.count - 1


def _can_merge(batch: _RegisterBatch, definition: RegisterDefinition) -> bool:
    """Return whether definition can extend an existing batch."""
    assert definition.address is not None
    assert definition.function is not None
    merged_count = _definition_end(definition) - batch.start_address + 1
    return (
        definition.function == batch.function
        and definition.address <= batch.end_address + 1 + _MAX_BATCH_GAP
        and merged_count <= _MAX_BATCH_COUNT
    )


def _extend_batch(
    batch: _RegisterBatch, definition: RegisterDefinition
) -> _RegisterBatch:
    """Grow a batch so it ends at the definition's final address."""
    return _RegisterBatch(
        function=batch.function,
        start_address=batch.start_address,
        count=_definition_end(definition) - batch.start_address + 1,
    )


def _plan_batches(definitions: Sequence[RegisterDefinition]) -> tuple[_RegisterBatch, ...]:
    """Merge nearby same-function registers into contiguous read batches."""
    ordered = sorted(
        definitions,
        key=lambda definition: (definition.function, definition.address),
    )
    batches: list[_RegisterBatch] = []
    for definition in ordered:
        assert definition.address is not None
        assert definition.function is not None
        if batches and _can_merge(batches[-1], definition):
            batches[-1] = _extend_batch(batches[-1], definition)
            continue
        batches.append(
            _RegisterBatch(
                function=definition.function,
                start_address=definition.address,
                count=definition.count,
            )
        )
    return tuple(batches)


def _decode_leaf(
    definition: RegisterDefinition,
    batch_values: dict[tuple[str, int], tuple[int, ...]],
) -> Measurement:
    """Decode one leaf register from batched Modbus values."""
    assert definition.address is not None
    assert definition.function is not None
    end_address = _definition_end(definition)
    for (function, start_address), values in batch_values.items():
        batch_end = start_address + len(values) - 1
        if (
            function == definition.function
            and start_address <= definition.address
            and end_address <= batch_end
        ):
            offset = definition.address - start_address
            slice_values = values[offset : offset + definition.count]
            return decode_register(definition, slice_values)
    raise LookupError(f"no batch covered register {definition.key}")


def _numeric_source_values(
    decoded: Mapping[str, Measurement],
) -> dict[str, float | int]:
    """Collect numeric leaf values for math measurements."""
    return {
        key: measurement.value
        for key, measurement in decoded.items()
        if isinstance(measurement.value, (int, float))
        and not isinstance(measurement.value, bool)
    }


def _measurement_for(
    definition: RegisterDefinition,
    decoded: Mapping[str, Measurement],
    source_values: Mapping[str, float | int],
) -> Measurement:
    """Return a leaf or math measurement for one requested definition."""
    if definition.sources is None:
        return decoded[definition.key]
    return decode_math(definition, source_values)


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
    *,
    on_error: Callable[[RegisterReadError], None] | None = None,
) -> tuple[Measurement, ...]:
    """Read several named registers, batching adjacent Modbus ranges.

    When one Modbus batch fails, skip it and continue with the rest. Call
    *on_error* for each skipped batch when provided. If every requested
    measurement is lost to read failures, re-raise the first error.
    """
    definitions = tuple(_lookup_register(profile, key) for key in keys)
    leaves = _leaf_definitions(profile, definitions)
    batch_values: dict[tuple[str, int], tuple[int, ...]] = {}
    read_errors: list[RegisterReadError] = []
    for batch in _plan_batches(leaves):
        try:
            batch_values[(batch.function, batch.start_address)] = _read_register_range(
                reader,
                batch.function,
                batch.start_address,
                batch.count,
            ).values
        except RegisterReadError as error:
            read_errors.append(error)
    decoded: dict[str, Measurement] = {}
    for leaf in leaves:
        try:
            decoded[leaf.key] = _decode_leaf(leaf, batch_values)
        except LookupError:
            continue
    source_values = _numeric_source_values(decoded)
    measurements = tuple(
        _measurement_for(definition, decoded, source_values)
        for definition in definitions
        if definition.key in decoded
        or (
            definition.sources is not None
            and all(source.key in decoded for source in definition.sources)
        )
    )
    if not measurements and read_errors:
        raise read_errors[0]
    if on_error is not None:
        for error in read_errors:
            on_error(error)
    return measurements
