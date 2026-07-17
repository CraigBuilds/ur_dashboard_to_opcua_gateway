"""Test the rewritten gateway against real URSim, SFTP, and OPC UA services."""

import sys
import time
import typing

import asyncua.sync
import pytest
import ur_dashboard_to_opcua_gateway._03_compose_gateway as compose_gateway

if sys.version_info < (3, 10):
    pytest.skip("Container-backed system tests require Python 3.10 or newer.", allow_module_level=True)

pytest.importorskip("testcontainers", reason="Install the system-test extra to run container-backed tests.")

import tests.system.robot_lab as robot_lab_module

OPC_NAMESPACE = compose_gateway.OPC_NAMESPACE


def child(parent: asyncua.sync.SyncNode, namespace: int, name: str) -> asyncua.sync.SyncNode:
    """Return one child using the gateway namespace resolved at runtime."""
    return parent.get_child([f"{namespace}:{name}"])


def call(parent: asyncua.sync.SyncNode, namespace: int, name: str) -> object:
    """Call one no-argument OPC UA method beneath an object node."""
    return parent.call_method(child(parent, namespace, name))


def robot_node(client: asyncua.sync.Client) -> typing.Tuple[int, asyncua.sync.SyncNode]:
    """Return the gateway robot object and its dynamically assigned namespace."""
    namespace = client.get_namespace_index(OPC_NAMESPACE)

    return namespace, child(client.nodes.objects, namespace, "UR20")


def wait_for_status(node: asyncua.sync.SyncNode) -> str:
    """Wait for the gateway's Dashboard-backed status poll to publish text."""
    deadline = time.monotonic() + 10.0

    while time.monotonic() < deadline:
        value = node.read_value()

        if isinstance(value, str) and value:
            return value

        time.sleep(0.1)

    raise AssertionError("ProgramState did not receive a polled Dashboard value.")


def verify_gateway(lab: robot_lab_module.RobotLab, endpoint: str, expected: typing.List[str]) -> None:
    """Verify flat methods and status against real external services."""
    lab.ursim.prepare_robot()

    try:
        with asyncua.sync.Client(endpoint) as client:
            namespace, robot = robot_node(client)
            methods = child(robot, namespace, "Methods")
            status = child(robot, namespace, "Status")
            parameters = child(robot, namespace, "Parameters")
            assert parameters.get_children() == []
            assert isinstance(wait_for_status(child(status, namespace, "ProgramState")), str)
            expected_method_names = {"StartProgram_" + "_".join(part.replace(".urp", "") for part in program.split("/")) for program in expected}
            actual_method_names = {node.read_browse_name().Name for node in methods.get_children()}
            assert expected_method_names | {"PauseProgram", "StopProgram"} == actual_method_names

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
