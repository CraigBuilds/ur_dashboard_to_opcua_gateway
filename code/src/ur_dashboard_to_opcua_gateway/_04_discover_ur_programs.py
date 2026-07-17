"""Select and configure reusable Universal Robots program discovery.

This application adapter presents one ``discover_programs(args)`` operation while delegating traversal to ``universal_robots_clients.program_discovery``.
Local configuration becomes a direct local-filesystem call. SFTP configuration becomes a convenience SFTP call with the credentials already resolved by the
command-line module and the gateway's current explicit decision to trust unknown host keys.

Keeping backend selection here prevents the reusable client package from depending on ``Args``, environment-variable names, password prompting, or this
application's insecure MVP policy. Both backends still return the same deterministic list of relative, forward-slash URP paths.

The public API is ``discover_programs()``. This module depends on ``_02_parse_command_line_args`` and
``universal_robots_clients.program_discovery`` but knows nothing about Dashboard, RTDE, application command construction, or OPC UA.
"""

import typing

import universal_robots_clients.program_discovery as program_discovery

import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args

__all__ = ["discover_programs"]


def discover_programs(args: parse_command_line_args.Args) -> typing.List[str]:
    """Discover the UR programs selected by gateway configuration.

    Used by ``_03_compose_gateway.compose_gateway()`` through a configured partial function.
    """
    if args.catalog == "local":
        return program_discovery.discover_local_programs(args.programs_folder)

    if args.catalog != "sftp":
        raise ValueError(f"Unsupported catalogue: {args.catalog}")

    if args.robot_host is None:
        raise ValueError("Robot host is required for SFTP discovery.")

    if args.robot_password is None:
        raise ValueError("Robot password is required for SFTP discovery.")

    return program_discovery.discover_programs_over_sftp(
        host=args.robot_host,
        root=args.programs_folder,
        username=args.sftp_username,
        password=args.robot_password,
        port=args.sftp_port,
        trust_unknown_host_keys=True,
    )
