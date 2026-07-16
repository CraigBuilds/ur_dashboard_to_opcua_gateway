"""Prepare dependencies and run the real Docker-backed system tests."""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import typing

_MINIMUM_PYTHON = (3, 10)
_PROJECT_CACHE_NAME = "ur_dashboard_to_opcua_gateway"


def _parse_args() -> argparse.Namespace:
    """Parse system-test runner arguments."""
    parser = argparse.ArgumentParser(description="Prepare and run the real Docker-backed URSim system tests.")
    parser.add_argument("--catalog", choices=("all", "local", "sftp"), default="all", help="Run both catalogue paths or select one.")
    parser.add_argument("--collect-only", action="store_true", help="Install dependencies and collect tests without requiring Docker.")
    parser.add_argument("--no-pull", action="store_true", help="Let Testcontainers pull the URSim image instead of pulling it before pytest.")
    parser.add_argument("--python", type=pathlib.Path, help="Use this Python 3.10 or later executable for the reusable test environment.")
    parser.add_argument("--skip-install", action="store_true", help="Reuse an already prepared virtual environment without installing dependencies.")
    parser.add_argument("--venv", type=pathlib.Path, help="Override the virtual-environment path.")
    parser.add_argument("pytest_arguments", nargs=argparse.REMAINDER, help="Arguments after -- are passed to pytest.")

    return parser.parse_args()


def _repository_root() -> pathlib.Path:
    """Return the repository root."""
    return pathlib.Path(__file__).resolve().parents[1]


def _run(command: typing.Sequence[str], cwd: pathlib.Path, environment: typing.Optional[typing.Dict[str, str]] = None) -> None:
    """Run one visible command."""
    printable = subprocess.list2cmdline(list(command))
    print(f"\n> {printable}", flush=True)
    subprocess.run(command, cwd=str(cwd), env=environment, check=True)


