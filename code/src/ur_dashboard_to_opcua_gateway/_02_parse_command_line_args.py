"""Define and resolve all configuration accepted by ``ur_dashboard_to_opcua_gateway``.

This module is the package's configuration boundary. It translates command-line options, environment values, defaults, and validation rules into one immutable
``Args`` dataclass so downstream modules consume resolved values rather than understanding ``argparse`` or prompting for credentials themselves. Local
catalogues require only a program folder; SFTP catalogues additionally require a robot host and obtain the password from ``UR_ROBOT_PASSWORD`` or an interactive
prompt. The Dashboard host defaults to the SFTP robot host when appropriate.

The public API consists of ``Args``, the shared configuration value object, and ``parse_args()``, which builds and executes the parser. Parser construction,
password acquisition, and default resolution are internal helpers.

This foundational module depends only on the Python standard library. It is consumed by ``_01_main``, the composition root, program discovery, and Dashboard
control, but imports none of those modules; that direction keeps the package dependency graph acyclic.
"""

import argparse
import dataclasses
import getpass
import os
import typing

__all__ = ["Args", "parse_args"]

_DEFAULT_PROGRAMS_FOLDER = "/programs"
_DEFAULT_SFTP_PORT = 22
_DEFAULT_SFTP_USERNAME = "root"
_DEFAULT_DASHBOARD_HOST = "127.0.0.1"
_DEFAULT_DASHBOARD_PORT = 29999
_DEFAULT_OPCUA_ENDPOINT = "opc.tcp://0.0.0.0:4840/ur20/"
_PASSWORD_VARIABLE = "UR_ROBOT_PASSWORD"


@dataclasses.dataclass(frozen=True)
class Args:
    """Resolved gateway configuration.

    Used by ``_01_main``, ``_03_compose_gateway``, ``_04_discover_ur_programs``, and ``_05_control_ur_programs_via_dashboard``.
    """

    catalog: str
    programs_folder: str = _DEFAULT_PROGRAMS_FOLDER
    robot_host: typing.Optional[str] = None
    robot_password: typing.Optional[str] = None
    sftp_port: int = _DEFAULT_SFTP_PORT
    sftp_username: str = _DEFAULT_SFTP_USERNAME
    dashboard_host: str = _DEFAULT_DASHBOARD_HOST
    dashboard_port: int = _DEFAULT_DASHBOARD_PORT
    opcua_endpoint: str = _DEFAULT_OPCUA_ENDPOINT


def _create_parser() -> argparse.ArgumentParser:
    """Create the gateway command-line parser."""
    parser = argparse.ArgumentParser(description="Expose UR programs through OPC UA.")
    parser.add_argument("--catalog", choices=("local", "sftp"), required=True, help="Choose local filesystem or SFTP program discovery.")
    parser.add_argument("--programs-folder", default=_DEFAULT_PROGRAMS_FOLDER, help="Set the root folder searched recursively for UR program files.")
    parser.add_argument("--robot-host", help="Set the robot host used for SFTP discovery; required with --catalog sftp.")
    parser.add_argument("--sftp-port", type=int, default=_DEFAULT_SFTP_PORT, help="Set the robot SFTP port.")
    parser.add_argument("--sftp-username", default=_DEFAULT_SFTP_USERNAME, help="Set the robot SFTP username.")
    parser.add_argument("--dashboard-host", help="Set the Dashboard Server host; defaults to the robot host for SFTP or 127.0.0.1 for local discovery.")
    parser.add_argument("--dashboard-port", type=int, default=_DEFAULT_DASHBOARD_PORT, help="Set the Dashboard Server port.")
    parser.add_argument("--opcua-endpoint", default=_DEFAULT_OPCUA_ENDPOINT, help="Set the OPC UA server endpoint URL.")

    return parser


def _read_robot_password() -> str:
    """Read the SFTP password from the environment or an interactive prompt."""
    password = os.getenv(_PASSWORD_VARIABLE)

    if password is not None:
        return password

    return getpass.getpass("Robot password: ")


def _dashboard_host(parsed: argparse.Namespace) -> str:
    """Resolve the Dashboard Server host."""
    if parsed.dashboard_host:
        return parsed.dashboard_host

    if parsed.catalog == "sftp":
        return parsed.robot_host

    return _DEFAULT_DASHBOARD_HOST


def parse_args(arguments: typing.Optional[typing.Sequence[str]] = None) -> Args:
    """Parse command-line arguments into resolved configuration.

    Used by ``_01_main.main()``.
    """
    parser = _create_parser()
    parsed = parser.parse_args(arguments)

    if parsed.catalog == "sftp" and not parsed.robot_host:
        parser.error("--robot-host is required for an SFTP catalogue.")

    password = _read_robot_password() if parsed.catalog == "sftp" else None

    return Args(
        catalog=parsed.catalog,
        programs_folder=parsed.programs_folder,
        robot_host=parsed.robot_host,
        robot_password=password,
        sftp_port=parsed.sftp_port,
        sftp_username=parsed.sftp_username,
        dashboard_host=_dashboard_host(parsed),
        dashboard_port=parsed.dashboard_port,
        opcua_endpoint=parsed.opcua_endpoint,
    )
