"""Verify the reusable RTDE client against a real URSim controller."""

import sys

import pytest
import universal_robots_clients.rtde as rtde

if sys.version_info < (3, 10):
    pytest.skip("Container-backed system tests require Python 3.10 or newer.", allow_module_level=True)

pytest.importorskip("testcontainers", reason="Install the system-test extra to run container-backed tests.")

import tests.system.robot_lab as robot_lab_module


@pytest.mark.system
def test_rtde_client_connects_and_exchanges_typed_registers(robot_lab: robot_lab_module.RobotLab) -> None:
    """Connect both native interfaces and exercise real upper-range recipes."""
    client = rtde.connect(robot_lab.ursim.host, frequency=20.0)

    try:
        assert rtde.is_connected(client)
        assert type(rtde.read_output_int_register(client, 42)) is int
        assert type(rtde.read_output_double_register(client, 42)) is float
        rtde.write_input_int_register(client, 42, 123)
        rtde.write_input_double_register(client, 42, 1.25)
    finally:
        rtde.disconnect(client)

    assert not rtde.is_connected(client)
