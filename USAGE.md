# Usage

Rainbow reads named measurements from a SunSynk inverter over Modbus using a
YAML device profile and either a serial or TCP reader.

## One-shot poll

```python
from pathlib import Path

from rainbow.client import Client
from rainbow.profiles import load_profile
from rainbow.reader import ModbusReader

profile = load_profile(Path("profiles/sunsynk_8k_sg05lp1.yaml"))
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

## Repeated polling

`Client.run` yields successful polls and sleeps between cycles. Failed polls
raise `ClientError` from `poll()`, but `run` catches them, skips that cycle,
optionally reports via `on_error`, and continues:

```python
from rainbow.client import Client, ClientError


def log_error(error: ClientError) -> None:
    print("poll failed:", error, "cause:", error.__cause__)


with ModbusReader.tcp(host="modbus-gateway.example", port=502) as reader:
    client = Client(reader, profile, keys=keys)
    for measurements in client.run(
        interval=5.0,
        iterations=12,
        on_error=log_error,
    ):
        for measurement in measurements:
            print(measurement.key, measurement.value, measurement.unit)
```

`sleep` defaults to `time.sleep`. Pass a custom callable in tests to avoid
real delays.

## Errors

- Constructing a `Client` with no keys raises `ValueError`.
- `poll()` raises `ClientError` on failure and preserves the underlying cause
  (`RegisterReadError`, `DecodeError`, `KeyError`, or `LookupError`).
- `run()` does not stop on `ClientError`; use `on_error` to observe failures.
  Direct `poll()` calls still raise to the caller.

## Profiles

See [PROFILES.md](PROFILES.md) for authoring YAML profiles and decode options.
