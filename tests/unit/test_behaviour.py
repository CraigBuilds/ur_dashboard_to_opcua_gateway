"""Test gateway validation, application policy, adapters, and lifecycle behavior."""

import functools
import pathlib
import signal
import types
import typing
import unittest.mock

import pytest
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery
import ur_dashboard_to_opcua_gateway._01_main as main_module
import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args
import ur_dashboard_to_opcua_gateway._04_discover_ur_programs as discover_ur_programs
import ur_dashboard_to_opcua_gateway._05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde as control_ur_programs_and_exchange_parameters
import ur_dashboard_to_opcua_gateway._06_combine_program_discovery_and_control as combine_program_discovery_and_control
import ur_dashboard_to_opcua_gateway._07_expose_program_commands_via_opcua as expose_program_commands_via_opcua

import tests.support.program_fixture as program_fixture
import tests.system.run as run_system_tests


def test_sftp_args_require_robot_host(capsys: pytest.CaptureFixture[str]) -> None:
    """Reject incomplete SFTP configuration before asking for credentials."""
    with pytest.raises(SystemExit) as error:
        parse_command_line_args.parse_args(["--catalog", "sftp"])

    assert error.value.code == 2
    assert "--robot-host is required for an SFTP catalogue." in capsys.readouterr().err


def test_sftp_args_prompt_for_password_and_preserve_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve prompted credentials and every configurable endpoint override."""
    monkeypatch.delenv("UR_ROBOT_PASSWORD", raising=False)
    prompts: typing.List[str] = []
    monkeypatch.setattr(parse_command_line_args.getpass, "getpass", lambda prompt: prompts.append(prompt) or "prompted-secret")
    args = parse_command_line_args.parse_args(
        [
            "--catalog",
            "sftp",
            "--programs-folder",
            "/robot/programs",
            "--robot-host",
            "robot.example",
            "--sftp-port",
            "2222",
            "--sftp-username",
            "operator",
            "--dashboard-host",
            "dashboard.example",
            "--dashboard-port",
            "30000",
            "--opcua-endpoint",
            "opc.tcp://127.0.0.1:5000/gateway/",
        ]
    )

    assert prompts == ["Robot password: "]
    assert args.robot_host == "robot.example"
    assert args.robot_password == "prompted-secret"
    assert args.sftp_port == 2222
    assert args.sftp_username == "operator"
    assert args.dashboard_host == "dashboard.example"
    assert args.dashboard_port == 30000


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (parse_command_line_args.Args(catalog="invalid"), "Unsupported catalogue"),
        (parse_command_line_args.Args(catalog="sftp", robot_password="secret"), "Robot host is required"),
        (parse_command_line_args.Args(catalog="sftp", robot_host="robot"), "Robot password is required"),
    ],
)
def test_discovery_rejects_invalid_configuration(args: parse_command_line_args.Args, message: str) -> None:
    """Report unsupported or incomplete discovery configuration clearly."""
    with pytest.raises(ValueError, match=message):
        discover_ur_programs.discover_programs(args)


def test_sftp_discovery_delegates_resolved_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pass application configuration into the reusable SFTP discovery package."""
    captured: typing.Dict[str, object] = {}

    def discover(**configuration: object) -> typing.List[str]:
        """Capture one package discovery call."""
        captured.update(configuration)

        return ["Main.urp"]

    monkeypatch.setattr(program_discovery, "discover_programs_over_sftp", discover)
    args = parse_command_line_args.Args(
        catalog="sftp", programs_folder="/robot/programs", robot_host="robot", robot_password="secret", sftp_port=2222, sftp_username="operator"
    )

    assert discover_ur_programs.discover_programs(args) == ["Main.urp"]
    assert captured == {"host": "robot", "root": "/robot/programs", "username": "operator", "password": "secret", "port": 2222, "trust_unknown_host_keys": True}


