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
        self.project = self.repository / "code"
        self._stack = contextlib.ExitStack()
        self.ursim: ursim_container.UrSimContainer
        self.sftp: openssh_container.OpenSshContainer
        self._gateways: typing.Dict[str, gateway_container.GatewayContainer] = {}

    def start(self) -> "RobotLab":
        """Build images, start services, and expose both gateway arrangements."""
        suffix = uuid.uuid4().hex[:12]
        network_context = tc_network.Network()
        network = self._stack.enter_context(network_context)
        gateway_tag = f"ur_dashboard_to_opcua_gateway_test:{suffix}"
        gateway_context = tc_image.DockerImage(self.project, tag=gateway_tag, clean_up=True)
        gateway_image = self._stack.enter_context(gateway_context)
        ssh_context_path = self.repository / "tests" / "system" / "docker" / "openssh"
        ssh_tag = f"ur-program-openssh-test:{suffix}"
        ssh_context = tc_image.DockerImage(ssh_context_path, tag=ssh_tag, clean_up=True)
        ssh_image = self._stack.enter_context(ssh_context)
        ursim_context = ursim_container.UrSimContainer(self.programs, network)
        self.ursim = self._stack.enter_context(ursim_context)
        sftp_context = openssh_container.OpenSshContainer(str(ssh_image), self.programs, network)
        self.sftp = self._stack.enter_context(sftp_context)
        self.ursim.prepare_robot()
        local = gateway_container.GatewayContainer.local(str(gateway_image), self.programs, self.ursim.network_mode, self.ursim.host, self.ursim.opcua_port)
        remote = gateway_container.GatewayContainer.sftp(str(gateway_image), network)
        self._gateways["local"] = self._stack.enter_context(local)
        self._gateways["sftp"] = self._stack.enter_context(remote)

        return self

    def gateway(self, catalogue: str) -> gateway_container.GatewayContainer:
        """Return one configured gateway."""
        return self._gateways[catalogue]

    def stop(self) -> None:
        """Stop containers, remove images, and remove the private network."""
        self._stack.close()

    def __enter__(self) -> "RobotLab":
        """Start the context-managed lab."""
        return self.start()

    def __exit__(self, _type: typing.Optional[typing.Type[BaseException]], _value: typing.Optional[BaseException], _traceback: object) -> None:
        """Stop the context-managed lab."""
        self.stop()
