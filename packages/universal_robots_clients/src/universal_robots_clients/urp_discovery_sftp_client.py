"""Discover Universal Robots program files through SFTP.

``discover_programs()`` traverses a caller-owned connected SFTP client. ``connect_and_discover_programs()`` is the convenience API for applications that want
this module to configure Paramiko, open the SSH and SFTP connections, perform discovery, and close both resources. Both operations recursively find
case-insensitive ``.urp`` files and return sorted, normalized paths relative to the supplied root.

Unknown-host-key trust is an explicit argument. By default, Paramiko uses loaded system host keys and rejects unknown hosts; callers must deliberately enable
automatic trust when operating in a controlled environment. Authentication values are ordinary arguments so credential storage and prompting remain
application concerns.

The traversal code depends only on the standard library. ``connect_and_discover_programs()`` imports optional Paramiko when called, allowing the package's base
installation and local discovery client to work without SSH dependencies. The module is used by ``urp_discovery_client`` and can also be imported directly.
"""

import pathlib
import stat
import typing

__all__ = ["connect_and_discover_programs", "discover_programs"]

DEFAULT_PORT = 22
DEFAULT_TIMEOUT = 5.0
_URP_SUFFIX = ".urp"


def _is_urp(path: pathlib.PurePath) -> bool:
    """Return whether one path has a case-insensitive URP suffix."""
    return path.suffix.lower() == _URP_SUFFIX


def _walk_programs(sftp: typing.Any, root: pathlib.PurePosixPath, folder: pathlib.PurePosixPath) -> typing.Iterator[str]:
    """Recursively yield normalized URP paths through an SFTP client."""
    for entry in sftp.listdir_attr(str(folder)):
        path = folder / entry.filename
        mode = entry.st_mode or 0

        if stat.S_ISDIR(mode):
            yield from _walk_programs(sftp, root, path)
        elif _is_urp(path):
            yield path.relative_to(root).as_posix()


def discover_programs(sftp: typing.Any, root: typing.Union[str, pathlib.Path, pathlib.PurePosixPath]) -> typing.List[str]:
    """Return all URP paths through a caller-owned connected SFTP client.

    Used by SFTP-capable applications and ``connect_and_discover_programs()``.
    """
    folder = pathlib.PurePosixPath(root)

    return sorted(_walk_programs(sftp, folder, folder))


def connect_and_discover_programs(
    host: str,
    root: typing.Union[str, pathlib.Path, pathlib.PurePosixPath],
    username: str,
    password: str,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
    trust_unknown_host_keys: bool = False,
) -> typing.List[str]:
    """Connect over SFTP, discover URP files, and close the connection.

    Used by ``urp_discovery_client`` and applications that prefer a one-call SFTP operation.
    """
    import paramiko

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()

    if trust_unknown_host_keys:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(host, port=port, username=username, password=password, timeout=timeout)

    with ssh:
        with ssh.open_sftp() as sftp:
            return discover_programs(sftp, root)