def test_dashboard_adapter_binds_package_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind gateway arguments while retaining qualified reusable package operations."""
    calls: typing.List[typing.Tuple[str, typing.Tuple[object, ...]]] = []

    monkeypatch.setattr(dashboard, "load_program", lambda *args: calls.append(("load", args)) or "loaded")
    monkeypatch.setattr(dashboard, "play_program", lambda *args: calls.append(("play", args)) or "played")
    monkeypatch.setattr(dashboard, "pause_program", lambda *args: calls.append(("pause", args)) or "paused")
    monkeypatch.setattr(dashboard, "stop_program", lambda *args: calls.append(("stop", args)) or "stopped")
    monkeypatch.setattr(dashboard, "get_program_state", lambda *args: calls.append(("state", args)) or "STOPPED")
    args = parse_command_line_args.Args(catalog="local", dashboard_host="robot", dashboard_port=30000)
    commands = control_ur_programs_and_exchange_parameters.create_dashboard_commands(args)

    assert commands["load_program"]("Main.urp") == "loaded"
    assert commands["play_program"]() == "played"
    assert commands["pause_program"]() == "paused"
    assert commands["stop_program"]() == "stopped"
    assert commands["get_program_state"]() == "STOPPED"
    assert calls == [
        ("load", ("robot", "Main.urp", 30000, 5.0)),
        ("play", ("robot", 30000, 5.0)),
        ("pause", ("robot", 30000, 5.0)),
        ("stop", ("robot", 30000, 5.0)),
        ("state", ("robot", 30000, 5.0)),
    ]


def test_gateway_interfaces_bind_program_methods_and_robot_operations() -> None:
    """Create flat, no-result application methods while retaining execution order."""
    events: typing.List[str] = []

    def load(program: str) -> str:
        """Record one program load."""
        events.append(f"load:{program}")

        return "loaded"

    def command(name: str) -> typing.Callable[[], str]:
        """Create one response-returning Dashboard command."""

        def run() -> str:
            """Record one Dashboard operation."""
            events.append(name)

            return name

        return run

    state = command("state")
    commands = {
        "load_program": load,
        "play_program": command("play"),
        "pause_program": command("pause"),
        "stop_program": command("stop"),
        "get_program_state": state,
    }
    interfaces = combine_program_discovery_and_control.create_interfaces(lambda: ["Main.urp", "Production/Pick Part.urp"], commands)

    assert interfaces.parameter_interface == {}
    assert interfaces.status_interface == {"ProgramState": state}
    assert set(interfaces.method_interface) == {"StartProgram_Main", "StartProgram_Production_Pick_Part", "PauseProgram", "StopProgram"}
    assert inspect_signature_parameters(interfaces.method_interface) == set()
    interfaces.method_interface["StartProgram_Production_Pick_Part"]()
    interfaces.method_interface["PauseProgram"]()
    interfaces.method_interface["StopProgram"]()
    assert events == ["load:Production/Pick Part.urp", "play", "pause", "stop"]


def inspect_signature_parameters(interface: typing.Mapping[str, typing.Callable[..., object]]) -> typing.Set[str]:
    """Return all parameters remaining on an interface's functions."""
    import inspect

    return {parameter for function in interface.values() for parameter in inspect.signature(function).parameters}


def test_program_method_name_collisions_are_rejected() -> None:
    """Reject distinct program paths that flatten to the same OPC UA method name."""
    commands = {
        "load_program": lambda program: "loaded",
        "play_program": lambda: "played",
        "pause_program": lambda: "paused",
        "stop_program": lambda: "stopped",
        "get_program_state": lambda: "STOPPED",
    }

    with pytest.raises(ValueError, match="duplicate"):
        combine_program_discovery_and_control.create_interfaces(lambda: ["Pick-Part.urp", "Pick Part.urp"], commands)


