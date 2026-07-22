"""Test gateway validation, package binding, application policy, and lifecycle."""

import pathlib
import signal
import types
import typing
import unittest.mock

import pytest
import universal_robots_clients.dashboard_client as dashboard_client
import universal_robots_clients.rtde_client as rtde_client
import ur_dashboard_to_opcua_gateway.main as main_module
import ur_dashboard_to_opcua_gateway.args as parse_command_line_args
import ur_dashboard_to_opcua_gateway.gateway as compose_gateway

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

    def prompt_for_password(prompt: str) -> str:
        """Capture the prompt and return one deterministic password."""
        prompts.append(prompt)

        return "prompted-secret"

    monkeypatch.setattr(parse_command_line_args.getpass, "getpass", prompt_for_password)
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
            "--rtde-host",
            "rtde.example",
            "--rtde-frequency",
            "20",
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
    assert args.rtde_host == "rtde.example"
    assert args.rtde_frequency == 20.0


@pytest.mark.parametrize("frequency", [0.0, -1.0, float("nan"), float("inf"), True])
def test_args_reject_invalid_rtde_frequency(frequency: object) -> None:
    """Reject RTDE receive rates that cannot configure a useful stream."""
    with pytest.raises(ValueError, match="RTDE frequency"):
        parse_command_line_args.Args(catalog="local", rtde_frequency=typing.cast(float, frequency))


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

    monkeypatch.setattr(dashboard_client, "load_program", load)
    monkeypatch.setattr(dashboard_client, "play_program", command("play", "played"))
    monkeypatch.setattr(dashboard_client, "pause_program", command("pause", "paused"))
    monkeypatch.setattr(dashboard_client, "stop_program", command("stop", "stopped"))
    monkeypatch.setattr(dashboard_client, "get_program_state", command("state", "STOPPED"))
    receiver = unittest.mock.MagicMock()
    writer = unittest.mock.MagicMock()
    client = rtde_client.Client(receiver, writer, 42, 46)
    receiver.isConnected.return_value = True
    writer.isConnected.return_value = True
    receiver.getRobotMode.return_value = 7
    receiver.getSafetyMode.return_value = 1
    receiver.getRuntimeState.return_value = 2
    receiver.isProtectiveStopped.return_value = False
    receiver.isEmergencyStopped.return_value = False
    receiver.getActualTCPPose.return_value = (0, 1, 2, 3, 4, 5)
    receiver.getActualTCPSpeed.return_value = (1, 2, 3, 4, 5, 6)
    receiver.getActualTCPForce.return_value = (2, 3, 4, 5, 6, 7)
    receiver.getActualQ.return_value = (3, 4, 5, 6, 7, 8)
    receiver.getJointTemperatures.return_value = (30, 31, 32, 33, 34, 35)
    receiver.getTargetSpeedFraction.return_value = 0.8
    receiver.getSpeedScalingCombined.return_value = 0.6
    receiver.getDigitalInState.side_effect = lambda channel: channel == 16
    receiver.getDigitalOutState.side_effect = lambda channel: channel == 17
    writer.setSpeedSlider.return_value = True
    writer.setToolDigitalOut.return_value = True
    connect = unittest.mock.MagicMock(return_value=client)
    monkeypatch.setattr(compose_gateway.rtde_client, "connect", connect)
    args = parse_command_line_args.Args(catalog="local", dashboard_host="robot", dashboard_port=30000, rtde_host="rtde", rtde_frequency=20.0)
    discoveries: typing.List[typing.Tuple[object, ...]] = []

    def discover(
        backend: str,
        root: object,
        host: typing.Optional[str],
        username: str,
        password: typing.Optional[str],
        port: int,
        timeout: float = 5.0,
        trust_unknown_host_keys: bool = False,
    ) -> typing.List[str]:
        discoveries.append((backend, root, host, username, password, port, timeout, trust_unknown_host_keys))

        return ["Main.urp", "Production/Pick Part.urp"]

    monkeypatch.setattr(compose_gateway.urp_discovery_client, "discover_programs", discover)
    monkeypatch.setattr(compose_gateway.declarative_opcua_server, "create_server", lambda **configuration: captured.update(configuration) or object())

    compose_gateway.compose_gateway(args)

    status_interface = typing.cast(typing.Dict[str, typing.Callable[[], object]], captured["status_interface"])
    parameter_interface = typing.cast(typing.Dict[str, typing.Callable[..., None]], captured["parameter_interface"])
    method_interface = typing.cast(typing.Dict[str, typing.Callable[..., object]], captured["method_interface"])
    assert set(parameter_interface) == {"MoveSpeedPercent", "GripperOutput0", "GripperOutput1"}
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
    assert inspect_required_signature_parameters(parameter_interface) == {"percent", "value"}
    assert inspect_required_signature_parameters(method_interface) == {"program"}
    assert {name: reader() for name, reader in status_interface.items()} == {
        "ProgramState": "STOPPED",
        "RtdeConnected": True,
        "RobotModeCode": 7,
        "SafetyModeCode": 1,
        "RuntimeStateCode": 2,
        "ProtectiveStopped": False,
        "EmergencyStopped": False,
        "TcpPose": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        "TcpSpeed": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "TcpForce": [2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        "JointPositions": [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        "JointTemperatures": [30.0, 31.0, 32.0, 33.0, 34.0, 35.0],
        "SpeedSliderPercent": 80.0,
        "SpeedScalingPercent": 60.0,
        "GripperInput0": True,
        "GripperInput1": False,
        "GripperOutput0": False,
        "GripperOutput1": True,
    }
    parameter_interface["MoveSpeedPercent"](40.0)
    parameter_interface["GripperOutput0"](True)
    parameter_interface["GripperOutput1"](False)
    assert method_interface["ListPrograms"]() == ["Main.urp", "Production/Pick Part.urp"]
    assert method_interface["LoadProgram"]("Main.urp") == "loaded"
    assert method_interface["RunProgram"]() == "played"
    method_interface["StartProgram_Production_Pick_Part"]()
    method_interface["PauseProgram"]()
    method_interface["StopProgram"]()
    assert len(discoveries) == 2
    connect.assert_called_once_with("rtde", frequency=20.0)
    writer.setSpeedSlider.assert_called_once_with(0.4)
    assert writer.setToolDigitalOut.call_args_list == [unittest.mock.call(0, True), unittest.mock.call(1, False)]
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
    monkeypatch.setattr(compose_gateway.urp_discovery_client, "discover_programs", lambda *arguments, **keywords: ["Pick-Part.urp", "Pick Part.urp"])
    connect = unittest.mock.MagicMock()
    monkeypatch.setattr(compose_gateway.rtde_client, "connect", connect)

    with pytest.raises(ValueError, match="duplicate"):
        compose_gateway.compose_gateway(args)

    connect.assert_not_called()


def test_gateway_closes_rtde_after_server_and_on_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Own the persistent RTDE connection across normal and failed OPC UA lifecycles."""
    client = unittest.mock.MagicMock()
    server = unittest.mock.MagicMock()
    gateway = compose_gateway._Gateway(server, client)
    disconnect = unittest.mock.MagicMock()
    monkeypatch.setattr(compose_gateway.rtde_client, "disconnect", disconnect)

    with gateway as entered:
        assert entered is gateway
        disconnect.assert_not_called()

    server.__enter__.assert_called_once_with()
    server.__exit__.assert_called_once_with(None, None, None)
    disconnect.assert_called_once_with(client)

    disconnect.reset_mock()
    server.__enter__.side_effect = RuntimeError("port unavailable")

    with pytest.raises(RuntimeError, match="port unavailable"):
        gateway.__enter__()

    disconnect.assert_called_once_with(client)


def test_failed_server_composition_closes_rtde(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid leaking RTDE when declarative OPC UA validation or setup fails."""
    client = unittest.mock.MagicMock()
    disconnect = unittest.mock.MagicMock()
    monkeypatch.setattr(compose_gateway.urp_discovery_client, "discover_programs", lambda *arguments, **keywords: [])
    monkeypatch.setattr(compose_gateway.rtde_client, "connect", lambda *arguments, **keywords: client)
    monkeypatch.setattr(compose_gateway.rtde_client, "disconnect", disconnect)
    monkeypatch.setattr(compose_gateway.declarative_opcua_server, "create_server", unittest.mock.MagicMock(side_effect=RuntimeError("invalid interface")))

    with pytest.raises(RuntimeError, match="invalid interface"):
        compose_gateway.compose_gateway(parse_command_line_args.Args(catalog="local"))

    disconnect.assert_called_once_with(client)


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
