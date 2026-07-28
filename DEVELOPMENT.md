# Development

## Setup

```bash
make sync
make install-hooks
make build-dev
```

## Checks

```bash
make test
make lint
make check
```

`make test` builds the development Docker image and runs the suite inside it.
`make check` runs lint and tests.

Run `make help` to list all available commands.

## Packaging

Build an sdist and wheel into `dist/`:

```bash
uv build
```

Inspect the wheel contents if you need to confirm `py.typed` is included and
no profile YAML is packaged:

```bash
unzip -l dist/rainbow_energy_modbus_client-*.whl
```

## Docker

Build the development image:

```bash
make build-dev
```

Run the test suite using that image:

```bash
make test
```

Build and run the production CLI image (pushed to GHCR on merges to `main`):

```bash
make build
docker run --rm -v "$PWD:/profiles:ro" -w /profiles rainbow-energy-modbus-client \
  check-profile profiles/sunsynk_8k_sg05lp1.yaml
```

Image tags: `latest`, short commit SHA, and CalVer+SHA (for example
`2026.7.28-a1b2c3d`) at `ghcr.io/rainbow-energy/rainbow-energy-modbus-client`.

## Profile checks

Device maps live in
[rainbow-energy-modbus-profiles](https://github.com/rainbow-energy/rainbow-energy-modbus-profiles).
This package loads them only by filesystem path.

Check which registers a profile uses that Rainbow Energy Modbus Client cannot handle yet:

```bash
make check-profile PROFILE=path/to/profile.yaml
# equivalent after install:
rainbow-energy-modbus-client check-profile path/to/profile.yaml
```

The command exits `0` when every register is supported, `1` when unsupported
features are listed, and `2` when the YAML fails to load (schema errors,
overlapping addresses, and similar).

See [PROFILES.md](PROFILES.md) for how to author YAML profiles.
