.PHONY: help sync install-hooks test lint check build build-dev check-profile

IMAGE ?= rainbow-energy-modbus-client
DEV_IMAGE ?= rainbow-energy-modbus-client-dev

help:
	@printf '%s\n' \
		"make sync          Install locked dependencies" \
		"make install-hooks Install Git hooks" \
		"make build-dev     Build the development image" \
		"make build         Build the production CLI image" \
		"make test          Run tests in the development image" \
		"make lint          Run Ruff checks" \
		"make check         Run lint and tests" \
		"make check-profile Check a profile YAML for unsupported features"

sync:
	uv sync

install-hooks:
	uv run --locked pre-commit install

test: build-dev
	docker run --rm $(DEV_IMAGE)

lint: build-dev
	docker run --rm $(DEV_IMAGE) uv run --locked ruff check .

check: lint test

build-dev:
	docker build --target development -t $(DEV_IMAGE) .

build:
	docker build --target production -t $(IMAGE) .

check-profile:
	@test -n "$(PROFILE)" || (echo "Usage: make check-profile PROFILE=path/to/profile.yaml" >&2; exit 2)
	uv run --locked python scripts/check_profile.py "$(PROFILE)"
