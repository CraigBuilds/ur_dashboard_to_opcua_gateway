"""Implement the package's fixed Status, Parameters, and Methods address space.

``create_server()`` validates three flat mappings and creates a configured but unstarted managed server. Status getters are polled on one package-owned thread
and changed values are written through ``asyncua`` so ordinary OPC UA subscriptions receive notifications. Parameter setters are installed at the server's
attribute-write boundary, allowing a client write to call application code before the accepted value is retained. Method functions are wrapped to hide the
parent-node argument required by ``asyncua``.

Function annotations are part of the runtime contract. A small internal map supports scalar booleans, integers, doubles, strings, and byte strings, plus
homogeneous one-dimensional ``typing.List`` values of those types. Unsupported, unresolved, or contextually invalid signatures fail while the server is being
created rather than producing a malformed address space later.

This internal module depends on ``asyncua`` plus standard-library inspection, threading, typing, logging, and dataclass support. Only the package root re-exports
``create_server()``; binding records, type resolution, callback wrappers, and the managed server implementation remain private.
"""

import copy
import dataclasses
import functools
import inspect
import logging
import threading
import types
import typing

import asyncua
import asyncua.sync
import asyncua.ua

_StatusFunction = typing.Callable[[], typing.Any]
_ParameterFunction = typing.Callable[..., None]
_MethodFunction = typing.Callable[[], None]
_StatusInterface = typing.Mapping[str, _StatusFunction]
_ParameterInterface = typing.Mapping[str, _ParameterFunction]
_MethodInterface = typing.Mapping[str, _MethodFunction]
_TypeDefinition = typing.Tuple[asyncua.ua.VariantType, typing.Any, typing.Type[typing.Any], bool]

_LOGGER = logging.getLogger(__name__)
_POLL_INTERVAL_SECONDS = 0.1
_DEFAULT_ENDPOINT = "opc.tcp://127.0.0.1:4840/"
_DEFAULT_NAMESPACE = "urn:declarative-opcua-server"
_DEFAULT_ROOT_OBJECT = "Application"
_SCALAR_TYPE_DEFINITIONS: typing.Dict[typing.Type[typing.Any], typing.Tuple[asyncua.ua.VariantType, typing.Any]] = {
    bool: (asyncua.ua.VariantType.Boolean, False),
    int: (asyncua.ua.VariantType.Int64, 0),
    float: (asyncua.ua.VariantType.Double, 0.0),
    str: (asyncua.ua.VariantType.String, ""),
    bytes: (asyncua.ua.VariantType.ByteString, b""),
}


@dataclasses.dataclass
class _StatusBinding:
    """Hold one polled status getter and its latest published value."""

    name: str
    variable: asyncua.sync.SyncNode
    reader: _StatusFunction
    variant_type: asyncua.ua.VariantType
    python_type: typing.Type[typing.Any]
    is_array: bool
    last_value: typing.Any


@dataclasses.dataclass
class _ManagedServer:
    """Own an asyncua server together with its polling lifecycle."""

    _server: asyncua.sync.Server
    _status_bindings: typing.List[_StatusBinding]
    _stop_requested: threading.Event = dataclasses.field(default_factory=threading.Event)
    _polling_thread: typing.Optional[threading.Thread] = None

    def start(self) -> None:
        """Start OPC UA service and status polling."""
        if self._polling_thread is not None:
            raise RuntimeError("Server has already been started.")

        self._server.start()
        thread = threading.Thread(target=self._poll_status, name="declarative-opcua-status", daemon=True)
        self._polling_thread = thread
        thread.start()

    def stop(self) -> None:
        """Stop status polling and OPC UA service."""
        self._stop_requested.set()
        thread = self._polling_thread

        if thread is not None:
            thread.join(timeout=5.0)

            if thread.is_alive():
                _LOGGER.warning("Status polling did not stop before the OPC UA server shutdown timeout.")

        self._server.stop()

    def __enter__(self) -> "_ManagedServer":
        """Start and return this context-managed server."""
        self.start()

        return self

    def __exit__(
        self,
        _exception_type: typing.Optional[typing.Type[BaseException]],
        _exception: typing.Optional[BaseException],
        _traceback: typing.Optional[types.TracebackType],
    ) -> None:
        """Stop this context-managed server."""
        self.stop()

    def _poll_status(self) -> None:
        """Publish changed status values until shutdown is requested."""
        while not self._stop_requested.wait(_POLL_INTERVAL_SECONDS):
            for binding in self._status_bindings:
                try:
                    value = binding.reader()
                    _validate_runtime_value(binding.name, value, binding.python_type, binding.is_array)

                    if value == binding.last_value:
                        continue

                    snapshot = copy.deepcopy(value)
                    variant = asyncua.ua.Variant(snapshot, binding.variant_type)
                    binding.variable.write_value(variant)
                    binding.last_value = snapshot
                except Exception:
                    _LOGGER.exception("Could not refresh OPC UA status node %s.", binding.name)


