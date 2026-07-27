"""Test the packaged rainbow-energy-modbus-client CLI."""

from rainbow_energy_modbus_client.cli import main, run_poll
from rainbow_energy_modbus_client.profiles import list_packaged_profiles
from rainbow_energy_modbus_client.reader import RegisterData


class FakeReader:
    """Return canned register values without serial hardware."""

    def __init__(self, values: tuple[int, ...] = ()) -> None:
        """Store values returned by the next read."""
        self.values = values

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


def test_cli_without_subcommand_prints_usage_and_exits_2(capsys):
    """Require a subcommand when the CLI is invoked with no arguments."""
    exit_code = main([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "usage:" in captured.err.lower()


def test_list_packaged_profiles_returns_sorted_stems():
    """Discover packaged profile YAML stems from package data."""
    names = list_packaged_profiles()

    assert names == tuple(sorted(names))
    assert "sunsynk_8k_sg05lp1" in names


def test_cli_list_profiles_prints_packaged_names(capsys):
    """Print one packaged profile stem per line."""
    exit_code = main(["list-profiles"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.splitlines() == list(list_packaged_profiles())


def test_cli_check_profile_accepts_packaged_name(capsys):
    """Validate a packaged profile by stem name."""
    exit_code = main(["check-profile", "sunsynk_8k_sg05lp1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "registers are supported" in captured.out


def test_cli_check_profile_rejects_unknown_profile(capsys):
    """Exit with a profile error when the name or path cannot be loaded."""
    exit_code = main(["check-profile", "missing_device"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "profile error:" in captured.err


def test_run_poll_prints_measurements(capsys, tmp_path):
    """Poll once through the CLI helper and print key, value, and unit."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        """
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
""",
        encoding="utf-8",
    )
    reader = FakeReader(values=(85,))

    exit_code = run_poll(str(profile_path), ("battery_soc",), reader)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "battery_soc\t85\t%"


def test_run_poll_rejects_unknown_profile(capsys):
    """Exit with a profile error when the poll profile cannot be loaded."""
    exit_code = run_poll("missing_device", ("battery_soc",), FakeReader())
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "profile error:" in captured.err


def test_run_poll_reports_client_errors(capsys, tmp_path):
    """Exit non-zero when a poll fails after the profile loads."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        """
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
""",
        encoding="utf-8",
    )

    exit_code = run_poll(str(profile_path), ("missing_key",), FakeReader(values=(1,)))
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "poll error:" in captured.err


def test_cli_poll_over_tcp(monkeypatch, capsys, tmp_path):
    """Wire poll arguments to a TCP reader and print measurements."""
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        """
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
""",
        encoding="utf-8",
    )

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
    profile_path.write_text(
        """
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
""",
        encoding="utf-8",
    )

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
