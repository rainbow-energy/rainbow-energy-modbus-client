# Usage

Rainbow Energy Client reads and writes named measurements on an inverter over
Modbus using a YAML device profile and either a serial or TCP transport.

## One-shot poll

```python
from rainbow_energy_client import Client, ModbusReader, load_packaged_profile

profile = load_packaged_profile("sunsynk_8k_sg05lp1")
keys = ("battery_soc", "battery_voltage", "pv_power")

with ModbusReader.serial(port="/dev/ttyUSB0") as reader:
    client = Client(reader, profile, keys=keys)
    measurements = client.poll()
    for measurement in measurements:
        print(measurement.key, measurement.value, measurement.unit)
```

TCP (for example via `mbusd`):

```python
with ModbusReader.tcp(host="modbus-gateway.example", port=502) as reader:
    client = Client(reader, profile, keys=keys)
    measurements = client.poll()
```

## Writes

`Client.write` encodes engineering values for profile keys with
`access: write` and writes holding registers. Poll `keys` still configure
`poll()` / `run()`; write targets are looked up from the profile by key and
do not need to be in that list.

```python
with ModbusReader.tcp(host="modbus-gateway.example", port=502) as reader:
    client = Client(reader, profile, keys=keys)
    client.write({
        "battery_shutdown_capacity": 20,
        "grid_charge_enabled": True,
        "aux_port_usage": "Smartload",
        "prog1_time": "1:30",
    })
```

Supported write shapes follow the profile definition:

- numeric `uint16` / `int16` (inverse scale and offset)
- `options` labels or raw integers
- `binary` booleans (bitmasked keys read-modify-write the full word)
- `time` (`H:MM`) and `datetime` (`YYYY-MM-DD H:MM:SS`)

`write()` raises `ClientError` and preserves causes such as
`RegisterWriteError`, `RegisterReadError` (bitmask RMW), `EncodeError`,
`KeyError`, or `ValueError`.

## Repeated polling

`Client.run` yields successful polls and sleeps between cycles:

```python
with ModbusReader.tcp(host="modbus-gateway.example", port=502) as reader:
    client = Client(reader, profile, keys=keys)
    for measurements in client.run(interval=5.0):
        for measurement in measurements:
            print(measurement.key, measurement.value, measurement.unit)
```

Omit `iterations` (or pass `iterations=None`) to poll until the consumer
stops. Pass a positive `iterations` for a finite run. `sleep` defaults to
`time.sleep`; pass a custom callable in tests to avoid real delays.

Keep the loop body thin (for example enqueue work for another process or
thread) so Modbus polling stays on interval.

## Error logging

`poll()` raises `ClientError` on failure and preserves the underlying cause
(`RegisterReadError`, `DecodeError`, `KeyError`, or `LookupError`).

When only some Modbus batches or leaf decodes fail, `poll()` and `run()` still
return the successful measurements and report each skipped failure via
`on_error` as a `ClientError` whose cause is the underlying
`RegisterReadError` or `DecodeError`.

`run()` also catches total poll failures, skips yielding that cycle, and
continues. Pass `on_error` to observe both cases:

```python
from rainbow_energy_client import ClientError


def log_error(error: ClientError) -> None:
    print("poll failed:", error, "cause:", error.__cause__)


with ModbusReader.tcp(host="modbus-gateway.example", port=502) as reader:
    client = Client(reader, profile, keys=keys)
    for measurements in client.run(interval=5.0, on_error=log_error):
        for measurement in measurements:
            print(measurement.key, measurement.value, measurement.unit)
```

Constructing a `Client` with no keys raises `ValueError`. Direct `poll()`
calls still raise `ClientError` to the caller on total failure.

## CLI

After install, use the `rainbow-energy-client` command:

```bash
rainbow-energy-client list-profiles
rainbow-energy-client check-profile sunsynk_8k_sg05lp1
rainbow-energy-client check-profile path/to/profile.yaml
```

`check-profile` exit codes: `0` supported, `1` unsupported features,
`2` load/schema error.

Poll named measurements once over Modbus TCP or serial:

```bash
rainbow-energy-client poll \
  --profile sunsynk_8k_sg05lp1 \
  --key battery_soc --key pv_power \
  --tcp modbus-gateway.example

rainbow-energy-client poll \
  --profile sunsynk_8k_sg05lp1 \
  --key battery_soc \
  --serial /dev/ttyUSB0 \
  --device-id 1
```

Use `--tcp-port` when the Modbus TCP port is not `502`. Output is one
`key<TAB>value<TAB>unit` line per measurement. Exit codes: `0` success,
`1` poll failure, `2` profile load error.

## Profiles

See [PROFILES.md](PROFILES.md) for authoring YAML profiles and decode options.
