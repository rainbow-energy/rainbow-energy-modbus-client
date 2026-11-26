"""Test the rainbow-energy-modbus-client CLI."""

import pytest

from rainbow_energy_modbus_client.cli import (
    _parse_set_argument,
    _parse_set_value,
    main,
    run_poll,
    run_write,
)
from rainbow_energy_modbus_client.reader import RegisterData


class FakeReader:
    """Return canned register values without serial hardware."""

    def __init__(self, values: tuple[int, ...] = ()) -> None:
        """Store values returned by the next read."""
        self.values = values
        self.writes: list[tuple[int, tuple[int, ...]]] = []

    def read_holding_registers(self, start_address: int, count: int) -> RegisterData:
        """Return canned holding-register values."""
        return RegisterData(
            device_id=1,
            start_address=start_address,
            values=self.values,
        )

    def read_input_registers(self, start_address: int, count: int) -> RegisterData:
        """Return canned input-register values."""
        return RegisterData(
            device_id=1,
            start_address=start_address,
            values=self.values,
        )

    def write_holding_registers(
        self, start_address: int, values: tuple[int, ...] | list[int]
    ) -> None:
        """Record a holding-register write."""
        self.writes.append((start_address, tuple(values)))


_MINIMAL_PROFILE = """
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: 184
    function: holding
    data_type: uint16
    scale: 1
    unit: "%"
    access: read
  - key: battery_shutdown_capacity
    name: Battery Shutdown Capacity
    address: 217
    function: holding
    data_type: uint16
    scale: 1
    unit: "%"
    access: write
"""


