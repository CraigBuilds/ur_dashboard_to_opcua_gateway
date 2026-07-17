"""Collect independent clients for Universal Robots protocols and program assets.

The distribution currently contains ``dashboard`` for one-command Dashboard Server exchanges and ``program_discovery`` for deterministic local or SFTP URP
catalogues. Consumers import those modules explicitly so calls retain protocol context, optional dependencies remain isolated, and future RTDE support can have
its own lifecycle without creating a monolithic robot client.

The root package intentionally re-exports no functions. Dashboard uses only the Python standard library, local discovery uses ``pathlib``, and SFTP discovery
loads optional Paramiko support only when requested. The package has no dependency on OPC UA or on any gateway application.
"""

__all__ = []
