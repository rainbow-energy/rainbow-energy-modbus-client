# syntax=docker/dockerfile:1

# Build production CLI image:
#   docker build --target production -t rainbow-energy-modbus-client .
#
# Build development (lint/tests):
#   docker build --target development -t rainbow-energy-modbus-client-dev .
#
# Check a profile (mount the profiles repo or any directory with YAML maps):
#   docker run --rm -v "$PWD:/work:ro" -w /work rainbow-energy-modbus-client \
#     check-profile profiles/sunsynk_8k_sg05lp1.yaml

ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.11.29

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim-bookworm AS build

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev --no-editable

FROM build AS development

RUN uv sync --locked --no-editable

CMD ["uv", "run", "--locked", "pytest"]

FROM python:${PYTHON_VERSION}-slim-bookworm AS production

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN useradd --create-home --uid 10001 energy

COPY --from=build /opt/venv /opt/venv

USER energy

ENTRYPOINT ["rainbow-energy-modbus-client"]
CMD ["--help"]
