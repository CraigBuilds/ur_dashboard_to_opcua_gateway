"""Adapt the application command model into a synchronous OPC UA server.

This is the package's presentation and transport boundary. ``create_server()`` receives the generic command registry and per-program shortcuts produced by
``_06_combine_program_discovery_and_control``. It creates the ``Objects/UR20`` address space, exposes generic operations as methods, and mirrors program paths
below ``ProgramShortcuts`` with no-argument ``load`` and ``run`` methods. Function signatures and return annotations are inspected to generate OPC UA input and
output metadata, including string-array results for program discovery.

The public API is ``OPC_NAMESPACE``, which gives clients a stable namespace URI, and ``create_server()``, which returns a configured but unstarted
``asyncua.sync.Server``. Folder caching, callback adaptation, argument construction, and node creation are internal details. The current MVP deliberately
configures ``NoSecurity`` and leaves server startup and shutdown to ``_01_main``.

This module depends on ``asyncua`` and the command types from ``_06_combine_program_discovery_and_control``. It does not know how programs are discovered or how
Dashboard commands reach the robot, so another transport could expose the same application registry without changing those lower-level modules.
"""

import functools
import inspect
import pathlib
import typing

import asyncua
import asyncua.sync
import asyncua.ua

import ur_dashboard_to_opcua_gateway._06_combine_program_discovery_and_control as combine_program_discovery_and_control

_Method = typing.Callable[..., combine_program_discovery_and_control.CommandResult]
_FolderCache = typing.Dict[pathlib.PurePosixPath, asyncua.sync.SyncNode]

__all__ = ["OPC_NAMESPACE", "create_server"]

OPC_NAMESPACE = "urn:ur20:program-control"
_OPC_OBJECT_NAME = "UR20"
_SHORTCUTS_FOLDER = "ProgramShortcuts"


def _string_argument(name: str, is_array: bool = False) -> asyncua.ua.Argument:
    """Create one OPC UA string argument."""
    argument = asyncua.ua.Argument()
    argument.Name = name
    argument.DataType = asyncua.ua.NodeId(asyncua.ua.ObjectIds.String)

    if is_array:
        argument.ValueRank = asyncua.ua.ValueRank.OneDimension

    return argument


def _input_arguments(command: combine_program_discovery_and_control.Command) -> typing.List[asyncua.ua.Argument]:
    """Create OPC UA input arguments for a registered command."""
    parameters = inspect.signature(command).parameters
    arguments: typing.List[asyncua.ua.Argument] = []

    for name in parameters:
        argument = _string_argument(name)
        arguments.append(argument)

    return arguments


def _returns_array(command: combine_program_discovery_and_control.Command) -> bool:
    """Return whether a command returns an array of strings."""
    target = command.func if isinstance(command, functools.partial) else command

    try:
        hints = typing.get_type_hints(target)
        annotation = hints.get("return")
    except (NameError, TypeError):
        annotation = inspect.signature(command).return_annotation

    origin = typing.get_origin(annotation)

    return origin is list


def _output_arguments(command: combine_program_discovery_and_control.Command) -> typing.List[asyncua.ua.Argument]:
    """Create OPC UA output arguments for a registered command."""
    is_array = _returns_array(command)
    argument = _string_argument("result", is_array)

    return [argument]


def _make_method(command: combine_program_discovery_and_control.Command) -> _Method:
    """Adapt a registry command to an OPC UA method callback."""

    @asyncua.uamethod
    def method(_parent: asyncua.ua.NodeId, *arguments: str) -> combine_program_discovery_and_control.CommandResult:
        return command(*arguments)

    return method


def _add_methods(parent: asyncua.sync.SyncNode, namespace: int, commands: combine_program_discovery_and_control.CommandRegistry) -> None:
    """Add registered commands as OPC UA methods beneath one node."""
    items = commands.items()

    for name, command in items:
        method = _make_method(command)
        inputs = _input_arguments(command)
        outputs = _output_arguments(command)

        parent.add_method(namespace, name, method, inputs, outputs)


def _get_program_folder(root: asyncua.sync.SyncNode, namespace: int, path: pathlib.PurePosixPath, folders: _FolderCache) -> asyncua.sync.SyncNode:
    """Return an existing program folder or create its missing parts."""
    current = root
    current_path = pathlib.PurePosixPath()

    for part in path.parts:
        current_path /= part
        existing = folders.get(current_path)

        if existing is not None:
            current = existing
            continue

        current = current.add_folder(namespace, part)
        key = current_path
        folders[key] = current

    return current


def _add_program_shortcuts(parent: asyncua.sync.SyncNode, namespace: int, shortcuts: combine_program_discovery_and_control.ProgramShortcuts) -> None:
    """Add no-argument program shortcuts beneath one OPC UA folder."""
    root = parent.add_folder(namespace, _SHORTCUTS_FOLDER)
    folders: _FolderCache = {}
    items = shortcuts.items()

    for program, commands in items:
        path = pathlib.PurePosixPath(program)
        folder = _get_program_folder(root, namespace, path.parent, folders)
        program_node = folder.add_object(namespace, path.name)
        _add_methods(program_node, namespace, commands)


def create_server(
    commands: combine_program_discovery_and_control.CommandRegistry, shortcuts: combine_program_discovery_and_control.ProgramShortcuts, endpoint: str
) -> asyncua.sync.Server:
    """Expose program commands through a configured OPC UA server.

    Used by ``_03_compose_gateway.compose_gateway()``.
    """
    server = asyncua.sync.Server()
    server.set_endpoint(endpoint)
    server.set_server_name("ur_dashboard_to_opcua_gateway")
    policies = [asyncua.ua.SecurityPolicyType.NoSecurity]
    server.set_security_policy(policies)

    namespace = server.register_namespace(OPC_NAMESPACE)
    objects = server.nodes.objects
    robot = objects.add_object(namespace, _OPC_OBJECT_NAME)

    _add_methods(robot, namespace, commands)
    _add_program_shortcuts(robot, namespace, shortcuts)

    return server
