# Rainbow Energy Client agent guidance

## Project context

- Rainbow Energy Client is a small Python library for reading inverters directly through a
  USB-RS485 adapter or Modbus TCP (for example via a serial-to-TCP gateway).
- Use PyModbus for Modbus RTU/TCP transport; do not reimplement protocol framing, CRC,
  retries, or serial communication.
- Python dependencies and locking are managed with `uv`.
- Tests run in the development Docker image through the `Makefile`.

## Development process

- Follow strict TDD, one test per cycle:
  1. Add one test for one behaviour.
  2. Run it and confirm it fails for the expected reason.
  3. Write only enough production code to pass.
  4. Refactor while keeping all tests green.
- Work through one tests at a time and ask for user confirmation of next step.
- Use injected fake clients in unit tests; tests must not require USB hardware.
- Aim for 100% code coverage; cover new code and close gaps shown by
  `make test` (`--cov-report=term-missing`).
- Prefer clear application errors while preserving underlying exceptions as causes.
- Add concise docstrings to modules and public classes, functions, and methods.
- Do not add speculative abstractions or unrelated features.

## Documentation

- Keep docs in sync with behaviour changes in the same change set when practical.
- Update [PROFILES.md](PROFILES.md) when profile schema, data types, decode
  modifiers, overlap rules, or authoring guidance change.
- Update [README.md](README.md) when the high-level product description changes.
- Update [USAGE.md](USAGE.md) when the client API or example workflow changes.
- Update [DEVELOPMENT.md](DEVELOPMENT.md) when setup, commands, Docker, or
  profile-check workflow changes.
- Do not leave docs describing removed or outdated behaviour.

## Commit messages

- Summarize the change in a subject of about 50 characters or fewer.
- Separate the subject from an optional body with a blank line.
- Wrap body text at about 72 characters.
- Explain the problem and why the change is needed rather than how the code works.
- Document important side effects or unintuitive consequences.
- Put issue references at the end, for example `Resolves: #123`.

## Commands

- `make sync` — synchronize locked dependencies.
- `make install-hooks` — install repository Git hooks.
- `make build` — build the development Docker image.
- `make test` — build the image and run tests in it.
- `make lint` — run Ruff.
- `make check` — run lint and tests.
