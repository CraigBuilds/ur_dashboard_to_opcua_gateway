"""Provide the small Docker Engine operations needed by the system-test runner."""

import argparse
import sys
import typing


def _docker_sdk() -> typing.Any:
    """Import the Docker SDK from the prepared system-test environment."""
    try:
        import docker
    except ImportError as error:
        message = "The Docker SDK is unavailable. Prepare the system-test environment without --skip-install, then try again."
        raise RuntimeError(message) from error

    return docker


def inspect_platform() -> str:
    """Return the Docker daemon operating system and architecture."""
    docker_sdk = _docker_sdk()

    try:
        client = docker_sdk.from_env()

        try:
            information = client.info()
        finally:
            client.close()
    except docker_sdk.errors.DockerException as error:
        message = f"Docker is unavailable through the Docker SDK: {error}"
        raise RuntimeError(message) from error

    operating_system = information.get("OSType")
    architecture = information.get("Architecture")

    if not isinstance(operating_system, str) or not isinstance(architecture, str):
        message = "The Docker daemon did not report its operating system and architecture."
        raise RuntimeError(message)

    return f"{operating_system}/{architecture}"


def pull_image(image: str) -> None:
    """Pull one image through the Docker SDK and close the client afterwards."""
    docker_sdk = _docker_sdk()

    try:
        client = docker_sdk.from_env()

        try:
            client.images.pull(image)
        finally:
            client.close()
    except docker_sdk.errors.DockerException as error:
        message = f"Docker could not pull {image}: {error}"
        raise RuntimeError(message) from error


def _parse_args(arguments: typing.Optional[typing.Sequence[str]] = None) -> argparse.Namespace:
    """Parse the internal Docker helper command."""
    parser = argparse.ArgumentParser(description="Inspect Docker or pull an image through the Docker SDK.")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("info", help="Print the Docker daemon platform.")
    pull = subparsers.add_parser("pull", help="Pull an image.")
    pull.add_argument("image", help="Image reference to pull.")

    return parser.parse_args(arguments)


def _main(arguments: typing.Optional[typing.Sequence[str]] = None) -> int:
    """Run one requested Docker SDK operation."""
    args = _parse_args(arguments)

    try:
        if args.operation == "info":
            print(inspect_platform())
        else:
            pull_image(typing.cast(str, args.image))
    except RuntimeError as error:
        print(error, file=sys.stderr)

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(_main())
