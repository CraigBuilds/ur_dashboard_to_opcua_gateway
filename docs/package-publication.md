# Package publication

The repository contains two independently buildable Python distributions:

- `packages/declarative_opcua_server` builds `declarative-opcua-server` and imports as `declarative_opcua_server`.
- `packages/universal_robots_clients` builds `universal-robots-clients` and imports as `universal_robots_clients`.

Both distributions use semantic versions, maintain package-local changelogs, publish typed-package markers, declare Python 3.8.3 or later, and keep runtime
dependencies bounded by compatible major versions. Their README files are the PyPI descriptions and contain installation, API, usage, security, and development
guidance.

Both distribution names returned no existing PyPI project on 2026-07-21. Availability is not reserved until an authorized owner uploads a release, so it must be
checked again immediately before publication.

## Release prerequisites

Before a public release:

1. Decide and add the intended software license. Licensing is an owner decision and is not inferred by the build process.
1. Confirm the distribution names are still available on PyPI or controlled by the intended owner.
1. Update the package version and package-local `CHANGELOG.md` together.
1. Run the repository's Python 3.8, current-Python, and URSim test suites.
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

## TestPyPI

Upload and install from TestPyPI before the first production release:

```bash
python -m twine upload --repository testpypi dist/*
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ PACKAGE_NAME
```

The extra production index is needed because package dependencies may not be mirrored on TestPyPI. Verify the README rendering, metadata, imports, and basic
example before continuing.

## PyPI

After TestPyPI succeeds, upload the exact already-tested artifacts:

```bash
python -m twine upload dist/*
```

Then install by distribution name from PyPI in a new environment, rerun smoke tests, create the matching Git tag, and record the released versions in the
gateway dependency constraints. Published versions are immutable; fixes require a new version rather than replacing an artifact.
