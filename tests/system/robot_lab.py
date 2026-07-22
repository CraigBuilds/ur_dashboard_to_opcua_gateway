"""Compose the real container-backed services used by system tests."""

import contextlib
import pathlib
import typing
import uuid

import testcontainers.core.image as tc_image
import testcontainers.core.network as tc_network

import tests.system.containers.gateway_container as gateway_container
import tests.system.containers.openssh_container as openssh_container
import tests.system.containers.ursim_container as ursim_container


class RobotLab:
    """Manage the complete real-service test laboratory for one pytest session."""

    def __init__(self, programs: pathlib.Path) -> None:
        """Configure paths and service state."""
        self.programs = programs
        self.repository = pathlib.Path(__file__).resolve().parents[2]
        self.project = self.repository
        self._stack = contextlib.ExitStack()
        self.ursim: ursim_container.UrSimContainer
        self.sftp: openssh_container.OpenSshContainer
        self._network: tc_network.Network
        self._gateway_image: str

    def start(self) -> "RobotLab":
        """Build images, start services, and expose both gateway arrangements."""
        suffix = uuid.uuid4().hex[:12]
        network_context = tc_network.Network()
        self._network = self._stack.enter_context(network_context)
        gateway_tag = f"ur_dashboard_to_opcua_gateway_test:{suffix}"
        gateway_context = tc_image.DockerImage(self.project, tag=gateway_tag, clean_up=True, dockerfile_path="code/Dockerfile")
        gateway_image = self._stack.enter_context(gateway_context)
        self._gateway_image = str(gateway_image)
        ssh_context_path = self.repository / "tests" / "system" / "docker" / "openssh"
        ssh_tag = f"ur-program-openssh-test:{suffix}"
        ssh_context = tc_image.DockerImage(ssh_context_path, tag=ssh_tag, clean_up=True)
        ssh_image = self._stack.enter_context(ssh_context)
        ursim_context = ursim_container.UrSimContainer(self.programs, self._network)
        self.ursim = self._stack.enter_context(ursim_context)
        sftp_context = openssh_container.OpenSshContainer(str(ssh_image), self.programs, self._network)
        self.sftp = self._stack.enter_context(sftp_context)
        self.ursim.prepare_robot()

        return self

    def gateway(self, catalogue: str) -> gateway_container.GatewayContainer:
        """Return one unstarted gateway so catalogue variants run sequentially."""
        if catalogue == "local":
            return gateway_container.GatewayContainer.local(self._gateway_image, self.programs, self.ursim.network_mode, self.ursim.host, self.ursim.opcua_port)

        if catalogue == "sftp":
            return gateway_container.GatewayContainer.sftp(self._gateway_image, self._network)

        raise ValueError(f"Unsupported catalogue: {catalogue}")

    def stop(self) -> None:
        """Stop containers, remove images, and remove the private network."""
        self._stack.close()

    def __enter__(self) -> "RobotLab":
        """Start the context-managed lab."""
        return self.start()

    def __exit__(self, _type: typing.Optional[typing.Type[BaseException]], _value: typing.Optional[BaseException], _traceback: object) -> None:
        """Stop the context-managed lab."""
        self.stop()
