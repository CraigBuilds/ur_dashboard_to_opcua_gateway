"""Create a small, opinionated OPC UA server from flat function dictionaries.

The package exposes one public operation, ``create_server()``. Consumers provide separate status, parameter, and method interfaces. Status functions are typed
zero-argument getters that are polled into read-only OPC UA variables. Parameter functions are typed one-argument setters invoked when clients write OPC UA
variables. Method functions become OPC UA methods whose required annotated arguments and optional annotated return value define the method signature.

The implementation owns synchronous ``asyncua`` setup, Python-to-OPC-UA type conversion, callback adaptation, and polling. ``create_server()`` returns the plain
``asyncua.sync.Server`` so its normal ``start()``, ``stop()``, and context-manager lifecycle remain available. The package deliberately does not model arbitrary
folders, objects, node identifiers, security schemes, robot protocols, or application workflow.

This package depends on ``asyncua`` and the Python standard library. It has no knowledge of Universal Robots or the gateway that first motivated it.
"""

import declarative_opcua_server._server as _server

__all__ = ["create_server"]

create_server = _server.create_server
