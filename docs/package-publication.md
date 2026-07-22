# Package publication

The reusable distributions live in independent public repositories:

- [`declarative-opcua-server`](https://github.com/CraigBuilds/declarative-opcua-server) imports as `declarative_opcua_server`.
- [`universal-robots-clients`](https://github.com/CraigBuilds/universal-robots-clients) imports as `universal_robots_clients`.

Both distributions use semantic versions, maintain package-local changelogs, publish typed-package markers, declare Python 3.8.3 or later, and keep runtime
dependencies bounded by compatible major versions. Their README files are the PyPI descriptions and contain installation, API, usage, security, and development
guidance.

The gateway repository neither builds nor tests package artifacts. Each package repository owns that work and publishes its own distribution.

## Release prerequisites

Before a public release:

1. Decide and add the intended software license. Licensing is an owner decision and is not inferred by the build process.
1. Confirm the distribution names are still available on PyPI or controlled by the intended owner.
1. Update the package version and package-local `CHANGELOG.md` together.
1. Run the package repository's Python 3.8, current-Python, and real-service test suites.
1. Use a scoped PyPI API token through the publishing environment. Do not commit credentials or place them on a command line.

## Build and inspect

Run these commands from each package directory in a clean environment:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
python -m build
python -m twine check dist/*
```

Install the wheel into a second empty environment and import every documented module. For `universal-robots-clients`, repeat with the `sftp` and `rtde` extras.
The parent repository's system test remains the compatibility contract between the built packages and the gateway.

## PyPI

Upload the exact tested artifacts from each package repository:

```bash
python -m twine upload dist/*
```

Then install by distribution name from PyPI in a new environment, rerun smoke tests, create the matching Git tag, and confirm that the gateway resolves the
released versions without the temporary GitHub-archive bridge. Published versions are immutable; fixes require a new version rather than replacing an artifact.
