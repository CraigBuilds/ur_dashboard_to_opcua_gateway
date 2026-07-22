"""Discover Universal Robots program files on a local filesystem.

``discover_programs()`` recursively searches one directory for files with a case-insensitive ``.urp`` suffix. It returns deterministic, sorted paths relative
to that directory and normalizes path separators to forward slashes so catalogues are stable across Windows and Linux.

This focused module is appropriate for mounted robot program folders, copied backups, development fixtures, and any application that can access URP files
without opening a network connection. It owns no connection lifecycle or application configuration.

The module depends only on ``pathlib`` and ``typing`` from the Python standard library. It is used by ``urp_discovery_client`` and can also be imported directly.
"""

import pathlib
import typing

__all__ = ["discover_programs"]

_URP_SUFFIX = ".urp"


def _is_urp(path: pathlib.PurePath) -> bool:
    """Return whether one path has a case-insensitive URP suffix."""
    return path.suffix.lower() == _URP_SUFFIX


def discover_programs(root: typing.Union[str, pathlib.Path, pathlib.PurePosixPath]) -> typing.List[str]:
    """Return all URP paths beneath one local root.

    Used by ``urp_discovery_client`` and applications with direct filesystem access.
    """
    folder = pathlib.Path(root)
    paths = folder.rglob("*")
    programs = (path.relative_to(folder) for path in paths if path.is_file() and _is_urp(path))

    return sorted(path.as_posix() for path in programs)
