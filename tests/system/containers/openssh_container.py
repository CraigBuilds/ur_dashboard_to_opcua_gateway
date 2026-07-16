"""Run an OpenSSH SFTP service in a disposable test container."""

import pathlib
import types
import typing

import paramiko
import testcontainers.core.container as tc_container
import testcontainers.core.network as tc_network

import tests.support.waiting as waiting

SFTP_PORT = 22
SFTP_USERNAME = "root"
SFTP_PASSWORD = "easybot"
START_TIMEOUT = 60.0


class OpenSshContainer:
    """Manage a real OpenSSH/SFTP service for remote catalogue tests."""

    def __init__(self, image: str, programs: pathlib.Path, network: tc_network.Network) -> None:
        """Configure the OpenSSH container."""
        program_path = str(programs.resolve())
        container = tc_container.DockerContainer(
            image,
            env={"SFTP_PASSWORD": (SFTP_PASSWORD)},
            ports=[SFTP_PORT],
            volumes=[(program_path, "/programs", "ro")],
            network=network,
            network_aliases=["sftp"],
        )
        self._container = container

    @property
    def host(self) -> str:
        """Return the Docker host address."""
        return self._container.get_container_host_ip()

    @property
    def port(self) -> int:
        """Return the mapped SSH port."""
        port = self._container.get_exposed_port(SFTP_PORT)

        return int(port)

    def start(self) -> "OpenSshContainer":
        """Start OpenSSH and verify SFTP."""
        self._container.start()

        try:
            waiting.wait_until(self._sftp_ready, START_TIMEOUT)
        except Exception as error:
            logs = self.logs()
            self.stop()
            text = f"OpenSSH failed to start.\n{logs[-4000:]}"
            raise RuntimeError(text) from error

        return self

    def stop(self) -> None:
        """Stop and remove OpenSSH."""
        self._container.stop()

    def logs(self) -> str:
        """Return combined container logs."""
        stdout, stderr = self._container.get_logs()
        data = stdout + stderr

        return data.decode(errors="replace")

    def __enter__(self) -> "OpenSshContainer":
        """Start context-managed OpenSSH."""
        return self.start()

    def __exit__(
        self, _type: typing.Optional[typing.Type[BaseException]], _value: typing.Optional[BaseException], _traceback: typing.Optional[types.TracebackType]
    ) -> None:
        """Stop context-managed OpenSSH."""
        self.stop()

    def _sftp_ready(self) -> bool:
        """Return whether real SFTP can list the mounted programs directory."""
        ssh = paramiko.SSHClient()
        policy = paramiko.AutoAddPolicy()
        ssh.set_missing_host_key_policy(policy)
        ssh.connect(self.host, port=self.port, username=SFTP_USERNAME, password=SFTP_PASSWORD, timeout=5.0)

        with ssh:
            with ssh.open_sftp() as sftp:
                sftp.listdir("/programs")

        return True
