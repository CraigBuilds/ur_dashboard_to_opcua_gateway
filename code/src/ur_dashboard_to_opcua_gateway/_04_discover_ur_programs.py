"""Find UR program files and return a transport-neutral catalogue.

Program discovery is intentionally hidden behind one operation so callers do not need separate local and remote code paths. ``discover_programs(args)`` is the
only public API. It selects the configured backend, searches recursively for case-insensitive ``.urp`` files, converts each match to a path relative to the
configured root, and returns a deterministic sorted list using forward-slash separators.

Local discovery uses ``pathlib`` directly. SFTP discovery uses ``paramiko`` to connect to the robot, walk remote directory entries, and distinguish files from
folders using their mode bits. Paramiko is imported only when SFTP is used, preserving local discovery when the optional dependency is not installed. The
current MVP accepts unknown SSH host keys automatically and authenticates with the credentials already resolved in ``Args``.

This module depends on ``_02_parse_command_line_args`` for configuration and otherwise has no knowledge of Dashboard control, application commands, or OPC UA.
The composition root adapts its argument-taking function into the zero-argument command required by later modules.
"""

from __future__ import annotations

import pathlib
import stat
import typing

import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args

if typing.TYPE_CHECKING:
    import paramiko

__all__ = ["discover_programs"]

_URP_SUFFIX = ".urp"


def _is_urp(path: pathlib.PurePath) -> bool:
    """Return whether a path is a URP file."""
    suffix = path.suffix.lower()

    return suffix == _URP_SUFFIX


def _trust_host_key(ssh: paramiko.SSHClient) -> None:
    """Accept an SSH host key automatically."""
    import paramiko

    policy = paramiko.AutoAddPolicy()
    ssh.set_missing_host_key_policy(policy)


def _discover_local_programs(folder: pathlib.Path) -> typing.List[str]:
    """Discover programs in one local folder."""
    paths = folder.rglob("*")
    programs = (path.relative_to(folder) for path in paths if path.is_file() and _is_urp(path))

    return sorted(path.as_posix() for path in programs)


def _recursive_find_sftp_programs(sftp: paramiko.SFTPClient, root: pathlib.PurePosixPath, folder: pathlib.PurePosixPath) -> typing.Iterator[str]:
    """Recursively yield programs in one SFTP folder."""
    entries = sftp.listdir_attr(str(folder))

    for entry in entries:
        path = folder / entry.filename
        mode = entry.st_mode or 0

        if stat.S_ISDIR(mode):
            yield from _recursive_find_sftp_programs(sftp, root, path)
            continue

        if _is_urp(path):
            relative = path.relative_to(root)
            yield str(relative)


def _discover_sftp_programs(host: str, password: str, folder: pathlib.PurePosixPath, port: int, username: str) -> typing.List[str]:
    """Discover programs through SSH and SFTP."""
    import paramiko

    ssh = paramiko.SSHClient()
    _trust_host_key(ssh)
    ssh.connect(host, port=port, username=username, password=password)

    with ssh:
        with ssh.open_sftp() as sftp:
            programs = _recursive_find_sftp_programs(sftp, folder, folder)
            result = sorted(programs)

    return result


def discover_programs(args: parse_command_line_args.Args) -> typing.List[str]:
    """Discover configured UR programs.

    Used by ``_03_compose_gateway.compose_gateway()`` through a configured partial function.
    """
    if args.catalog == "local":
        folder = pathlib.Path(args.programs_folder)

        return _discover_local_programs(folder)

    if args.catalog != "sftp":
        message = f"Unsupported catalogue: {args.catalog}"
        raise ValueError(message)

    if args.robot_host is None:
        message = "Robot host is required for SFTP discovery."
        raise ValueError(message)

    if args.robot_password is None:
        message = "Robot password is required for SFTP discovery."
        raise ValueError(message)

    folder = pathlib.PurePosixPath(args.programs_folder)

    return _discover_sftp_programs(args.robot_host, args.robot_password, folder, args.sftp_port, args.sftp_username)
