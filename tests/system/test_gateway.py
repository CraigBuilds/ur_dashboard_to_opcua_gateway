"""Test the rewritten gateway against real URSim, SFTP, and OPC UA services."""

import sys
import time
import typing

import asyncua.sync
import pytest
import ur_dashboard_to_opcua_gateway.gateway as compose_gateway

if sys.version_info < (3, 10):
    pytest.skip("Container-backed system tests require Python 3.10 or newer.", allow_module_level=True)

pytest.importorskip("testcontainers", reason="Install the system-test extra to run container-backed tests.")

import tests.system.robot_lab as robot_lab_module

OPC_NAMESPACE = compose_gateway.OPC_NAMESPACE


def child(parent: asyncua.sync.SyncNode, namespace: int, name: str) -> asyncua.sync.SyncNode:
    """Return one child using the gateway namespace resolved at runtime."""
    return parent.get_child([f"{namespace}:{name}"])


def call(parent: asyncua.sync.SyncNode, namespace: int, name: str, *arguments: object) -> object:
    """Call one OPC UA method beneath an object node."""
    return parent.call_method(child(parent, namespace, name), *arguments)


def robot_node(client: asyncua.sync.Client) -> typing.Tuple[int, asyncua.sync.SyncNode]:
    """Return the gateway robot object and its dynamically assigned namespace."""
    namespace = client.get_namespace_index(OPC_NAMESPACE)

    return namespace, child(client.nodes.objects, namespace, "UR20")


def wait_for_status(node: asyncua.sync.SyncNode, accepts: typing.Callable[[object], bool], description: str) -> object:
    """Wait for one gateway status poll to publish an acceptable value."""
    deadline = time.monotonic() + 10.0

    while time.monotonic() < deadline:
        value = node.read_value()

        if accepts(value):
            return value

        time.sleep(0.1)

    raise AssertionError(f"{description} did not receive the expected polled value.")


def verify_gateway(lab: robot_lab_module.RobotLab, endpoint: str, expected: typing.List[str]) -> None:
    """Verify flat methods and status against real external services."""
    lab.ursim.prepare_robot()

    try:
        with asyncua.sync.Client(endpoint) as client:
            namespace, robot = robot_node(client)
            methods = child(robot, namespace, "Methods")
            status = child(robot, namespace, "Status")
            parameters = child(robot, namespace, "Parameters")
            parameter_names = {node.read_browse_name().Name for node in parameters.get_children()}
            assert parameter_names == {"MoveSpeedPercent", "GripperOutput0", "GripperOutput1"}
            assert isinstance(
                wait_for_status(child(status, namespace, "ProgramState"), lambda value: isinstance(value, str) and bool(value), "ProgramState"), str
            )
            assert wait_for_status(child(status, namespace, "RtdeConnected"), lambda value: value is True, "RtdeConnected") is True

            for name in ("RobotModeCode", "SafetyModeCode", "RuntimeStateCode"):
                assert type(wait_for_status(child(status, namespace, name), lambda value: type(value) is int, name)) is int

            for name in ("ProtectiveStopped", "EmergencyStopped", "GripperInput0", "GripperInput1", "GripperOutput0", "GripperOutput1"):
                assert type(wait_for_status(child(status, namespace, name), lambda value: type(value) is bool, name)) is bool

            for name in ("TcpPose", "TcpSpeed", "TcpForce", "JointPositions", "JointTemperatures"):
                value = wait_for_status(
                    child(status, namespace, name),
                    lambda actual: isinstance(actual, list) and len(actual) == 6 and all(type(item) is float for item in actual),
                    name,
                )
                assert isinstance(value, list)

            for name in ("SpeedSliderPercent", "SpeedScalingPercent"):
                assert type(wait_for_status(child(status, namespace, name), lambda value: type(value) is float, name)) is float

            child(parameters, namespace, "MoveSpeedPercent").write_value(35.0)
            wait_for_status(
                child(status, namespace, "SpeedSliderPercent"), lambda value: type(value) is float and abs(value - 35.0) < 0.1, "SpeedSliderPercent"
            )
            child(parameters, namespace, "GripperOutput0").write_value(True)
            wait_for_status(child(status, namespace, "GripperOutput0"), lambda value: value is True, "GripperOutput0")
            child(parameters, namespace, "GripperOutput0").write_value(False)
            wait_for_status(child(status, namespace, "GripperOutput0"), lambda value: value is False, "GripperOutput0")
            expected_method_names = {"StartProgram_" + "_".join(part.replace(".urp", "") for part in program.split("/")) for program in expected}
            actual_method_names = {node.read_browse_name().Name for node in methods.get_children()}
            assert expected_method_names | {"ListPrograms", "LoadProgram", "RunProgram", "PauseProgram", "StopProgram"} == actual_method_names

            assert call(methods, namespace, "ListPrograms") == expected
            call(methods, namespace, "LoadProgram", "Main.urp")
            assert "Main.urp" in lab.ursim.command("get loaded program")
            call(methods, namespace, "RunProgram")
            lab.ursim.wait_for_program_state("PLAYING")
            call(methods, namespace, "StopProgram")
            lab.ursim.wait_for_program_state("STOPPED")

            call(methods, namespace, "StartProgram_Main")
            lab.ursim.wait_for_program_state("PLAYING")
            assert "Main.urp" in lab.ursim.command("get loaded program")

            call(methods, namespace, "PauseProgram")
            lab.ursim.wait_for_program_state("PAUSED")
            call(methods, namespace, "StopProgram")
            lab.ursim.wait_for_program_state("STOPPED")

            call(methods, namespace, "StartProgram_Production_PickPart")
            lab.ursim.wait_for_program_state("PLAYING")
            assert "PickPart.urp" in lab.ursim.command("get loaded program")
            call(methods, namespace, "StopProgram")
            lab.ursim.wait_for_program_state("STOPPED")
    finally:
        lab.ursim.command("stop")


@pytest.mark.system
@pytest.mark.parametrize("catalogue", ["local", "sftp"])
def test_gateway_system(robot_lab: robot_lab_module.RobotLab, expected_programs: typing.List[str], catalogue: str) -> None:
    """Run the same real system contract for local and SFTP discovery."""
    gateway = robot_lab.gateway(catalogue)
    verify_gateway(robot_lab, gateway.endpoint, expected_programs)
