"""Test the gateway against real URSim, SFTP, and OPC UA services."""

import sys
import typing

import asyncua.sync
import pytest
import ur_dashboard_to_opcua_gateway._07_expose_program_commands_via_opcua as expose_program_commands_via_opcua

if sys.version_info < (3, 10):
    pytest.skip("Container-backed system tests require Python 3.10 or newer.", allow_module_level=True)

pytest.importorskip("testcontainers", reason="Install the system-test extra to run container-backed tests.")

import tests.robot_lab as robot_lab_module

OPC_NAMESPACE = expose_program_commands_via_opcua.OPC_NAMESPACE


def child(parent: asyncua.sync.SyncNode, namespace: int, name: str) -> asyncua.sync.SyncNode:
    """Return one child using the gateway namespace resolved at runtime."""
    path = f"{namespace}:{name}"

    return parent.get_child([path])


def call(parent: asyncua.sync.SyncNode, namespace: int, name: str, *arguments: str) -> object:
    """Call an OPC UA method beneath one object node."""
    method = child(parent, namespace, name)

    return parent.call_method(method, *arguments)


def robot_node(client: asyncua.sync.Client) -> typing.Tuple[int, asyncua.sync.SyncNode]:
    """Return the gateway robot object and its dynamically assigned namespace."""
    namespace = client.get_namespace_index(OPC_NAMESPACE)
    nodes = client.nodes
    robot = child(nodes.objects, namespace, "UR20")

    return namespace, robot


def verify_gateway(lab: robot_lab_module.RobotLab, endpoint: str, expected: typing.List[str]) -> None:
    """Verify generic and dynamic methods against real external services."""
    lab.ursim.prepare_robot()

    try:
        client_context = asyncua.sync.Client(endpoint)

        with client_context as client:
            namespace, robot = robot_node(client)
            programs = call(robot, namespace, "programs")
            assert programs == expected

            status = call(robot, namespace, "status")
            assert isinstance(status, str)

            loaded = call(robot, namespace, "load", "Main.urp")
            assert isinstance(loaded, str)
            loaded_lower = loaded.lower()
            assert "loading" in loaded_lower
            assert "error" not in loaded_lower

            direct_loaded = lab.ursim.command("get loaded program")
            assert "Main.urp" in direct_loaded

            started = call(robot, namespace, "start")
            assert isinstance(started, str)
            started_lower = started.lower()
            assert "starting" in started_lower
            assert "failed" not in started_lower
            lab.ursim.wait_for_program_state("PLAYING")

            paused = call(robot, namespace, "pause")
            assert isinstance(paused, str)
            lab.ursim.wait_for_program_state("PAUSED")

            stopped = call(robot, namespace, "stop")
            assert isinstance(stopped, str)
            lab.ursim.wait_for_program_state("STOPPED")

            shortcuts = child(robot, namespace, "ProgramShortcuts")
            main = child(shortcuts, namespace, "Main.urp")
            shortcut_loaded = call(main, namespace, "load")
            assert isinstance(shortcut_loaded, str)
            shortcut_lower = shortcut_loaded.lower()
            assert "loading" in shortcut_lower
            assert "error" not in shortcut_lower

            production = child(shortcuts, namespace, "Production")
            pick = child(production, namespace, "PickPart.urp")
            run = call(pick, namespace, "run")
            assert isinstance(run, str)
            run_lower = run.lower()
            assert "loading" in run_lower
            assert "starting" in run_lower
            assert "error" not in run_lower
            assert "failed" not in run_lower
            lab.ursim.wait_for_program_state("PLAYING")

            shortcut_program = lab.ursim.command("get loaded program")
            assert "PickPart.urp" in shortcut_program

            stopped = call(robot, namespace, "stop")
            assert isinstance(stopped, str)
            lab.ursim.wait_for_program_state("STOPPED")
    finally:
        lab.ursim.command("stop")


@pytest.mark.system
@pytest.mark.parametrize("catalogue", ["local", "sftp"])
def test_gateway_system(robot_lab: robot_lab_module.RobotLab, expected_programs: typing.List[str], catalogue: str) -> None:
    """Run the same real system contract for local and SFTP program discovery."""
    gateway = robot_lab.gateway(catalogue)
    verify_gateway(robot_lab, gateway.endpoint, expected_programs)
