# Development

## Setup

```bash
make sync
make install-hooks
make build
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

## Docker

Build the development image:

```bash
make build
```

Run the test suite using that image:

```bash
make test
```

## Profile checks

Production profiles live in `src/rainbow_energy_client/data/` and must load
cleanly with every register supported by Rainbow Energy Client. The test suite
enforces this for each packaged profile.

Work-in-progress maps for gap analysis live in `profiles/draft/`. These are
excluded from packaged profile tests and are not shipped in the package.

Check which registers a profile uses that Rainbow Energy Client cannot handle yet:

```bash
make check-profile PROFILE=profiles/draft/sunsynk_8k_sg05lp1.yaml
```

The command exits `0` when every register is supported, `1` when unsupported
features are listed, and `2` when the YAML fails to load (schema errors,
overlapping addresses, and similar).

See [PROFILES.md](PROFILES.md) for how to author YAML profiles.
