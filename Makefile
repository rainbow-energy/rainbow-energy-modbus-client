.PHONY: help sync install-hooks test lint check build check-profile

help:
	@printf '%s\n' \
		"make sync          Install locked dependencies" \
		"make install-hooks Install Git hooks" \
		"make build         Build the development image" \
		"make test          Run tests in the development image" \
		"make lint          Run Ruff checks" \
		"make check         Run lint and tests" \
		"make check-profile Check a profile YAML for unsupported features"

sync:
	uv sync

install-hooks:
	uv run --locked pre-commit install

test: build
	docker run --rm rainbow-energy-modbus-client-dev

lint:
	uv run --locked ruff check .

check: lint test

build:
	docker build --target development -t rainbow-energy-modbus-client-dev .

check-profile:
	@test -n "$(PROFILE)" || (echo "Usage: make check-profile PROFILE=path/to/profile.yaml" >&2; exit 2)
	uv run --locked python scripts/check_profile.py "$(PROFILE)"
