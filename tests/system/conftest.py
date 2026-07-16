"""Provide shared program and robot-laboratory pytest fixtures."""

import typing

import pytest

import tests.support.program_fixture as program_fixture


@pytest.fixture(scope="session")
def expected_programs() -> typing.List[str]:
    """Provide expected program paths."""
    return ["Main.urp", "Production/PickPart.urp"]


@pytest.fixture(scope="session")
def robot_lab(tmp_path_factory: pytest.TempPathFactory) -> typing.Iterator[typing.Any]:
    """Start one self-contained real-service laboratory for the test session."""
    import tests.system.robot_lab as robot_lab_module

    root = tmp_path_factory.mktemp("robot-programs")
    program_fixture.create_program_tree(root)

    with robot_lab_module.RobotLab(root) as lab:
        yield lab
