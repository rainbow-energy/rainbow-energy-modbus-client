# Rainbow

A minimal Python library that reads a SunSynk inverter over Modbus and returns
structured data. Connect with a USB-RS485 adapter (serial RTU) or via Modbus TCP
(for example through an `mbusd` gateway).

## Usage

See [USAGE.md](USAGE.md) for `Client` polling over serial or TCP.

## Device profiles

See [PROFILES.md](PROFILES.md) for how to author YAML profiles, data types,
and decode options.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for setup, Docker, tests, and profile
checks.
