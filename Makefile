.PHONY: help sync test lint check build

help:
	@printf '%s\n' \
		"make sync          Install locked dependencies" \
		"make build         Build the development image" \
		"make test          Run tests in the development image" \
		"make lint          Run Ruff checks" \
		"make check         Run lint and tests"

sync:
	uv sync

test: build
	docker run --rm rainbow-dev

lint:
	uv run --locked ruff check .

check: lint test

build:
	docker build --target development -t rainbow-dev .