def _function_name(function: typing.Callable[..., typing.Any]) -> str:
    """Return a useful function name for validation errors."""
    target = function.func if isinstance(function, functools.partial) else function

    return getattr(target, "__name__", repr(target))


def _resolved_hints(function: typing.Callable[..., typing.Any]) -> typing.Dict[str, typing.Any]:
    """Resolve annotations while preserving the remaining signature of a partial."""
    target = function.func if isinstance(function, functools.partial) else function

    try:
        return typing.get_type_hints(target)
    except (NameError, TypeError) as error:
        name = _function_name(function)
        message = f"Could not resolve type annotations for '{name}': {error}"
        raise TypeError(message) from error


def _resolved_return_type(function: typing.Callable[..., typing.Any]) -> typing.Any:
    """Return one function's resolved return annotation."""
    hints = _resolved_hints(function)

    return hints.get("return", inspect.Signature.empty)


def _is_none_annotation(annotation: typing.Any) -> bool:
    """Return whether an annotation represents no returned value."""
    return annotation in (inspect.Signature.empty, None, type(None))


def _resolve_type(annotation: typing.Any, interface_name: str, function_name: str) -> _TypeDefinition:
    """Resolve one supported annotation into OPC UA type metadata."""
    origin = typing.get_origin(annotation)
    is_array = origin is list
    python_type = annotation

    if is_array:
        arguments = typing.get_args(annotation)

        if len(arguments) != 1:
            message = f"{interface_name} function '{function_name}' must use a homogeneous typing.List annotation."
            raise TypeError(message)

        python_type = arguments[0]

    scalar = _SCALAR_TYPE_DEFINITIONS.get(python_type)

    if scalar is None:
        supported = "bool, int, float, str, bytes, and typing.List of those scalar types"
        message = f"{interface_name} function '{function_name}' uses unsupported type {annotation!r}; supported types are {supported}."
        raise TypeError(message)

    variant_type, scalar_default = scalar
    default_value = [] if is_array else scalar_default

    return variant_type, default_value, python_type, is_array


def _validate_runtime_value(name: str, value: typing.Any, python_type: typing.Type[typing.Any], is_array: bool) -> None:
    """Validate a status value against its declared Python type."""
    values = value if is_array and isinstance(value, list) else [value]

    if is_array and not isinstance(value, list):
        message = f"Status function '{name}' returned {type(value).__name__}; expected list."
        raise TypeError(message)

    for item in values:
        if type(item) is not python_type:
            message = f"Status function '{name}' returned {type(item).__name__}; expected {python_type.__name__}."
            raise TypeError(message)


def _validate_names(interface_name: str, interface: typing.Mapping[str, typing.Callable[..., typing.Any]]) -> None:
    """Validate one flat interface's names and callable values."""
    for name, function in interface.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"{interface_name} names must be non-empty strings.")

        if not callable(function):
            raise TypeError(f"{interface_name} entry '{name}' must be callable.")


def _status_definition(name: str, reader: _StatusFunction) -> _TypeDefinition:
    """Validate one status getter and return its OPC UA type metadata."""
    signature = inspect.signature(reader)

    if signature.parameters:
        message = f"Status function '{_function_name(reader)}' for '{name}' must accept no arguments."
        raise TypeError(message)

    annotation = _resolved_return_type(reader)

    if _is_none_annotation(annotation):
        message = f"Status function '{_function_name(reader)}' for '{name}' must declare a return type."
        raise TypeError(message)

    return _resolve_type(annotation, "Status", _function_name(reader))


def _parameter_definition(name: str, writer: _ParameterFunction) -> _TypeDefinition:
    """Validate one parameter setter and return its OPC UA type metadata."""
    signature = inspect.signature(writer)
    parameters = list(signature.parameters.values())

    if len(parameters) != 1:
        message = f"Parameter function '{_function_name(writer)}' for '{name}' must accept exactly one argument."
        raise TypeError(message)

    return_annotation = _resolved_return_type(writer)

    if not _is_none_annotation(return_annotation):
        message = f"Parameter function '{_function_name(writer)}' for '{name}' must not return a value."
        raise TypeError(message)

    parameter = parameters[0]
    hints = _resolved_hints(writer)
    annotation = hints.get(parameter.name, parameter.annotation)

    if annotation is inspect.Parameter.empty:
        message = f"Parameter function '{_function_name(writer)}' for '{name}' must annotate its argument."
        raise TypeError(message)

    return _resolve_type(annotation, "Parameter", _function_name(writer))