def _capture(command: typing.Sequence[str], cwd: pathlib.Path, environment: typing.Optional[typing.Dict[str, str]] = None) -> str:
    """Run one command and return its standard output."""
    result = subprocess.run(command, cwd=str(cwd), env=environment, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    return result.stdout.strip()


def _candidate_python_commands() -> typing.Iterator[typing.List[str]]:
    """Yield likely Python commands from newest to oldest supported version."""
    current = [sys.executable]

    if sys.version_info >= _MINIMUM_PYTHON:
        yield current

    launcher = shutil.which("py")

    if launcher is not None:
        for version in ("3.13", "3.12", "3.11", "3.10"):
            yield [launcher, f"-{version}"]

    for executable in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
        path = shutil.which(executable)

        if path is not None and path != sys.executable:
            yield [path]


def _python_version(command: typing.Sequence[str], repository: pathlib.Path) -> typing.Optional[typing.Tuple[int, int, int]]:
    """Return an interpreter version when a candidate command works."""
    probe = "import sys; print('.'.join(str(part) for part in sys.version_info[:3]))"

    try:
        output = _capture([*command, "-c", probe], repository)
        parts = output.split(".")
        version = tuple(int(part) for part in parts)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None

    if len(version) != 3:
        return None

    return typing.cast(typing.Tuple[int, int, int], version)


def _find_supported_python(
    repository: pathlib.Path, configured: typing.Optional[pathlib.Path] = None
) -> typing.Tuple[typing.List[str], typing.Tuple[int, int, int]]:
    """Find Python 3.10 or later for the container tooling."""
    if configured is not None:
        command = [str(configured.expanduser().resolve())]
        version = _python_version(command, repository)

        if version is None:
            message = f"The configured Python executable could not be run: {command[0]}"
            raise RuntimeError(message)

        if version < _MINIMUM_PYTHON:
            formatted = ".".join(str(part) for part in version)
            message = f"The configured Python is {formatted}; Python 3.10 or later is required for the system-test dependencies."
            raise RuntimeError(message)

        return command, version

    seen: typing.Set[typing.Tuple[str, ...]] = set()

    for command in _candidate_python_commands():
        key = tuple(command)

        if key in seen:
            continue

        seen.add(key)
        version = _python_version(command, repository)

        if version is not None and version >= _MINIMUM_PYTHON:
            return command, version

    message = "Python 3.10 or later is required for the system-test dependencies. Install a current Python release and run this command again."
    raise RuntimeError(message)


def _cache_root() -> pathlib.Path:
    """Return an operating-system cache directory outside the repository."""
    if os.name == "nt":
        fallback = pathlib.Path.home() / "AppData" / "Local"
        base = pathlib.Path(os.environ.get("LOCALAPPDATA", fallback))
    else:
        fallback = pathlib.Path.home() / ".cache"
        base = pathlib.Path(os.environ.get("XDG_CACHE_HOME", fallback))

    return base / _PROJECT_CACHE_NAME


def _venv_path(configured: typing.Optional[pathlib.Path], version: typing.Tuple[int, int, int]) -> pathlib.Path:
    """Return the configured or default virtual-environment path."""
    if configured is not None:
        return configured.expanduser().resolve()

    major, minor, _patch = version

    return _cache_root() / f"system-tests-py{major}{minor}"


def _venv_python(environment: pathlib.Path) -> pathlib.Path:
    """Return the Python executable inside one virtual environment."""
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"

    return environment / "bin" / "python"


def _create_virtual_environment(command: typing.Sequence[str], environment: pathlib.Path, repository: pathlib.Path) -> pathlib.Path:
    """Create the reusable system-test virtual environment when needed."""
    python = _venv_python(environment)

    if python.is_file():
        return python

    environment.parent.mkdir(parents=True, exist_ok=True)
    _run([*command, "-m", "venv", str(environment)], repository)

    if not python.is_file():
        message = f"Virtual environment did not create its Python executable: {python}"
        raise RuntimeError(message)

    return python


def _copy_package_for_install(repository: pathlib.Path, destination: pathlib.Path) -> pathlib.Path:
    """Copy package sources so dependency installation leaves the repository clean."""
    source = repository / "code"
    target = destination / "code"
    ignored = shutil.ignore_patterns("__pycache__", "*.egg-info", "build", "dist")
    shutil.copytree(str(source), str(target), ignore=ignored)

    return target


def _install_dependencies(python: pathlib.Path, repository: pathlib.Path) -> None:
    """Install the package and system-test dependencies into the reusable environment."""
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip"], repository)

    with tempfile.TemporaryDirectory(prefix="ur_dashboard_to_opcua_gateway_system_tests_") as temporary:
        package = _copy_package_for_install(repository, pathlib.Path(temporary))
        requirement = f"{package}[system-test]"
        _run([str(python), "-m", "pip", "install", requirement], repository)


def _test_environment() -> typing.Dict[str, str]:
    """Return environment settings that keep Python caches out of the repository."""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    return environment


def _require_docker(repository: pathlib.Path) -> str:
    """Return the Docker executable after validating the daemon platform."""
    docker = shutil.which("docker")

    if docker is None:
        message = "Docker was not found. Install and start Docker Desktop or Docker Engine with Linux amd64 containers, then run this command again."
        raise RuntimeError(message)

    try:
        platform = _capture([docker, "info", "--format", "{{.OSType}}/{{.Architecture}}"], repository)
    except subprocess.CalledProcessError as error:
        message = "Docker is installed, but its daemon is not available. Start Docker and wait until it is ready."
        raise RuntimeError(message) from error

    operating_system, separator, architecture = platform.partition("/")
    supported_architectures = {"amd64", "x86_64"}

    if separator != "/" or operating_system != "linux" or architecture not in supported_architectures:
        message = f"The URSim system tests require a Linux amd64 Docker engine; Docker reported {platform!r}."
        raise RuntimeError(message)

    return docker


def _ursim_image(python: pathlib.Path, repository: pathlib.Path, environment: typing.Dict[str, str]) -> str:
    """Read the pinned URSim image from the test harness."""
    statement = "import tests.containers.ursim_container as ursim_container; print(ursim_container.URSIM_IMAGE)"

    return _capture([str(python), "-c", statement], repository, environment)


def _pull_ursim_image(docker: str, python: pathlib.Path, repository: pathlib.Path, environment: typing.Dict[str, str]) -> None:
    """Pull the exact URSim image used by the system tests."""
    image = _ursim_image(python, repository, environment)
    print(f"\nThe first pull is large. Preparing {image}.", flush=True)
    _run([docker, "pull", image], repository)


def _run_tests(
    python: pathlib.Path, repository: pathlib.Path, cache: pathlib.Path, catalog: str, collect_only: bool, pytest_arguments: typing.Sequence[str]
) -> None:
    """Run or collect the real system tests."""
    cache.mkdir(parents=True, exist_ok=True)
    command = [str(python), "-m", "pytest", "-c", "tests/pytest.ini", "-o", f"cache_dir={cache}", "-m", "system"]

    if catalog != "all":
        command.extend(["-k", catalog])

    if collect_only:
        command.append("--collect-only")

    forwarded = list(pytest_arguments)

    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]

    command.extend(forwarded)
    _run(command, repository, _test_environment())


def _main() -> int:
    """Prepare dependencies and run the Docker-backed system tests."""
    args = _parse_args()
    repository = _repository_root()

    try:
        python_command, version = _find_supported_python(repository, args.python)
        environment_path = _venv_path(args.venv, version)
        docker = None if args.collect_only else _require_docker(repository)

        if args.skip_install:
            python = _venv_python(environment_path)

            if not python.is_file():
                message = f"The requested virtual environment is not prepared: {environment_path}"
                raise RuntimeError(message)
        else:
            python = _create_virtual_environment(python_command, environment_path, repository)
            _install_dependencies(python, repository)

        print(f"Using Python {'.'.join(str(part) for part in version)} and environment {environment_path}.", flush=True)
        environment = _test_environment()

        if docker is not None and not args.no_pull:
            _pull_ursim_image(docker, python, repository, environment)

        pytest_cache = environment_path.parent / f"{environment_path.name}-pytest-cache"
        _run_tests(python, repository, pytest_cache, args.catalog, args.collect_only, args.pytest_arguments)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nSystem-test runner failed: {error}", file=sys.stderr)

        if isinstance(error, subprocess.CalledProcessError):
            return error.returncode

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(_main())
