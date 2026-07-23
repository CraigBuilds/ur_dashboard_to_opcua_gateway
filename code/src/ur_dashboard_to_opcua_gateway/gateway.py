"""Declare how Universal Robots clients are exposed by the OPC UA server."""

import functools
import typing

import declarative_opcua_server
import universal_robots_clients.dashboard_client as dashboard_client
import universal_robots_clients.rtde_client as rtde_client
import universal_robots_clients.urp_discovery_client as urp_discovery_client

import ur_dashboard_to_opcua_gateway.args as parse_command_line_args

__all__ = ["OPC_NAMESPACE", "compose_gateway"]

OPC_NAMESPACE = "urn:ur20:program-control"


def compose_gateway(args: parse_command_line_args.Args) -> typing.Any:
    """Tie configured robot operations directly to a declarative OPC UA server."""
    programs = urp_discovery_client.catalog(
        args.catalog,
        args.programs_folder,
        start_program=functools.partial(dashboard_client.load_and_play_program, args.dashboard_host, port=args.dashboard_port, timeout=5.0),
        host=args.robot_host,
        username=args.sftp_username,
        password=args.robot_password,
        port=args.sftp_port,
        trust_unknown_host_keys=True,
    )
    rtde_client.configure(args.rtde_host or args.dashboard_host, frequency=args.rtde_frequency)

    return declarative_opcua_server.create_server(
        status_interface={
            "ProgramState": functools.partial(dashboard_client.get_program_state, args.dashboard_host, args.dashboard_port, 5.0),
            "RtdeConnected": rtde_client.is_connected,
            "RobotModeCode": rtde_client.read_robot_mode,
            "SafetyModeCode": rtde_client.read_safety_mode,
            "RuntimeStateCode": rtde_client.read_runtime_state,
            "ProtectiveStopped": rtde_client.is_protective_stopped,
            "EmergencyStopped": rtde_client.is_emergency_stopped,
            "TcpPose": rtde_client.read_actual_tcp_pose,
            "TcpSpeed": rtde_client.read_actual_tcp_speed,
            "TcpForce": rtde_client.read_actual_tcp_force,
            "JointPositions": rtde_client.read_actual_joint_positions,
            "JointTemperatures": rtde_client.read_joint_temperatures,
            "SpeedSliderPercent": rtde_client.read_speed_slider_percent,
            "SpeedScalingPercent": rtde_client.read_speed_scaling_percent,
            "GripperInput0": functools.partial(rtde_client.read_tool_digital_input, 0),
            "GripperInput1": functools.partial(rtde_client.read_tool_digital_input, 1),
            "GripperOutput0": functools.partial(rtde_client.read_tool_digital_output, 0),
            "GripperOutput1": functools.partial(rtde_client.read_tool_digital_output, 1),
        },
        parameter_interface={
            "MoveSpeedPercent": rtde_client.write_speed_slider_percent,
            "GripperOutput0": functools.partial(rtde_client.write_tool_digital_output, 0),
            "GripperOutput1": functools.partial(rtde_client.write_tool_digital_output, 1),
        },
        method_interface={
            "ListPrograms": programs.discover,
            "LoadProgram": functools.partial(dashboard_client.load_program, args.dashboard_host, port=args.dashboard_port, timeout=5.0),
            "RunProgram": functools.partial(dashboard_client.play_program, args.dashboard_host, args.dashboard_port, 5.0),
            "PauseProgram": functools.partial(dashboard_client.pause_program, args.dashboard_host, args.dashboard_port, 5.0),
            "StopProgram": functools.partial(dashboard_client.stop_program, args.dashboard_host, args.dashboard_port, 5.0),
            "RefreshPrograms": declarative_opcua_server.refresh_method(programs.methods),
        },
        endpoint=args.opcua_endpoint,
        namespace=OPC_NAMESPACE,
        root_object="UR20",
    )
