FROM python:3.12-slim

WORKDIR /workspace

COPY code/pyproject.toml ./code/pyproject.toml
COPY code/src ./code/src

RUN python -m pip install --no-cache-dir "./code[sftp]"

ENTRYPOINT ["ur_dashboard_to_opcua_gateway"]
