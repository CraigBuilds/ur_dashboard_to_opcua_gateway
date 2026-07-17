"""Apply this gateway's identity to the reusable declarative OPC UA server.

The reusable ``declarative_opcua_server`` package owns address-space construction, annotations, polling, write callbacks, and lifecycle. This final application
adapter supplies the UR-specific namespace and root object, forwards the three flat interfaces created by module 6, and returns the configured but unstarted
managed server to the composition root.

The public API is ``OPC_NAMESPACE`` for clients and tests plus ``create_server()`` for composition. No asyncua implementation details, robot transports, program
discovery, or invocation policy remain here.

This module depends on ``declarative_opcua_server`` and ``_06_combine_program_discovery_and_control``. The reusable server package does not import either the
gateway or Universal Robots clients.
"""

import typing

import declarative_opcua_server

import ur_dashboard_to_opcua_gateway._06_combine_program_discovery_and_control as combine_program_discovery_and_control

__all__ = ["OPC_NAMESPACE", "create_server"]

OPC_NAMESPACE = "urn:ur20:program-control"
_ROOT_OBJECT = "UR20"


def create_server(interfaces: combine_program_discovery_and_control.GatewayInterfaces, endpoint: str) -> typing.Any:
    """Create this gateway's configured declarative OPC UA server.

    Used by ``_03_compose_gateway.compose_gateway()``.
    """
    return declarative_opcua_server.create_server(
        status_interface=interfaces.status_interface,
        parameter_interface=interfaces.parameter_interface,
        method_interface=interfaces.method_interface,
        endpoint=endpoint,
        namespace=OPC_NAMESPACE,
        root_object=_ROOT_OBJECT,
    )
