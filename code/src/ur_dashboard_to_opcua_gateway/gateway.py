"""
This is the package's composition root. It wires resolved configuration, program discovery, Dashboard methods, persistent RTDE telemetry and controls, and the
declarative OPC UA server into one context-managed gateway. It does not run that gateway; process signals and waiting belong to ``main.py``.
"""

import dataclasses
import functools
import pathlib
import re
import types
import typing

import declarative_opcua_server
import universal_robots_clients.dashboard_client as dashboard_client
import universal_robots_clients.rtde_client as rtde_client
import universal_robots_clients.urp_discovery_client as urp_discovery_client

import ur_dashboard_to_opcua_gateway.args as parse_command_line_args

__all__ = ["OPC_NAMESPACE", "compose_gateway"]

OPC_NAMESPACE = "urn:ur20:program-control"
_ROOT_OBJECT = "UR20"
_DASHBOARD_TIMEOUT = 5.0


@dataclasses.dataclass(frozen=True)
class _Gateway:
    """Own the configured OPC UA server and its persistent RTDE connection."""

    server: typing.Any
    rtde: rtde_client.Client

    def __enter__(self) -> "_Gateway":
        """Start the OPC UA server while retaining the already-connected RTDE client."""
        try:
            self.server.__enter__()
        except BaseException:
            rtde_client.disconnect(self.rtde)
            raise

        return self

    def __exit__(
        self,
        exception_type: typing.Optional[typing.Type[BaseException]],
        exception: typing.Optional[BaseException],
        traceback: typing.Optional[types.TracebackType],
    ) -> typing.Optional[bool]:
        """Stop OPC UA polling before disconnecting both RTDE interfaces."""
        try:
            return typing.cast(typing.Optional[bool], self.server.__exit__(exception_type, exception, traceback))
        finally:
            rtde_client.disconnect(self.rtde)


def _program_method_name(program: str) -> str:
    """Convert a relative URP path into one deterministic flat method name."""
    path = pathlib.PurePosixPath(program)
    normalized = (re.sub(r"[^A-Za-z0-9]+", "_", part).strip("_") for part in path.with_suffix("").parts)
    meaningful = [part for part in normalized if part]

    if not meaningful:
        raise ValueError(f"Program path cannot produce a method name: {program!r}")

    return "StartProgram_" + "_".join(meaningful)


def _read_speed_slider_percent(client: rtde_client.Client) -> float:
    """Convert the controller's requested speed fraction to an OPC UA percentage."""
    return rtde_client.read_speed_slider_fraction(client) * 100.0


def _read_speed_scaling_percent(client: rtde_client.Client) -> float:
    """Convert effective controller speed scaling to an OPC UA percentage."""
    return rtde_client.read_speed_scaling(client) * 100.0


def _write_move_speed_percent(client: rtde_client.Client, percent: float) -> None:
    """Validate and convert an OPC UA move-speed percentage to an RTDE fraction."""
    rtde_client.write_speed_slider_fraction(client, percent / 100.0)


def _write_gripper_output(client: rtde_client.Client, channel: int, value: bool) -> None:
    """Forward a gateway gripper command to one physical tool digital output."""
    rtde_client.write_tool_digital_output(client, channel, value)