def test_cli_without_subcommand_prints_usage_and_exits_2(capsys):
    """Require a subcommand when the CLI is invoked with no arguments."""
    exit_code = main([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "usage:" in captured.err.lower()


def test_cli_check_profile_accepts_supported_path(capsys, tmp_path):
    """Validate a profile YAML file by path."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")

    exit_code = main(["check-profile", str(profile_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "registers are supported" in captured.out


def test_cli_check_profile_rejects_missing_path(capsys):
    """Exit with a profile error when the path cannot be loaded."""
    exit_code = main(["check-profile", "missing_device.yaml"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "profile error:" in captured.err


def test_run_poll_prints_measurements(capsys, tmp_path):
    """Poll once through the CLI helper and print key, value, and unit."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")
    reader = FakeReader(values=(85,))

    exit_code = run_poll(str(profile_path), ("battery_soc",), reader)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "battery_soc\t85\t%"


def test_run_poll_rejects_missing_path(capsys):
    """Exit with a profile error when the poll profile path cannot be loaded."""
    exit_code = run_poll("missing_device.yaml", ("battery_soc",), FakeReader())
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "profile error:" in captured.err


def test_run_poll_reports_client_errors(capsys, tmp_path):
    """Exit non-zero when a poll fails after the profile loads."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")

    exit_code = run_poll(str(profile_path), ("missing_key",), FakeReader(values=(1,)))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "poll error:" in captured.err


def test_cli_poll_over_tcp(monkeypatch, capsys, tmp_path):
    """Wire poll arguments to a TCP reader and print measurements."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")

    class ContextFakeReader(FakeReader):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_tcp(host: str, port: int = 502, device_id: int = 1, client=None):
        assert host == "modbus.example"
        assert port == 1502
        assert device_id == 2
        return ContextFakeReader(values=(85,))

    monkeypatch.setattr("rainbow_energy_modbus_client.cli.ModbusReader.tcp", fake_tcp)

    exit_code = main(
        [
            "poll",
            "--profile",
            str(profile_path),
            "--key",
            "battery_soc",
            "--tcp",
            "modbus.example",
            "--tcp-port",
            "1502",
            "--device-id",
            "2",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "battery_soc\t85\t%"


def test_cli_poll_over_serial(monkeypatch, capsys, tmp_path):
    """Wire poll arguments to a serial reader and print measurements."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")

    class ContextFakeReader(FakeReader):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_serial(port: str, device_id: int = 1, client=None):
        assert port == "/dev/ttyUSB0"
        assert device_id == 1
        return ContextFakeReader(values=(42,))

    monkeypatch.setattr("rainbow_energy_modbus_client.cli.ModbusReader.serial", fake_serial)

    exit_code = main(
        [
            "poll",
            "--profile",
            str(profile_path),
            "--key",
            "battery_soc",
            "--serial",
            "/dev/ttyUSB0",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "battery_soc\t42\t%"


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def test_run_write_encodes_and_writes_value(capsys, tmp_path):
    """Write one profile key through the CLI helper."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")
    reader = FakeReader()

    exit_code = run_write(
        str(profile_path),
        {"battery_shutdown_capacity": 20},
        reader,
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert reader.writes == [(217, (20,))]
    assert captured.out.strip() == "wrote\tbattery_shutdown_capacity\t20"


def test_run_write_rejects_missing_path(capsys):
    """Exit with a profile error when the write profile path cannot be loaded."""
    exit_code = run_write(
        "missing_device.yaml",
        {"battery_shutdown_capacity": 20},
        FakeReader(),
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "profile error:" in captured.err


def test_run_write_reports_client_errors(capsys, tmp_path):
    """Exit non-zero when a write fails after the profile loads."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")

    exit_code = run_write(
        str(profile_path),
        {"battery_soc": 50},
        FakeReader(),
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "write error:" in captured.err
    assert captured.out == ""


def test_cli_write_over_tcp(monkeypatch, capsys, tmp_path):
    """Wire write arguments to a TCP transport and confirm the write."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")

    class ContextFakeReader(FakeReader):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    reader = ContextFakeReader()

    def fake_tcp(host: str, port: int = 502, device_id: int = 1, client=None):
        assert host == "modbus.example"
        assert port == 1502
        assert device_id == 2
        return reader

    monkeypatch.setattr("rainbow_energy_modbus_client.cli.ModbusReader.tcp", fake_tcp)

    exit_code = main(
        [
            "write",
            "--profile",
            str(profile_path),
            "--set",
            "battery_shutdown_capacity=20",
            "--tcp",
            "modbus.example",
            "--tcp-port",
            "1502",
            "--device-id",
            "2",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert reader.writes == [(217, (20,))]
    assert captured.out.strip() == "wrote\tbattery_shutdown_capacity\t20"


def test_cli_write_over_serial(monkeypatch, capsys, tmp_path):
    """Wire write arguments to a serial transport and confirm the write."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(_MINIMAL_PROFILE, encoding="utf-8")

    class ContextFakeReader(FakeReader):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    reader = ContextFakeReader()

    def fake_serial(port: str, device_id: int = 1, client=None):
        assert port == "/dev/ttyUSB0"
        assert device_id == 1
        return reader

    monkeypatch.setattr(
        "rainbow_energy_modbus_client.cli.ModbusReader.serial",
        fake_serial,
    )

    exit_code = main(
        [
            "write",
            "--profile",
            str(profile_path),
            "--set",
            "battery_shutdown_capacity=20",
            "--serial",
            "/dev/ttyUSB0",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert reader.writes == [(217, (20,))]
    assert captured.out.strip() == "wrote\tbattery_shutdown_capacity\t20"


def test_parse_set_value_coerces_bool_int_float_and_string():
    """Parse --set values into the types Client.write expects."""
    assert _parse_set_value("true") is True
    assert _parse_set_value("FALSE") is False
    assert _parse_set_value("20") == 20
    assert _parse_set_value("1.5") == 1.5
    assert _parse_set_value("1:30") == "1:30"
    assert _parse_set_value("Smartload") == "Smartload"


def test_parse_set_argument_splits_key_and_value():
    """Split KEY=VALUE set arguments for the write subcommand."""
    assert _parse_set_argument("battery_shutdown_capacity=20") == (
        "battery_shutdown_capacity",
        20,
    )


def test_parse_set_argument_rejects_missing_separator():
    """Reject --set values that are not KEY=VALUE pairs."""
    from argparse import ArgumentTypeError

    with pytest.raises(ArgumentTypeError, match="expected KEY=VALUE"):
        _parse_set_argument("battery_shutdown_capacity")


def test_parse_set_argument_rejects_empty_key():
    """Reject --set values with an empty key before '='."""
    from argparse import ArgumentTypeError

    with pytest.raises(ArgumentTypeError, match="expected KEY=VALUE"):
        _parse_set_argument("=20")
