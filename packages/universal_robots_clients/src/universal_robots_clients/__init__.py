"""Collect independent clients for Universal Robots protocols and program assets.

The distribution contains ``dashboard`` for one-command Dashboard Server exchanges, ``program_discovery`` for deterministic local or SFTP URP catalogues, and
``rtde`` for persistent typed register exchange. Consumers import those modules explicitly so calls retain protocol context and optional dependencies remain
isolated without creating a monolithic robot client.

The root package intentionally re-exports no functions. Dashboard and local discovery use only the Python standard library. SFTP discovery loads optional
Paramiko only when connecting, and RTDE loads optional ``ur-rtde`` only when creating a client. The package has no dependency on OPC UA or any gateway.
"""

__all__ = []
