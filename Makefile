.PHONY: help sync test lint check build test

help:
	@printf '%s\n' \
		"make sync          Install locked dependencies" \
		"make test          Run the test suite" \
		"make lint          Run Ruff checks" \
		"make check         Run lint and tests" \
		"make build  Build the production image" \
		"make test   Build and run tests in Docker"

sync:
	uv sync

test:
	uv run --locked pytest

lint:
	uv run --locked ruff check .

check: lint test

build:
	docker build --target production -t rainbow .

test:
	docker build --target development -t rainbow-dev .
	docker run --rm rainbow-dev
