"""Implement the package's fixed Status, Parameters, and Methods address space.

``create_server()`` validates three flat mappings and returns a configured ``asyncua.sync.Server``. Status getters are polled on a small background thread and
changed values are written through ``asyncua`` so ordinary OPC UA subscriptions receive notifications. The thread follows the lifetime of asyncua's own thread
loop, leaving startup, shutdown, and context management to the returned server. Parameter setters are installed at the server's attribute-write boundary, and
method functions are wrapped to hide the parent-node argument required by ``asyncua``.

Function annotations are part of the runtime contract. A small internal map supports scalar booleans, integers, doubles, strings, and byte strings, plus
homogeneous one-dimensional ``typing.List`` values of those types. Unsupported, unresolved, or contextually invalid signatures fail while the server is being
created rather than producing a malformed address space later.

This implementation module depends on ``asyncua`` plus standard-library inspection, threading, typing, logging, and dataclass support. The package root
re-exports ``create_server()``; binding records, type resolution, polling, and callback wrappers remain private.
"""

import copy
import dataclasses
import functools
import inspect
import logging
import threading
import time
import typing

import asyncua
import asyncua.sync
import asyncua.ua

_StatusFunction = typing.Callable[[], typing.Any]
_ParameterFunction = typing.Callable[..., None]
_MethodFunction = typing.Callable[..., typing.Any]
_StatusInterface = typing.Mapping[str, _StatusFunction]
_ParameterInterface = typing.Mapping[str, _ParameterFunction]
_MethodInterface = typing.Mapping[str, _MethodFunction]
_TypeDefinition = typing.Tuple[asyncua.ua.VariantType, typing.Any, typing.Type[typing.Any], bool]
_MethodDefinition = typing.Tuple[typing.List[typing.Tuple[str, _TypeDefinition]], typing.Optional[_TypeDefinition]]

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


def _poll_status(server: asyncua.sync.Server, bindings: typing.Sequence[_StatusBinding]) -> None:
    """Publish changed status values while asyncua's thread loop is alive."""
    while server.tloop.is_alive():
        time.sleep(_POLL_INTERVAL_SECONDS)

        if not server.tloop.is_alive():
            return

        if server.aio_obj.bserver is None:
            continue

        for binding in bindings:
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


def _start_status_polling(server: asyncua.sync.Server, bindings: typing.Sequence[_StatusBinding]) -> None:
    """Start polling when the interface contains status getters."""
    if not bindings:
        return

    thread = threading.Thread(target=_poll_status, args=(server, bindings), name="declarative-opcua-status", daemon=True)
    thread.start()


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


def _method_definition(name: str, method: _MethodFunction) -> _MethodDefinition:
    """Validate one method and return its required inputs and optional output."""
    signature = inspect.signature(method)
    hints = _resolved_hints(method)
    inputs: typing.List[typing.Tuple[str, _TypeDefinition]] = []

    for parameter in signature.parameters.values():
        if parameter.default is not inspect.Parameter.empty:
            continue

        if parameter.kind not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            message = f"Method function '{_function_name(method)}' for '{name}' may only expose required positional arguments."
            raise TypeError(message)

        annotation = hints.get(parameter.name, parameter.annotation)

        if annotation is inspect.Parameter.empty:
            message = f"Method function '{_function_name(method)}' for '{name}' must annotate argument '{parameter.name}'."
            raise TypeError(message)

        inputs.append((parameter.name, _resolve_type(annotation, "Method", _function_name(method))))

    annotation = _resolved_return_type(method)
    output = None if _is_none_annotation(annotation) else _resolve_type(annotation, "Method", _function_name(method))

    return inputs, output


def _method_argument(name: str, definition: _TypeDefinition) -> asyncua.ua.Argument:
    """Create one typed OPC UA method argument declaration."""
    variant_type, _default_value, _python_type, is_array = definition
    argument = asyncua.ua.Argument()
    argument.Name = name
    argument.DataType = asyncua.ua.NodeId(variant_type.value)
    argument.ValueRank = 1 if is_array else -1
    argument.ArrayDimensions = [0] if is_array else []

    return argument


def _adapt_method(method: _MethodFunction) -> typing.Callable[..., typing.Any]:
    """Hide asyncua's parent-node callback argument from an application method."""

    @asyncua.uamethod
    def opcua_method(_parent_node_id: asyncua.ua.NodeId, *arguments: typing.Any) -> typing.Any:
        return method(*arguments)

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
) -> asyncua.sync.Server:
    """Create a configured plain asyncua synchronous server.

    Used by applications that need a compact synchronous OPC UA adapter, including
    ``ur_dashboard_to_opcua_gateway._03_compose_gateway``.
    """
    _validate_names("Status interface", status_interface)
    _validate_names("Parameter interface", parameter_interface)
    _validate_names("Method interface", method_interface)
    status_definitions = [(name, reader, _status_definition(name, reader)) for name, reader in status_interface.items()]
    parameter_definitions = [(name, writer, _parameter_definition(name, writer)) for name, writer in parameter_interface.items()]

    method_definitions = [(name, method, _method_definition(name, method)) for name, method in method_interface.items()]

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

    for name, reader, status_definition in status_definitions:
        variant_type, default_value, python_type, is_array = status_definition
        initial_variant = asyncua.ua.Variant(default_value, variant_type)
        variable = status_folder.add_variable(namespace_index, name, initial_variant)
        variable.set_writable(False)
        status_bindings.append(_StatusBinding(name, variable, reader, variant_type, python_type, is_array, default_value))

    for name, writer, parameter_definition in parameter_definitions:
        variant_type, default_value, python_type, is_array = parameter_definition
        initial_variant = asyncua.ua.Variant(default_value, variant_type)
        variable = parameter_folder.add_variable(namespace_index, name, initial_variant)
        variable.set_writable(True)
        _install_parameter_writer(server, variable, name, writer, python_type, is_array)

    for name, method, method_definition in method_definitions:
        inputs, output = method_definition
        input_arguments = [_method_argument(argument_name, argument_definition) for argument_name, argument_definition in inputs]
        output_arguments = [] if output is None else [_method_argument("Result", output)]
        method_folder.add_method(namespace_index, name, _adapt_method(method), input_arguments, output_arguments)

    _start_status_polling(server, status_bindings)

    return server
