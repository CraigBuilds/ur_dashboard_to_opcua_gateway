"""Select local or SFTP discovery of Universal Robots program files.

``discover_programs()`` is the module's only public operation. It accepts one backend name and delegates to either ``urp_discovery_local_client`` or
``urp_discovery_sftp_client`` while preserving their common contract: recursively find case-insensitive ``.urp`` files, return paths relative to the supplied
root, normalize separators to forward slashes, and sort results deterministically.

This module is useful at configuration boundaries where the backend is selected at runtime. Callers that already know their backend should import the
corresponding backend module directly. SFTP credentials and trust policy are forwarded unchanged; environment variables, prompts, and application validation
remain outside this package.

The module depends only on the two discovery modules in this distribution. It has no knowledge of Dashboard, RTDE, OPC UA, or gateway configuration types.
"""

import pathlib
import typing

import universal_robots_clients.urp_discovery_local_client as urp_discovery_local_client
import universal_robots_clients.urp_discovery_sftp_client as urp_discovery_sftp_client

__all__ = ["discover_programs"]


def discover_programs(
    backend: str,
    root: typing.Union[str, pathlib.Path, pathlib.PurePosixPath],
    host: typing.Optional[str] = None,
    username: str = "root",
    password: typing.Optional[str] = None,
    port: int = urp_discovery_sftp_client.DEFAULT_PORT,
    timeout: float = urp_discovery_sftp_client.DEFAULT_TIMEOUT,
    trust_unknown_host_keys: bool = False,
) -> typing.List[str]:
    """Discover URP files through the selected backend.

    Used by applications that select discovery from configuration, including ``ur_dashboard_to_opcua_gateway``.
    """
    if backend == "local":
        return urp_discovery_local_client.discover_programs(root)

    if backend == "sftp":
        if host is None:
            raise ValueError("SFTP discovery requires a host.")

        if password is None:
            raise ValueError("SFTP discovery requires a password.")

        return urp_discovery_sftp_client.connect_and_discover_programs(host, root, username, password, port, timeout, trust_unknown_host_keys)

    raise ValueError(f"Unsupported URP-discovery backend: {backend}")
