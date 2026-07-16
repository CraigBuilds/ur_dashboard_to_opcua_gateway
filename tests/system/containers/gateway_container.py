"""Run the gateway application in a disposable test container."""

import pathlib
import types
import typing

import asyncua.sync
import testcontainers.core.container as tc_container
import testcontainers.core.network as tc_network

import tests.support.waiting as waiting

OPCUA_PORT = 4840
OPCUA_PATH = "/ur20/"
START_TIMEOUT = 90.0


class GatewayContainer:
    """Manage the real gateway application inside a disposable container."""

    def __init__(self, container: tc_container.DockerContainer, endpoint_host: typing.Optional[str], endpoint_port: typing.Optional[int]) -> None:
        """Store the configured container and externally reachable endpoint."""
        self._container = container
        self._endpoint_host = endpoint_host
        self._endpoint_port = endpoint_port

    @classmethod
    def local(cls, image: str, programs: pathlib.Path, network_mode: str, endpoint_host: str, endpoint_port: int) -> "GatewayContainer":
        """Create a local-catalogue gateway sharing the URSim network stack."""
        command = ["--catalog", "local", "--programs-folder", "/programs", "--dashboard-host", "127.0.0.1", "--opcua-endpoint", cls._listen_endpoint()]
        program_path = str(programs.resolve())
        container = tc_container.DockerContainer(image, command=command, volumes=[(program_path, "/programs", "ro")], network_mode=network_mode)

        return cls(container, endpoint_host, endpoint_port)

    @classmethod
    def sftp(cls, image: str, network: tc_network.Network) -> "GatewayContainer":
        """Create an SFTP-catalogue gateway on the shared test network."""
        command = [
            "--catalog",
            "sftp",
            "--programs-folder",
            "/programs",
            "--robot-host",
            "sftp",
            "--dashboard-host",
            "ursim",
            "--opcua-endpoint",
            cls._listen_endpoint(),
        ]
        container = tc_container.DockerContainer(
            image, command=command, env={"UR_ROBOT_PASSWORD": ("easybot")}, ports=[OPCUA_PORT], network=network, network_aliases=["gateway"]
        )

        return cls(container, None, None)

    @property
    def endpoint(self) -> str:
        """Return the OPC UA client endpoint."""
        host = self._endpoint_host
        port = self._endpoint_port

        if host is None:
            host = self._container.get_container_host_ip()

        if port is None:
            mapped = self._container.get_exposed_port(OPCUA_PORT)
            port = int(mapped)

        address = f"{host}:{port}"

        return f"opc.tcp://{address}{OPCUA_PATH}"

    def start(self) -> "GatewayContainer":
        """Start the gateway and wait for an OPC UA client to browse it."""
        self._container.start()

        try:
            waiting.wait_until(self._opcua_ready, START_TIMEOUT, 0.5)
        except Exception as error:
            logs = self.logs()
            self.stop()
            text = f"Gateway failed to start.\n{logs[-4000:]}"
            raise RuntimeError(text) from error

        return self

    def stop(self) -> None:
        """Stop and remove the gateway."""
        self._container.stop()

    def logs(self) -> str:
        """Return combined container logs."""
        stdout, stderr = self._container.get_logs()
        data = stdout + stderr

        return data.decode(errors="replace")

    def __enter__(self) -> "GatewayContainer":
        """Start the context-managed gateway."""
        return self.start()

    def __exit__(
        self, _type: typing.Optional[typing.Type[BaseException]], _value: typing.Optional[BaseException], _traceback: typing.Optional[types.TracebackType]
    ) -> None:
        """Stop the context-managed gateway."""
        self.stop()

    @staticmethod
    def _listen_endpoint() -> str:
        """Return the container endpoint."""
        return f"opc.tcp://0.0.0.0:4840{OPCUA_PATH}"

    def _opcua_ready(self) -> bool:
        """Return whether OPC UA browsing succeeds against the real server."""
        endpoint = self.endpoint

        client_context = asyncua.sync.Client(endpoint)

        with client_context as client:
            nodes = client.nodes
            objects = nodes.objects
            objects.get_children()

        return True
