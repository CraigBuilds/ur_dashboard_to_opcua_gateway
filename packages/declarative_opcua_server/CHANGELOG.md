# Changelog

All notable changes to this package are documented here.

## 0.2.0 - 2026-07-21

- Return a plain `asyncua.sync.Server` from `create_server()`.
- Build flat method, status, and parameter interfaces from annotated callables.
- Infer OPC UA scalar and list types from Python annotations.
- Keep polling and write subscriptions alive through resources owned by the returned server.
- Bound interpreter-specific dependencies so clean Python 3.8 installations remain resolvable.
- Support Python 3.8.3 and later.
