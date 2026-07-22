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
1. Configure the package repository's `release.yml` as a PyPI trusted publisher using the `pypi` GitHub environment. Do not commit API tokens or passwords.

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

Push the matching version tag to run the package repository's release workflow:

```bash
git tag -a v0.3.0 -m "Release 0.3.0"
git push origin v0.3.0
```

The workflow validates that the tag matches the package version, builds the exact artifacts, and exchanges GitHub's OIDC identity for a short-lived PyPI
publishing token. Then install by distribution name from PyPI in a new environment, rerun smoke tests, and confirm that the gateway resolves the released
versions. Published versions are immutable; fixes require a new version rather than replacing an artifact.
