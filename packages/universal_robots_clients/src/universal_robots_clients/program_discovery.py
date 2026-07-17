"""Discover Universal Robots program files through local filesystems or SFTP.

All discovery functions recursively find case-insensitive ``.urp`` files, return paths relative to the supplied root, normalize separators to forward slashes,
and sort results deterministically. ``discover_local_programs()`` uses ``pathlib``. ``discover_sftp_programs()`` traverses an already connected SFTP client so
connection ownership and authentication can remain with the caller. ``discover_programs_over_sftp()`` is a convenience operation for simple applications.

The convenience operation makes unknown-host-key trust an explicit argument and imports Paramiko only when called. The package's base installation can therefore
perform local discovery without Paramiko, while callers selecting SFTP choose authentication, endpoint, timeout, and host-key behavior deliberately.

This module depends on standard-library path and file-mode handling, with optional Paramiko used only by the connection convenience function. It has no knowledge
of Dashboard, RTDE, OPC UA, command-line parsing, passwords in environment variables, or application workflows.
"""

import pathlib
import stat
import typing

__all__ = ["discover_local_programs", "discover_programs_over_sftp", "discover_sftp_programs"]

DEFAULT_SFTP_PORT = 22
DEFAULT_SFTP_TIMEOUT = 5.0
_URP_SUFFIX = ".urp"


def _is_urp(path: pathlib.PurePath) -> bool:
    """Return whether one path has a case-insensitive URP suffix."""
    return path.suffix.lower() == _URP_SUFFIX


def discover_local_programs(root: typing.Union[str, pathlib.Path]) -> typing.List[str]:
    """Return all URP paths beneath one local root.

    Used by applications and tools that can access a mounted or copied UR program directory, including ``ur_dashboard_to_opcua_gateway``.
    """
    folder = pathlib.Path(root)
    paths = folder.rglob("*")
    programs = (path.relative_to(folder) for path in paths if path.is_file() and _is_urp(path))

    return sorted(path.as_posix() for path in programs)


def _walk_sftp_programs(sftp: typing.Any, root: pathlib.PurePosixPath, folder: pathlib.PurePosixPath) -> typing.Iterator[str]:
    """Recursively yield normalized URP paths through an SFTP client."""
    for entry in sftp.listdir_attr(str(folder)):
        path = folder / entry.filename
        mode = entry.st_mode or 0

        if stat.S_ISDIR(mode):
            yield from _walk_sftp_programs(sftp, root, path)
        elif _is_urp(path):
            yield path.relative_to(root).as_posix()


def discover_sftp_programs(sftp: typing.Any, root: typing.Union[str, pathlib.PurePosixPath]) -> typing.List[str]:
    """Return all URP paths through a caller-owned connected SFTP client.

    Used by SFTP-capable applications and by ``discover_programs_over_sftp()``.
    """
    folder = pathlib.PurePosixPath(root)

    return sorted(_walk_sftp_programs(sftp, folder, folder))


def discover_programs_over_sftp(
    host: str,
    root: typing.Union[str, pathlib.PurePosixPath],
    username: str,
    password: str,
    port: int = DEFAULT_SFTP_PORT,
    timeout: float = DEFAULT_SFTP_TIMEOUT,
    trust_unknown_host_keys: bool = False,
) -> typing.List[str]:
    """Connect over SFTP, discover URP files, and close the connection.

    Used by applications that prefer a one-call SFTP operation, including ``ur_dashboard_to_opcua_gateway`` while its current insecure host-key policy remains
    an explicit application decision.
    """
    import paramiko

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()

    if trust_unknown_host_keys:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(host, port=port, username=username, password=password, timeout=timeout)

    with ssh:
        with ssh.open_sftp() as sftp:
            return discover_sftp_programs(sftp, root)
