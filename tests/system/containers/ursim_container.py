"""Run and control an official URSim instance for system tests."""

import pathlib
import time
import types
import typing

import testcontainers.core.container as tc_container
import testcontainers.core.network as tc_network
import ur_dashboard_to_opcua_gateway._05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde as control_ur_programs_and_exchange_parameters

import tests.support.waiting as waiting

URSIM_IMAGE = "universalrobots/ursim_e-series:5.25.2"
URSIM_PROGRAMS = "/ursim/programs.UR20"
DASHBOARD_PORT = 29999
OPCUA_PORT = 4840
START_TIMEOUT = 240.0
ROBOT_TIMEOUT = 90.0


class UrSimContainer:
    """Manage an official UR20 URSim container for system tests."""

    def __init__(self, programs: pathlib.Path, network: tc_network.Network, image: str = URSIM_IMAGE) -> None:
        """Configure the simulator container."""
        program_path = str(programs.resolve())
        container = tc_container.DockerContainer(
            image,
            env={"ROBOT_MODEL": "UR20"},
            ports=[DASHBOARD_PORT, OPCUA_PORT],
            volumes=[(program_path, URSIM_PROGRAMS, "rw")],
            network=network,
            network_aliases=["ursim"],
        )
        self._container = container

    @property
    def host(self) -> str:
        """Return the Docker host address."""
        return self._container.get_container_host_ip()

    @property
    def dashboard_port(self) -> int:
        """Return the mapped Dashboard port."""
        port = self._container.get_exposed_port(DASHBOARD_PORT)

        return int(port)

    @property
    def opcua_port(self) -> int:
        """Return the mapped OPC UA port."""
        port = self._container.get_exposed_port(OPCUA_PORT)

        return int(port)

    @property
    def container_id(self) -> str:
        """Return the Docker container ID."""
        wrapped = self._container.get_wrapped_container()

        return str(wrapped.id)

    @property
    def network_mode(self) -> str:
        """Return a shared network namespace suitable for local deployment."""
        identifier = self.container_id
        prefix = "container:"

        return prefix + identifier

    def start(self) -> "UrSimContainer":
        """Start URSim and wait for the Dashboard Server."""
        self._container.start()

        try:
            waiting.wait_until(self._dashboard_ready, START_TIMEOUT)
        except Exception as error:
            logs = self.logs()
            self.stop()
            text = f"URSim failed to start.\n{logs[-4000:]}"
            raise RuntimeError(text) from error

        return self

    def stop(self) -> None:
        """Stop and remove the simulator."""
        self._container.stop()

    def command(self, command: str) -> str:
        """Send a real Dashboard command."""
        return control_ur_programs_and_exchange_parameters.send_command(self.host, self.dashboard_port, command)

    def prepare_robot(self) -> None:
        """Prepare URSim to execute the safe test program."""
        self.command("stop")
        mode = self.command("robotmode")

        if "POWER_OFF" in mode:
            self.command("power on")
            self._wait_for_mode("IDLE")

        mode = self.command("robotmode")

        if "IDLE" in mode:
            self.command("brake release")
            self._wait_for_mode("RUNNING")

    def wait_for_program_state(self, state: str, timeout: float = 20.0) -> None:
        """Wait for one Dashboard program state."""
        expected = state.upper()

        def has_state() -> bool:
            """Return whether the state is active."""
            response = self.command("programState")
            actual = response.upper()

            return actual.startswith(expected)

        waiting.wait_until(has_state, timeout, 0.25)

    def logs(self) -> str:
        """Return combined container logs."""
        stdout, stderr = self._container.get_logs()
        data = stdout + stderr

        return data.decode(errors="replace")

    def __enter__(self) -> "UrSimContainer":
        """Start the context-managed URSim."""
        return self.start()

    def __exit__(
        self, _type: typing.Optional[typing.Type[BaseException]], _value: typing.Optional[BaseException], _traceback: typing.Optional[types.TracebackType]
    ) -> None:
        """Stop the context-managed URSim."""
        self.stop()

    def _dashboard_ready(self) -> bool:
        """Return whether Dashboard and the simulated controller are ready."""
        response = self.command("robotmode")
        ready_modes = ("POWER_OFF", "IDLE", "RUNNING")

        return any(mode in response for mode in ready_modes)

    def _wait_for_mode(self, mode: str) -> None:
        """Wait for one robot mode."""
        deadline = time.monotonic()
        deadline += ROBOT_TIMEOUT

        while time.monotonic() < deadline:
            response = self.command("robotmode")

            if mode in response:
                return

            time.sleep(0.5)

        message = f"URSim did not reach robot mode {mode}."
        raise TimeoutError(message)
