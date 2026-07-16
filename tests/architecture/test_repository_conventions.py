"""Test repository-wide module structure and API conventions."""

import ast
import pathlib
import typing

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
PRODUCTION_ROOT = PROJECT_ROOT / "code" / "src" / "ur_dashboard_to_opcua_gateway"
PYTHON_ROOTS = (PRODUCTION_ROOT, PROJECT_ROOT / "tests")


def python_files() -> typing.List[pathlib.Path]:
    """Return project Python files that follow the namespace import convention."""
    return sorted(path for root in PYTHON_ROOTS for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_modules_have_docstrings() -> None:
    """Require every production and test module to describe its responsibility."""
    undocumented: typing.List[str] = []

    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        if ast.get_docstring(tree) is None:
            undocumented.append(str(path.relative_to(PROJECT_ROOT)))

    assert not undocumented, "Python modules must have top-level docstrings:\n" + "\n".join(undocumented)


def test_parser_arguments_have_help_messages() -> None:
    """Require every declared parser argument to explain its purpose."""
    undocumented: typing.List[str] = []

    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
                continue

            keywords = {keyword.arg for keyword in node.keywords}

            if "help" not in keywords:
                undocumented.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")

    assert not undocumented, "Parser arguments must define help messages:\n" + "\n".join(undocumented)


def test_imports_use_module_namespaces() -> None:
    """Require module imports so external calls retain their namespace."""
    direct_imports: typing.List[str] = []

    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module != "__future__":
                names = ", ".join(alias.name for alias in node.names)
                relative_path = path.relative_to(PROJECT_ROOT)
                direct_imports.append(f"{relative_path}:{node.lineno}: from {node.module} import {names}")

    assert not direct_imports, "Import modules and call members through their namespace:\n" + "\n".join(direct_imports)


def test_public_callables_document_their_consumers() -> None:
    """Require public functions, classes, and methods to state where they are used."""
    undocumented: typing.List[str] = []

    for path in sorted(PRODUCTION_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or node.name.startswith("_"):
                continue

            docstring = ast.get_docstring(node) or ""

            if "Used by " not in docstring:
                undocumented.append(f"{path.name}:{node.lineno}: {node.name}")

            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) or member.name.startswith("_"):
                        continue

                    member_docstring = ast.get_docstring(member) or ""

                    if "Used by " not in member_docstring:
                        undocumented.append(f"{path.name}:{member.lineno}: {node.name}.{member.name}")

    assert not undocumented, "Public callables must document their consumers:\n" + "\n".join(undocumented)


def _decorator_name(decorator: ast.expr) -> str:
    """Return a dotted decorator name without requiring ``ast.unparse``."""
    current = decorator.func if isinstance(decorator, ast.Call) else decorator
    parts: typing.List[str] = []

    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value

    if isinstance(current, ast.Name):
        parts.append(current.id)

    return ".".join(reversed(parts))


def test_production_classes_are_dataclasses() -> None:
    """Keep production behavior functional by reserving classes for data."""
    non_data_classes: typing.List[str] = []

    for path in sorted(PRODUCTION_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            decorators = {_decorator_name(decorator) for decorator in node.decorator_list}
            is_dataclass = any(decorator.startswith("dataclasses.dataclass") for decorator in decorators)

            if not is_dataclass:
                non_data_classes.append(f"{path.name}:{node.lineno}: {node.name}")

    assert not non_data_classes, "Production classes must be dataclasses:\n" + "\n".join(non_data_classes)
