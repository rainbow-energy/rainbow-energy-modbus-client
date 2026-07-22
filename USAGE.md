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

Continuous looping remains the caller's responsibility for now (call `poll`
on your own interval).

## Errors

- Constructing a `Client` with no keys raises `ValueError`.
- `poll()` raises `ClientError` on failure and preserves the underlying cause
  (`RegisterReadError`, `DecodeError`, `KeyError`, or `LookupError`).

## Profiles

See [PROFILES.md](PROFILES.md) for authoring YAML profiles and decode options.
