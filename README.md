# Rainbow

A minimal Python library that reads a SunSynk inverter directly through a USB-RS485
adapter and returns structured data.

## Development

```bash
make sync
make install-hooks
make build
make test
make lint
```

## Docker

Build the development image:

```bash
make build
```

Run the test suite using that image:

```bash
make test
```

Run `make help` to list all available commands.

## Device profiles

See [PROFILES.md](PROFILES.md) for how to author YAML profiles, data types,
and decode options.

Production profiles live in `profiles/` and must load cleanly with every
register supported by Rainbow. The test suite enforces this for each file in
that directory.

Work-in-progress maps for gap analysis live in `profiles/draft/`. These are
excluded from packaged profile tests and are not used by the application.

Check which registers a profile uses that Rainbow cannot handle yet:

```bash
make check-profile PROFILE=profiles/draft/sunsynk_8k_sg05lp1.yaml
```

The command exits `0` when every register is supported, `1` when unsupported
features are listed, and `2` when the YAML fails to load (schema errors,
overlapping addresses, and similar).
