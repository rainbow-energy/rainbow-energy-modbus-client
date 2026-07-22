# Rainbow

A minimal Python library that reads a SunSynk inverter over Modbus and returns
structured data. Connect with a USB-RS485 adapter (serial RTU) or via Modbus TCP
(for example through an `mbusd` gateway).

Use `Client` with a profile and key list to poll named measurements on demand
(`client.poll()`). Continuous looping remains the caller's responsibility for
now. Poll failures raise `ClientError` and preserve the underlying cause
(Modbus read, decode, or unknown key).

## Device profiles

See [PROFILES.md](PROFILES.md) for how to author YAML profiles, data types,
and decode options.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for setup, Docker, tests, and profile
checks.
