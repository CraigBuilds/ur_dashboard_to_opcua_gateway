"""Test gateway composition and process lifecycle in isolation."""

import gzip
import pathlib
import typing
import unittest.mock
import xml.etree.ElementTree

import pytest
import universal_robots_clients.rtde_client as rtde_client
import ur_dashboard_to_opcua_gateway.main as main_module
import ur_dashboard_to_opcua_gateway.args as parse_command_line_args
import ur_dashboard_to_opcua_gateway.gateway as compose_gateway

import tests.support.program_fixture as program_fixture


def test_local_command_line_args() -> None:
    """Resolve local catalogue defaults without requesting robot credentials."""
    args = parse_command_line_args.parse_args(["--catalog", "local"])

    assert args == parse_command_line_args.Args(catalog="local")


def test_sftp_command_line_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve SFTP credentials and use the robot as the default Dashboard host."""
    monkeypatch.setenv("UR_ROBOT_PASSWORD", "secret")
    args = parse_command_line_args.parse_args(["--catalog", "sftp", "--robot-host", "robot"])

    assert args.robot_host == "robot"
    assert args.robot_password == "secret"
    assert args.dashboard_host == "robot"


def test_compose_gateway_supplies_flat_interfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supply gateway identity and flat callable interfaces to the OPC UA package."""
    args = parse_command_line_args.Args(catalog="local", opcua_endpoint="opc.tcp://127.0.0.1:5000/gateway/")
    server = object()
    client = rtde_client.Client(unittest.mock.MagicMock(), unittest.mock.MagicMock(), 42, 46)
    captured: typing.Dict[str, object] = {}

    def create_server(**configuration: object) -> object:
        """Capture one reusable server creation."""
        captured.update(configuration)

        return server

    monkeypatch.setattr(compose_gateway.urp_discovery_client, "discover_programs", lambda *arguments, **keywords: ["Main.urp"])
    connect = unittest.mock.MagicMock(return_value=client)
    monkeypatch.setattr(compose_gateway.rtde_client, "connect", connect)
    monkeypatch.setattr(compose_gateway.declarative_opcua_server, "create_server", create_server)

    result = compose_gateway.compose_gateway(args)

    assert result.server is server
    connect.assert_called_once_with(args.dashboard_host, frequency=10.0)
    assert set(typing.cast(typing.Dict[str, object], captured["status_interface"])) == {
        "ProgramState",
        "RtdeConnected",
        "RobotModeCode",
        "SafetyModeCode",
        "RuntimeStateCode",
        "ProtectiveStopped",
        "EmergencyStopped",
        "TcpPose",
        "TcpSpeed",
        "TcpForce",
        "JointPositions",
        "JointTemperatures",
        "SpeedSliderPercent",
        "SpeedScalingPercent",
        "GripperInput0",
        "GripperInput1",
        "GripperOutput0",
        "GripperOutput1",
    }
    assert set(typing.cast(typing.Dict[str, object], captured["parameter_interface"])) == {"MoveSpeedPercent", "GripperOutput0", "GripperOutput1"}
    assert set(typing.cast(typing.Dict[str, object], captured["method_interface"])) == {
        "ListPrograms",
        "LoadProgram",
        "RunProgram",
        "PauseProgram",
        "StopProgram",
        "StartProgram_Main",
    }
    assert captured["endpoint"] == args.opcua_endpoint
    assert captured["namespace"] == compose_gateway.OPC_NAMESPACE
    assert captured["root_object"] == "UR20"


def test_composed_interfaces_pass_real_declarative_type_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Build the actual server so every bound RTDE callback annotation is validated."""
    receiver = unittest.mock.MagicMock()
    writer = unittest.mock.MagicMock()
    client = rtde_client.Client(receiver, writer, 42, 46)
    monkeypatch.setattr(compose_gateway.rtde_client, "connect", lambda *arguments, **keywords: client)

    gateway = compose_gateway.compose_gateway(
        parse_command_line_args.Args(catalog="local", programs_folder=str(tmp_path), opcua_endpoint="opc.tcp://127.0.0.1:5001/type-validation/")
    )

    try:
        assert gateway.rtde is client
        assert gateway.server is not None
    finally:
        gateway.server.tloop.stop()
        rtde_client.disconnect(client)


def test_main_owns_process_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parse, compose, and run the resource-owning gateway from the executable entry point."""
    args = parse_command_line_args.Args(catalog="local")
    server = object()
    started: typing.List[object] = []

    monkeypatch.setattr(parse_command_line_args, "parse_args", lambda: args)
    monkeypatch.setattr(compose_gateway, "compose_gateway", lambda actual: server)
    monkeypatch.setattr(main_module, "_run_until_stopped", lambda actual: started.append(actual))

    main_module.main()

    assert started == [server]


def test_program_fixture(tmp_path: pathlib.Path) -> None:
    """Generate a readable no-motion PolyScope program."""
    program = program_fixture.write_program(tmp_path, "Main")
    content = gzip.decompress(program.read_bytes())
    root = xml.etree.ElementTree.fromstring(content)
    main = root.find("./children/MainProgram")

    assert root.tag == "URProgram"
    assert root.attrib["name"] == "Main"
    assert main is not None
    wait = main.find("./children/Wait")
    assert wait is not None
    assert wait.attrib["type"] == "Sleep"
    assert wait.findtext("waitTime") == str(program_fixture.RUN_SECONDS)
    assert root.find(".//Move") is None
