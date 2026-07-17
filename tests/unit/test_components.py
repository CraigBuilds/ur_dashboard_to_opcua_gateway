"""Test gateway functions, composition, and process lifecycle in isolation."""

import functools
import gzip
import inspect
import pathlib
import typing
import xml.etree.ElementTree

import pytest
import ur_dashboard_to_opcua_gateway._01_main as main_module
import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args
import ur_dashboard_to_opcua_gateway._03_compose_gateway as compose_gateway
import ur_dashboard_to_opcua_gateway._04_discover_ur_programs as discover_ur_programs
import ur_dashboard_to_opcua_gateway._05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde as control_ur_programs_and_exchange_parameters
import ur_dashboard_to_opcua_gateway._06_combine_program_discovery_and_control as combine_program_discovery_and_control
import ur_dashboard_to_opcua_gateway._07_expose_program_commands_via_opcua as expose_program_commands_via_opcua

import tests.support.program_fixture as program_fixture


def test_local_catalogue(tmp_path: pathlib.Path) -> None:
    """Select package-backed local discovery and preserve relative paths."""
    nested = tmp_path / "Production"
    nested.mkdir()
    (tmp_path / "Main.urp").touch()
    (nested / "Pick.URP").touch()
    (tmp_path / "notes.txt").touch()
    args = parse_command_line_args.Args(catalog="local", programs_folder=str(tmp_path))

    assert discover_ur_programs.discover_programs(args) == ["Main.urp", "Production/Pick.URP"]


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


def test_component_configuration(tmp_path: pathlib.Path) -> None:
    """Configure discovery and Dashboard functions with interface-ready signatures."""
    args = parse_command_line_args.Args(catalog="local", programs_folder=str(tmp_path), dashboard_host="dashboard", dashboard_port=30000)
    discover_programs_function = functools.partial(discover_ur_programs.discover_programs, args)
    dashboard_commands = control_ur_programs_and_exchange_parameters.create_dashboard_commands(args)

    assert discover_programs_function() == []
    assert set(dashboard_commands) == {"load_program", "play_program", "pause_program", "stop_program", "get_program_state"}
    assert list(inspect.signature(dashboard_commands["load_program"]).parameters) == ["program"]
    assert all(not inspect.signature(dashboard_commands[name]).parameters for name in ("play_program", "pause_program", "stop_program", "get_program_state"))


def test_compose_gateway_wires_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compose configured functions, flat interfaces, and the application server."""
    args = parse_command_line_args.Args(catalog="local")
    dashboard_commands: control_ur_programs_and_exchange_parameters.DashboardCommands = {}
    interfaces = combine_program_discovery_and_control.GatewayInterfaces({}, {}, {})
    server = object()
    discovery_functions: typing.List[typing.Callable[[], typing.List[str]]] = []
    server_calls: typing.List[typing.Tuple[object, str]] = []

    def configured_discovery(actual: parse_command_line_args.Args) -> typing.List[str]:
        """Return programs for the composition test."""
        assert actual is args

        return []

    def create_interfaces(
        actual_discovery: typing.Callable[[], typing.List[str]], actual_dashboard_commands: control_ur_programs_and_exchange_parameters.DashboardCommands
    ) -> combine_program_discovery_and_control.GatewayInterfaces:
        """Capture the configured dependencies."""
        assert actual_dashboard_commands is dashboard_commands
        discovery_functions.append(actual_discovery)

        return interfaces

    def create_server(actual_interfaces: combine_program_discovery_and_control.GatewayInterfaces, endpoint: str) -> object:
        """Capture the composed interfaces."""
        server_calls.append((actual_interfaces, endpoint))

        return server

    monkeypatch.setattr(discover_ur_programs, "discover_programs", configured_discovery)
    monkeypatch.setattr(control_ur_programs_and_exchange_parameters, "create_dashboard_commands", lambda actual: dashboard_commands)
    monkeypatch.setattr(combine_program_discovery_and_control, "create_interfaces", create_interfaces)
    monkeypatch.setattr(expose_program_commands_via_opcua, "create_server", create_server)

    result = compose_gateway.compose_gateway(args)

    assert result is server
    assert server_calls == [(interfaces, args.opcua_endpoint)]
    assert len(discovery_functions) == 1
    configured_discovery_function = discovery_functions[0]
    assert isinstance(configured_discovery_function, functools.partial)
    assert configured_discovery_function.func is configured_discovery
    assert configured_discovery_function.args == (args,)


def test_main_owns_process_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parse, compose, and run the managed server from the executable entry point."""
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
