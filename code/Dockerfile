FROM python:3.12-slim

WORKDIR /workspace

# These immutable GitHub archives bridge the short interval before the same versions are released on PyPI. Once published, the gateway dependency declaration
# resolves both packages directly and these two explicit requirements can be removed.
RUN python -m pip install --no-cache-dir \
    "declarative-opcua-server @ https://github.com/CraigBuilds/declarative-opcua-server/archive/1f4cd1ccb37937cff690ea51fca860c9293b7ac8.zip" \
    "universal-robots-clients[sftp,rtde] @ https://github.com/CraigBuilds/universal-robots-clients/archive/d680e68555ddabd0eecd67de73a9ad4a22ff4d4f.zip"

COPY code/pyproject.toml ./code/pyproject.toml
COPY code/src ./code/src

RUN python -m pip install --no-cache-dir "./code[sftp]"

ENTRYPOINT ["ur_dashboard_to_opcua_gateway"]