def test_opcua_adapter_forwards_flat_interfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supply application identity and all three interfaces to the reusable server."""
    interfaces = combine_program_discovery_and_control.GatewayInterfaces(
        status_interface={"State": lambda: "STOPPED"}, parameter_interface={}, method_interface={"Stop": lambda: None}
    )
    server = object()
    captured: typing.Dict[str, object] = {}

    def create_server(**configuration: object) -> object:
        """Capture one reusable server creation."""
        captured.update(configuration)

        return server

    monkeypatch.setattr(expose_program_commands_via_opcua.declarative_opcua_server, "create_server", create_server)

    result = expose_program_commands_via_opcua.create_server(interfaces, "opc.tcp://127.0.0.1:4840/gateway/")

    assert result is server
    assert captured == {
        "status_interface": interfaces.status_interface,
        "parameter_interface": interfaces.parameter_interface,
        "method_interface": interfaces.method_interface,
        "endpoint": "opc.tcp://127.0.0.1:4840/gateway/",
        "namespace": expose_program_commands_via_opcua.OPC_NAMESPACE,
        "root_object": "UR20",
    }


def test_run_until_stopped_installs_handlers_and_closes_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the managed server active until either installed signal requests shutdown."""
    server = unittest.mock.MagicMock()
    stopped = unittest.mock.MagicMock()
    handlers: typing.Dict[int, typing.Callable[[int, typing.Optional[types.FrameType]], None]] = {}

    def install_handler(number: int, handler: typing.Callable[[int, typing.Optional[types.FrameType]], None]) -> None:
        """Capture one process signal handler."""
        handlers[number] = handler

    def wait() -> None:
        """Simulate SIGTERM while the server context is active."""
        assert server.__enter__.called
        handlers[signal.SIGTERM](signal.SIGTERM, None)

    stopped.wait.side_effect = wait
    monkeypatch.setattr(main_module.threading, "Event", lambda: stopped)
    monkeypatch.setattr(main_module.signal, "signal", install_handler)

    main_module._run_until_stopped(server)

    assert set(handlers) == {signal.SIGINT, signal.SIGTERM}
    stopped.set.assert_called_once_with()
    server.__enter__.assert_called_once_with()
    server.__exit__.assert_called_once()


def test_program_fixture_archives_are_reproducible(tmp_path: pathlib.Path) -> None:
    """Produce identical URP bytes for the same logical program."""
    first = program_fixture.write_program(tmp_path / "first", "Main")
    second = program_fixture.write_program(tmp_path / "second", "Main")

    assert first.read_bytes() == second.read_bytes()


def test_configured_system_test_python_is_selected(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Use an explicitly configured supported interpreter."""
    configured = tmp_path / "python.exe"
    monkeypatch.setattr(run_system_tests, "_python_version", lambda command, repository: (3, 12, 4))

    command, version = run_system_tests._find_supported_python(tmp_path, configured)

    assert command == [str(configured.resolve())]
    assert version == (3, 12, 4)


@pytest.mark.parametrize(("version", "message"), [(None, "could not be run"), ((3, 8, 3), "Python 3.10 or later")])
def test_configured_system_test_python_is_validated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, version: typing.Optional[typing.Tuple[int, int, int]], message: str
) -> None:
    """Reject an unavailable or unsupported configured interpreter."""
    monkeypatch.setattr(run_system_tests, "_python_version", lambda command, repository: version)

    with pytest.raises(RuntimeError, match=message):
        run_system_tests._find_supported_python(tmp_path, tmp_path / "python.exe")


def test_system_test_command_forwards_selection_and_pytest_args(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Build the expected collect-only pytest command and remove the forwarding separator."""
    captured: typing.List[typing.Tuple[typing.Sequence[str], pathlib.Path, typing.Optional[typing.Dict[str, str]]]] = []

    def run(command: typing.Sequence[str], cwd: pathlib.Path, environment: typing.Optional[typing.Dict[str, str]] = None) -> None:
        """Capture one runner command."""
        captured.append((command, cwd, environment))

    monkeypatch.setattr(run_system_tests, "_run", run)
    python = tmp_path / "python.exe"
    cache = tmp_path / "pytest-cache"

    run_system_tests._run_tests(python, tmp_path, cache, "sftp", True, ["--", "-q", "--maxfail=1"])

    assert cache.is_dir()
    command, cwd, environment = captured[0]
    assert command == [
        str(python),
        "-m",
        "pytest",
        "-c",
        "tests/pytest.ini",
        "-o",
        f"cache_dir={cache}",
        "-m",
        "system",
        "-k",
        "sftp",
        "--collect-only",
        "-q",
        "--maxfail=1",
    ]
    assert cwd == tmp_path
    assert environment is not None
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
