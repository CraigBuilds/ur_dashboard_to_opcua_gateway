FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN python -m pip install --no-cache-dir ".[sftp]"

ENTRYPOINT ["ur_dashboard_to_opcua_gateway"]