def _validate_method(name: str, method: _MethodFunction) -> None:
    """Validate one no-argument, no-result method function."""
    signature = inspect.signature(method)

    if signature.parameters:
        message = f"Method function '{_function_name(method)}' for '{name}' must accept no arguments."
        raise TypeError(message)

    annotation = _resolved_return_type(method)

    if not _is_none_annotation(annotation):
        message = f"Method function '{_function_name(method)}' for '{name}' must not return a value."
        raise TypeError(message)


def _adapt_method(method: _MethodFunction) -> typing.Callable[..., None]:
    """Hide asyncua's parent-node callback argument from an application method."""

    @asyncua.uamethod
    def opcua_method(_parent_node_id: asyncua.ua.NodeId) -> None:
        method()

    return opcua_method


def _install_parameter_writer(
    server: asyncua.sync.Server, variable: asyncua.sync.SyncNode, name: str, writer: _ParameterFunction, python_type: typing.Type[typing.Any], is_array: bool
) -> None:
    """Invoke an application setter before retaining a client-written value."""

    def set_value(node_data: typing.Any, attribute: asyncua.ua.AttributeIds, data_value: asyncua.ua.DataValue) -> None:
        """Validate, forward, and retain one OPC UA client write."""
        variant = data_value.Value
        value = None if variant is None else variant.Value
        _validate_runtime_value(name, value, python_type, is_array)
        writer(value)
        node_data.attributes[attribute].value = data_value

    server.aio_obj.set_attribute_value_setter(variable.nodeid, set_value)


def create_server(
    *,
    status_interface: _StatusInterface,
    parameter_interface: _ParameterInterface,
    method_interface: _MethodInterface,
    endpoint: str = _DEFAULT_ENDPOINT,
    namespace: str = _DEFAULT_NAMESPACE,
    root_object: str = _DEFAULT_ROOT_OBJECT,
) -> _ManagedServer:
    """Create a configured but unstarted server from three flat function interfaces.

    Used by applications that need a compact synchronous OPC UA adapter, including
    ``ur_dashboard_to_opcua_gateway._07_expose_program_commands_via_opcua``.
    """
    _validate_names("Status interface", status_interface)
    _validate_names("Parameter interface", parameter_interface)
    _validate_names("Method interface", method_interface)
    status_definitions = [(name, reader, _status_definition(name, reader)) for name, reader in status_interface.items()]
    parameter_definitions = [(name, writer, _parameter_definition(name, writer)) for name, writer in parameter_interface.items()]

    for name, method in method_interface.items():
        _validate_method(name, method)

    server = asyncua.sync.Server()
    server.set_endpoint(endpoint)
    server.set_server_name(f"{root_object} OPC UA Server")
    server.set_security_policy([asyncua.ua.SecurityPolicyType.NoSecurity])
    server.set_security_IDs(["Anonymous"])
    namespace_index = server.register_namespace(namespace)
    root = server.nodes.objects.add_object(namespace_index, root_object)
    status_folder = root.add_folder(namespace_index, "Status")
    parameter_folder = root.add_folder(namespace_index, "Parameters")
    method_folder = root.add_folder(namespace_index, "Methods")
    status_bindings: typing.List[_StatusBinding] = []

    for name, reader, definition in status_definitions:
        variant_type, default_value, python_type, is_array = definition
        initial_variant = asyncua.ua.Variant(default_value, variant_type)
        variable = status_folder.add_variable(namespace_index, name, initial_variant)
        variable.set_writable(False)
        status_bindings.append(_StatusBinding(name, variable, reader, variant_type, python_type, is_array, default_value))

    for name, writer, definition in parameter_definitions:
        variant_type, default_value, python_type, is_array = definition
        initial_variant = asyncua.ua.Variant(default_value, variant_type)
        variable = parameter_folder.add_variable(namespace_index, name, initial_variant)
        variable.set_writable(True)
        _install_parameter_writer(server, variable, name, writer, python_type, is_array)

    for name, method in method_interface.items():
        method_folder.add_method(namespace_index, name, _adapt_method(method))

    return _ManagedServer(server, status_bindings)
