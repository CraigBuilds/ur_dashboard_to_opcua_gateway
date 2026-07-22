"""Collect independent clients for Universal Robots protocols and program assets.

The distribution contains ``dashboard_client`` for Dashboard Server exchanges, three explicit URP discovery clients for backend selection, local filesystems,
and SFTP, and ``rtde_client`` for persistent typed register exchange. Consumers import those modules explicitly so calls retain protocol context and optional
dependencies remain isolated without creating a monolithic robot client.

The root package intentionally re-exports no functions. Dashboard and local discovery use only the Python standard library. SFTP discovery loads optional
Paramiko only when connecting, and the RTDE client loads optional ``ur-rtde`` only when creating a connection. The package has no dependency on OPC UA or any
gateway.
"""

__all__ = []
