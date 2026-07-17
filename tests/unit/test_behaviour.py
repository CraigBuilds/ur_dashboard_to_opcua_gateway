"""Test gateway validation, package binding, application policy, and lifecycle."""

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
import ur_dashboard_to_opcua_gateway._03_compose_gateway as compose_gateway

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
    ("catalog", "robot_host", "robot_password", "message"),
    [
        ("invalid", None, None, "Unsupported catalogue"),
        ("sftp", None, "secret", "Robot host is required"),
        ("sftp", "robot", None, "Robot password is required"),
    ],
)
def test_args_reject_invalid_configuration(catalog: str, robot_host: typing.Optional[str], robot_password: typing.Optional[str], message: str) -> None:
    """Reject unsupported or incomplete discovery configuration at the application boundary."""
    with pytest.raises(ValueError, match=message):
        parse_command_line_args.Args(catalog=catalog, robot_host=robot_host, robot_password=robot_password)


def test_sftp_discovery_delegates_resolved_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pass application configuration into the reusable SFTP discovery package."""
    discover = unittest.mock.MagicMock(return_value=["Main.urp"])

    monkeypatch.setattr(program_discovery, "discover_programs_over_sftp", discover)

    assert program_discovery.discover_programs(
        "sftp", "/robot/programs", host="robot", username="operator", password="secret", port=2222, trust_unknown_host_keys=True
    ) == ["Main.urp"]
    discover.assert_called_once_with("robot", "/robot/programs", "operator", "secret", 2222, program_discovery.DEFAULT_SFTP_TIMEOUT, True)


def test_gateway_methods_bind_package_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind package operations into typed flat interfaces and retain execution order."""
    calls: typing.List[typing.Tuple[str, typing.Tuple[object, ...]]] = []
    captured: typing.Dict[str, object] = {}

    def load(host: str, program: str, port: int, timeout: float) -> str:
        calls.append(("load", (host, program, port, timeout)))

        return "loaded"

    def command(name: str, response: str) -> typing.Callable[[str, int, float], str]:
        def run(host: str, port: int, timeout: float) -> str:
            calls.append((name, (host, port, timeout)))

            return response

        return run

    monkeypatch.setattr(dashboard, "load_program", load)
    monkeypatch.setattr(dashboard, "play_program", command("play", "played"))
    monkeypatch.setattr(dashboard, "pause_program", command("pause", "paused"))
    monkeypatch.setattr(dashboard, "stop_program", command("stop", "stopped"))
    monkeypatch.setattr(dashboard, "get_program_state", command("state", "STOPPED"))
    args = parse_command_line_args.Args(catalog="local", dashboard_host="robot", dashboard_port=30000)
    discoveries: typing.List[typing.Tuple[object, ...]] = []

    def discover(
        backend: str,
        root: object,
        host: typing.Optional[str],
        username: str,
        password: typing.Optional[str],
        port: int,
        timeout: float,
        trust_unknown_host_keys: bool,
    ) -> typing.List[str]:
        discoveries.append((backend, root, host, username, password, port, timeout, trust_unknown_host_keys))

        return ["Main.urp", "Production/Pick Part.urp"]

    monkeypatch.setattr(compose_gateway.program_discovery, "discover_programs", discover)
    monkeypatch.setattr(compose_gateway.declarative_opcua_server, "create_server", lambda **configuration: captured.update(configuration) or object())

    compose_gateway.compose_gateway(args)

    status_interface = typing.cast(typing.Dict[str, typing.Callable[[], object]], captured["status_interface"])
    method_interface = typing.cast(typing.Dict[str, typing.Callable[..., object]], captured["method_interface"])
    assert captured["parameter_interface"] == {}
    assert set(method_interface) == {
        "ListPrograms",
        "LoadProgram",
        "RunProgram",
        "PauseProgram",
        "StopProgram",
        "StartProgram_Main",
        "StartProgram_Production_Pick_Part",
    }
    assert inspect_signature_parameters(status_interface) == set()
    assert inspect_required_signature_parameters(method_interface) == {"program"}
    assert status_interface["ProgramState"]() == "STOPPED"
    assert method_interface["ListPrograms"]() == ["Main.urp", "Production/Pick Part.urp"]
    assert method_interface["LoadProgram"]("Main.urp") == "loaded"
    assert method_interface["RunProgram"]() == "played"
    method_interface["StartProgram_Production_Pick_Part"]()
    method_interface["PauseProgram"]()
    method_interface["StopProgram"]()
    assert len(discoveries) == 2
    assert calls == [
        ("state", ("robot", 30000, 5.0)),
        ("load", ("robot", "Main.urp", 30000, 5.0)),
        ("play", ("robot", 30000, 5.0)),
        ("load", ("robot", "Production/Pick Part.urp", 30000, 5.0)),
        ("play", ("robot", 30000, 5.0)),
        ("pause", ("robot", 30000, 5.0)),
        ("stop", ("robot", 30000, 5.0)),
    ]


def inspect_signature_parameters(interface: typing.Mapping[str, typing.Callable[..., object]]) -> typing.Set[str]:
    """Return all parameters remaining on an interface's functions."""
    import inspect

    return {parameter for function in interface.values() for parameter in inspect.signature(function).parameters}


def inspect_required_signature_parameters(interface: typing.Mapping[str, typing.Callable[..., object]]) -> typing.Set[str]:
    """Return required parameters remaining on an interface's functions."""
    import inspect

    return {
        name
        for function in interface.values()
        for name, parameter in inspect.signature(function).parameters.items()
        if parameter.default is inspect.Parameter.empty
    }


def test_program_method_name_collisions_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject distinct program paths that flatten to the same OPC UA method name."""
    args = parse_command_line_args.Args(catalog="local")
    monkeypatch.setattr(compose_gateway.program_discovery, "discover_programs", lambda *arguments: ["Pick-Part.urp", "Pick Part.urp"])

    with pytest.raises(ValueError, match="duplicate"):
        compose_gateway.compose_gateway(args)


def test_run_until_stopped_installs_handlers_and_closes_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the plain server active until either installed signal requests shutdown."""
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
