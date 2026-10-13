# src/tests/unit/test_import_boundaries.py
"""AST scan tests that statically enforce architectural boundaries and facade rules."""
import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent


def _get_python_files(directory: Path, exclude_dirs: tuple[str, ...] = ("tests", "__pycache__")):
    for path in directory.rglob("*.py"):
        if any(part in exclude_dirs for part in path.parts):
            continue
        yield path


def _resolve_import_target(node: ast.Import | ast.ImportFrom, file_path: Path) -> list[str]:
    """Resolves import targets into fully qualified module paths (supports relative imports)."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]

    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level > 0:
            # Relativer Import
            # file_path ist z.B. .../src/agentic/engine/jobs.py
            # parent ist .../src/agentic/engine (level 1)
            # level 2 ist .../src/agentic usw.
            rel_dir = file_path.parent
            for _ in range(node.level - 1):
                rel_dir = rel_dir.parent
            rel_package = ".".join(rel_dir.relative_to(SRC_DIR.parent).parts)
            target = f"{rel_package}.{module}" if module else rel_package
            return [target]
        return [module]

    return []


def test_facade_enforced_outside_agentic():
    """Outside of src/agentic/ (tests excluded), nobody may import internal subpackages
    of src.agentic - only the src.agentic facade is permitted."""
    violations = []
    forbidden_prefixes = (
        "src.agentic.agents",
        "src.agentic.engine",
        "src.agentic.tools",
    )

    for py_file in _get_python_files(SRC_DIR):
        # Skip src/agentic itself
        if "agentic" in py_file.parts:
            continue

        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in _resolve_import_target(node, py_file):
                    if any(target == p or target.startswith(f"{p}.") for p in forbidden_prefixes):
                        violations.append(f"{py_file.relative_to(SRC_DIR)}: {target}")

    assert not violations, (
        f"Verletzung der Fassaden-Regel: Direkte Importe auf agentic-Unterpakete gefunden:\n"
        + "\n".join(violations)
    )


def test_engine_has_exactly_one_delayed_agent_import():
    """src/agentic/engine/ may never import from agents or tools at module level.
    Exactly ONE deferred, function-local import is permitted: in jobs.py (_run_job)."""
    engine_dir = SRC_DIR / "agentic" / "engine"
    top_level_violations = []
    delayed_agent_imports = []

    for py_file in _get_python_files(engine_dir):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))

        # 1. Check top-level nodes
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in _resolve_import_target(node, py_file):
                    if "agentic.agents" in target or "agentic.tools" in target:
                        top_level_violations.append(f"{py_file.name}:{node.lineno} -> {target}")

        # 2. Alle Importe durchlaufen und verschachtelte finden
        for node in ast.walk(tree):
            if node in tree.body:
                continue  # war schon auf Modulebene
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in _resolve_import_target(node, py_file):
                    if "agentic.agents" in target or "agentic.tools" in target:
                        delayed_agent_imports.append((py_file.name, node.lineno, target))

    assert not top_level_violations, (
        f"Unerlaubte Top-Level-Importe in engine/ auf agents oder tools:\n"
        + "\n".join(top_level_violations)
    )

    # Exactly ONE deferred import may exist, in jobs.py
    assert len(delayed_agent_imports) == 1, (
        f"Expected exactly 1 deferred import in engine/ (jobs.py), found {len(delayed_agent_imports)}:\n"
        + "\n".join(f"{f}:{line} -> {target}" for f, line, target in delayed_agent_imports)
    )
    file_name, _, target = delayed_agent_imports[0]
    assert file_name == "jobs.py"
    assert "agentic.agents.task_agent" in target


def test_tools_do_not_import_agents_except_delegation():
    """Apart from delegation.py (which encapsulates agent calls), src/agentic/tools/ may
    never import from src.agentic.agents. In particular tasks.py must not import from agents."""
    tools_dir = SRC_DIR / "agentic" / "tools"
    violations = []

    for py_file in _get_python_files(tools_dir):
        if py_file.name == "delegation.py":
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in _resolve_import_target(node, py_file):
                    if "agentic.agents" in target:
                        violations.append(f"{py_file.name}:{node.lineno} -> {target}")

    assert not violations, (
        f"Apart from delegation.py, tools in tools/ must not import from agents/:\n"
        + "\n".join(violations)
    )


def test_schemas_do_not_import_internal_layers():
    """src/schemas/ darf keine Anwendungs-Schichten importieren (core, agentic, routes, navigation)."""
    schemas_dir = SRC_DIR / "schemas"
    violations = []
    forbidden_prefixes = ("src.agentic", "src.core", "src.routes", "src.navigation")

    for py_file in _get_python_files(schemas_dir):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in _resolve_import_target(node, py_file):
                    if any(target == p or target.startswith(f"{p}.") for p in forbidden_prefixes):
                        violations.append(f"{py_file.name}:{node.lineno} -> {target}")

    assert not violations, (
        f"Schemas must not import logic layers:\n" + "\n".join(violations)
    )
