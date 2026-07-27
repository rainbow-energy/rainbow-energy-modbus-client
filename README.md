# Rainbow Energy Modbus Client

A minimal Python library that reads an inverter over Modbus and returns
structured data. Connect with a USB-RS485 adapter (serial RTU) or via Modbus TCP
(for example through an `mbusd` gateway).

## Install

```bash
uv add git+https://github.com/rainbow-energy/rainbow-energy-modbus-client.git
```

After install, the `rainbow-energy-modbus-client` CLI is available (see [USAGE.md](USAGE.md)).

## Usage

See [USAGE.md](USAGE.md) for the Python API, CLI, and error logging.

## Device profiles

See [PROFILES.md](PROFILES.md) for how to author YAML profiles, data types,
and decode options.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for setup, Docker, tests, and profile
checks.
