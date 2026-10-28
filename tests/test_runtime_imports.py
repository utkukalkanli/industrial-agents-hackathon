"""Production installs only `[project] dependencies` (Vercel, no dev group): code that ships must not import a
package that only the dev group brings (httpx did, and every API call answered 500)."""

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ["agent", "backend", "core", "benchmark"]


def names(requirements: list[str]) -> set[str]:
    return {re.split(r"[\s\[<>=!~;]", requirement, maxsplit=1)[0].lower().replace("-", "_")
            for requirement in requirements}


def imported(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_shipped_code_imports_no_dev_only_package() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dev_only = names(project["dependency-groups"]["dev"]) - names(project["project"]["dependencies"])
    offenders = [f"{path.relative_to(ROOT)}: {module}"
                 for folder in SHIPPED for path in sorted((ROOT / folder).rglob("*.py"))
                 for module in sorted(imported(path) & dev_only)]
    assert not offenders, offenders
