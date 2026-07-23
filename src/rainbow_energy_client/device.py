"""Fetch, decode, and write measurements using a device profile."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from rainbow_energy_client.decode import DecodeError, Measurement, decode_math, decode_register
from rainbow_energy_client.encode import EncodeError, encode_register
from rainbow_energy_client.profiles import DeviceProfile, RegisterDefinition
from rainbow_energy_client.reader import RegisterData, RegisterReadError

_MAX_BATCH_COUNT = 32
_MAX_BATCH_GAP = 16

BatchError = RegisterReadError | DecodeError
WriteValue = float | int | str | bool


class RegisterReader(Protocol):
    """Describe the reader behavior used to fetch Modbus registers."""

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Read a contiguous range of holding registers."""
        ...

    def read_input_registers(self, start_address: int, count: int) -> RegisterData:
        """Read a contiguous range of input registers."""
        ...


class RegisterWriter(Protocol):
    """Describe the writer behavior used to update Modbus registers."""

    def write_holding_registers(
        self, start_address: int, values: tuple[int, ...] | list[int]
    ) -> None:
        """Write a contiguous range of holding registers."""
        ...


class RegisterTransport(RegisterReader, RegisterWriter, Protocol):
    """Describe combined read/write transport used for RMW writes."""

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
    batch_values: Mapping[tuple[str, int], tuple[int, ...]],
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


def _read_batches(
    reader: RegisterReader,
    leaves: Sequence[RegisterDefinition],
) -> tuple[dict[tuple[str, int], tuple[int, ...]], list[BatchError]]:
    """Read planned Modbus batches, collecting read failures."""
    batch_values: dict[tuple[str, int], tuple[int, ...]] = {}
    errors: list[BatchError] = []
    for batch in _plan_batches(leaves):
        try:
            batch_values[(batch.function, batch.start_address)] = _read_register_range(
                reader,
                batch.function,
                batch.start_address,
                batch.count,
            ).values
        except RegisterReadError as error:
            errors.append(error)
    return batch_values, errors


def _decode_leaves(
    leaves: Sequence[RegisterDefinition],
    batch_values: Mapping[tuple[str, int], tuple[int, ...]],
) -> tuple[dict[str, Measurement], list[BatchError]]:
    """Decode leaf registers from batch values, collecting decode failures."""
    decoded: dict[str, Measurement] = {}
    errors: list[BatchError] = []
    for leaf in leaves:
        try:
            decoded[leaf.key] = _decode_leaf(leaf, batch_values)
        except LookupError:
            continue
        except DecodeError as error:
            errors.append(error)
    return decoded, errors


def _collect_measurements(
    definitions: Sequence[RegisterDefinition],
    decoded: Mapping[str, Measurement],
) -> tuple[Measurement, ...]:
    """Build measurements for definitions whose leaf data is available."""
    source_values = _numeric_source_values(decoded)
    return tuple(
        _measurement_for(definition, decoded, source_values)
        for definition in definitions
        if definition.key in decoded
        or (
            definition.sources is not None
            and all(source.key in decoded for source in definition.sources)
        )
    )


def _resolve_partial_results(
    measurements: tuple[Measurement, ...],
    errors: Sequence[BatchError],
    on_error: Callable[[BatchError], None] | None,
) -> tuple[Measurement, ...]:
    """Raise on total failure, otherwise report partial errors and return."""
    if not measurements and errors:
        raise errors[0]
    if on_error is not None:
        for error in errors:
            on_error(error)
    return measurements


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
    on_error: Callable[[BatchError], None] | None = None,
) -> tuple[Measurement, ...]:
    """Read several named registers, batching adjacent Modbus ranges.

    When one Modbus batch or leaf decode fails, skip it and continue with the
    rest. Call *on_error* for each skipped failure when provided. If every
    requested measurement is lost, re-raise the first error.
    """
    definitions = tuple(_lookup_register(profile, key) for key in keys)
    leaves = _leaf_definitions(profile, definitions)
    batch_values, errors = _read_batches(reader, leaves)
    decoded, decode_errors = _decode_leaves(leaves, batch_values)
    errors.extend(decode_errors)
    measurements = _collect_measurements(definitions, decoded)
    return _resolve_partial_results(measurements, errors, on_error)


def _require_writable(definition: RegisterDefinition) -> None:
    """Reject registers that are not writable holding leaves."""
    if definition.access != "write":
        raise EncodeError(f"register {definition.key} is not writable")
    if definition.sources is not None:
        raise EncodeError(f"math register {definition.key} cannot be written")
    if definition.function != "holding":
        raise EncodeError(
            f"register {definition.key} writes require holding registers"
        )
    assert definition.address is not None


def _merge_bitmask(
    current: int,
    encoded: int,
    bitmask: int,
) -> int:
    """Merge encoded masked bits into an existing register word."""
    return (current & ~bitmask) | (encoded & bitmask)


def _words_for_write(
    transport: RegisterTransport,
    definition: RegisterDefinition,
    value: WriteValue,
) -> tuple[int, ...]:
    """Encode a value, applying read-modify-write when a bitmask is set."""
    encoded = encode_register(definition, value)
    if definition.bitmask is None:
        return encoded
    assert definition.address is not None
    if len(encoded) != 1:
        raise EncodeError(
            f"bitmask writes require a single register for {definition.key}"
        )
    current = transport.read_holding_registers(definition.address, 1).values[0]
    return (_merge_bitmask(current, encoded[0], definition.bitmask),)


def write_measurements(
    transport: RegisterTransport,
    profile: DeviceProfile,
    values: Mapping[str, WriteValue],
) -> None:
    """Encode and write named writable registers.

    Bitmasked registers read the current holding word, merge the encoded bits,
    then write the full word back.
    """
    if not values:
        raise ValueError("values must not be empty")
    for key, value in values.items():
        definition = _lookup_register(profile, key)
        _require_writable(definition)
        words = _words_for_write(transport, definition, value)
        assert definition.address is not None
        transport.write_holding_registers(definition.address, words)
