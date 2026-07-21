"""Factories for building test doubles with minimal boilerplate."""

from rainbow.profiles import RegisterDefinition


def make_register(**overrides) -> RegisterDefinition:
    """Build a RegisterDefinition, overriding only what the test needs."""
    values = {
        "key": "register",
        "name": "Register",
        "data_type": "uint16",
        "unit": "",
        "access": "read",
        "address": 0,
        "function": "holding",
        "scale": 1.0,
        "count": 1,
    }
    values.update(overrides)
    return RegisterDefinition(**values)
