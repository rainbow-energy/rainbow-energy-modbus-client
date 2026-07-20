# Rainbow

A minimal Python library that reads a SunSynk inverter directly through a USB-RS485
adapter and returns structured data.

## Development

```bash
make sync
make test
make lint
```

## Docker

Build the production image:

```bash
make build
```

Run the test suite in the development image:

```bash
make test
```

Run `make help` to list all available commands.
