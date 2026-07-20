.PHONY: help sync install-hooks test lint check build

help:
	@printf '%s\n' \
		"make sync          Install locked dependencies" \
		"make install-hooks Install Git hooks" \
		"make build         Build the development image" \
		"make test          Run tests in the development image" \
		"make lint          Run Ruff checks" \
		"make check         Run lint and tests"

sync:
	uv sync

install-hooks:
	uv run --locked pre-commit install

test: build
	docker run --rm rainbow-dev

lint:
	uv run --locked ruff check .

check: lint test

build:
	docker build --target development -t rainbow-dev .