def compose_gateway(args: parse_command_line_args.Args) -> _Gateway:
    """Compose package operations into a gateway that owns OPC UA and RTDE."""

    # Reuse one configured callable for startup method generation and the live ListPrograms method.
    discover_programs = functools.partial(
        urp_discovery_client.discover_programs,
        args.catalog,
        args.programs_folder,
        host=args.robot_host,
        username=args.sftp_username,
        password=args.robot_password,
        port=args.sftp_port,
        trust_unknown_host_keys=True,
    )

    # Fixed method callables are created once so refreshes preserve their OPC UA nodes and NodeIds. Generated methods are cached by both exposed name and source
    # path; an unchanged program therefore keeps its node, while a rename that normalizes to the same name replaces the bound Dashboard callback.
    fixed_methods: typing.Dict[str, typing.Callable[..., typing.Any]] = {
        "ListPrograms": discover_programs,
        "LoadProgram": functools.partial(dashboard_client.load_program, args.dashboard_host, port=args.dashboard_port, timeout=_DASHBOARD_TIMEOUT),
        "RunProgram": functools.partial(dashboard_client.play_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
        "PauseProgram": functools.partial(dashboard_client.pause_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
        "StopProgram": functools.partial(dashboard_client.stop_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
    }
    generated_methods: typing.Dict[str, typing.Tuple[str, typing.Callable[..., typing.Any]]] = {}
    server_holder: typing.Dict[str, typing.Any] = {}

    def build_method_interface(programs: typing.List[str]) -> typing.Dict[str, typing.Callable[..., typing.Any]]:
        """Build the complete desired method interface while retaining unchanged callbacks."""
        named_programs = [(_program_method_name(program), program) for program in programs]

        if len({name for name, _program in named_programs}) != len(named_programs):
            raise ValueError("Discovered program paths produce duplicate OPC UA method names.")

        refreshed: typing.Dict[str, typing.Tuple[str, typing.Callable[..., typing.Any]]] = {}

        for name, program in named_programs:
            previous = generated_methods.get(name)
            method = (
                previous[1]
                if previous is not None and previous[0] == program
                else functools.partial(dashboard_client.load_and_play_program, args.dashboard_host, program, args.dashboard_port, _DASHBOARD_TIMEOUT)
            )
            refreshed[name] = (program, method)

        generated_methods.clear()
        generated_methods.update(refreshed)

        return {**fixed_methods, "RefreshPrograms": refresh_programs, **{name: method for name, (_program, method) in refreshed.items()}}

    def refresh_programs() -> typing.List[str]:
        """Rediscover programs and make the generated OPC UA methods match the result."""
        programs = discover_programs()
        declarative_opcua_server.update_method_interface(server_holder["server"], build_method_interface(programs))

        return programs

    # Validate the initial catalogue before opening the persistent RTDE connection.
    programs = discover_programs()
    method_interface = build_method_interface(programs)

    # RTDE is a streaming protocol, so one client stays connected for the whole gateway lifetime. A separate host is useful when Dashboard is port-forwarded;
    # the normal case simply reuses the Dashboard host.
    client = rtde_client.connect(args.rtde_host or args.dashboard_host, frequency=args.rtde_frequency)

    try:
        server = declarative_opcua_server.create_server(
            # Every status callback is argument-free after partial binding. The declarative server infers each OPC UA data type from its return annotation and
            # polls the callbacks while the server is running. Vector order and units are documented in the README.
            status_interface={
                "ProgramState": functools.partial(dashboard_client.get_program_state, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
                "RtdeConnected": functools.partial(rtde_client.is_connected, client),
                "RobotModeCode": functools.partial(rtde_client.read_robot_mode, client),
                "SafetyModeCode": functools.partial(rtde_client.read_safety_mode, client),
                "RuntimeStateCode": functools.partial(rtde_client.read_runtime_state, client),
                "ProtectiveStopped": functools.partial(rtde_client.is_protective_stopped, client),
                "EmergencyStopped": functools.partial(rtde_client.is_emergency_stopped, client),
                "TcpPose": functools.partial(rtde_client.read_actual_tcp_pose, client),
                "TcpSpeed": functools.partial(rtde_client.read_actual_tcp_speed, client),
                "TcpForce": functools.partial(rtde_client.read_actual_tcp_force, client),
                "JointPositions": functools.partial(rtde_client.read_actual_joint_positions, client),
                "JointTemperatures": functools.partial(rtde_client.read_joint_temperatures, client),
                "SpeedSliderPercent": functools.partial(_read_speed_slider_percent, client),
                "SpeedScalingPercent": functools.partial(_read_speed_scaling_percent, client),
                # The tool flange exposes two digital inputs and outputs. This example labels them as gripper signals without assuming a vendor-specific meaning.
                "GripperInput0": functools.partial(rtde_client.read_tool_digital_input, client, 0),
                "GripperInput1": functools.partial(rtde_client.read_tool_digital_input, client, 1),
                "GripperOutput0": functools.partial(rtde_client.read_tool_digital_output, client, 0),
                "GripperOutput1": functools.partial(rtde_client.read_tool_digital_output, client, 1),
            },
            # Writable parameter nodes call their setter before the declarative server accepts the new OPC UA value. MoveSpeedPercent controls the robot's
            # global speed slider; the two output parameters are portable building blocks for a digitally controlled gripper.
            parameter_interface={
                "MoveSpeedPercent": functools.partial(_write_move_speed_percent, client),
                "GripperOutput0": functools.partial(_write_gripper_output, client, 0),
                "GripperOutput1": functools.partial(_write_gripper_output, client, 1),
            },
            # Methods are request/response operations. RefreshPrograms rediscovers URPs and declaratively replaces this complete mapping on the live server.
            method_interface=method_interface,
            endpoint=args.opcua_endpoint,
            namespace=OPC_NAMESPACE,
            root_object=_ROOT_OBJECT,
        )
    except BaseException:
        rtde_client.disconnect(client)
        raise

    server_holder["server"] = server

    return _Gateway(server, client)
