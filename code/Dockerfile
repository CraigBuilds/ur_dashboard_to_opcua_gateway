FROM python:3.12-slim

WORKDIR /workspace

COPY packages/declarative_opcua_server ./packages/declarative_opcua_server
COPY packages/universal_robots_clients ./packages/universal_robots_clients

RUN python -m pip install --no-cache-dir ./packages/declarative_opcua_server "./packages/universal_robots_clients[sftp]"

COPY code/pyproject.toml ./code/pyproject.toml
COPY code/src ./code/src

RUN python -m pip install --no-cache-dir "./code[sftp]"

ENTRYPOINT ["ur_dashboard_to_opcua_gateway"]
