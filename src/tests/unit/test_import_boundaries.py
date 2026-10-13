# src/tests/unit/test_import_boundaries.py
"""AST-Scan-Tests zur statischen Durchsetzung von Architekturgrenzen und Fassadenregeln."""
import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent


def _get_python_files(directory: Path, exclude_dirs: tuple[str, ...] = ("tests", "__pycache__")):
    for path in directory.rglob("*.py"):
        if any(part in exclude_dirs for part in path.parts):
            continue
        yield path


def _resolve_import_target(node: ast.Import | ast.ImportFrom, file_path: Path) -> list[str]:
    """Löst Import-Ziele in vollqualifizierte Modulpfade auf (unterstützt relative Importe)."""
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
    """Außerhalb von src/agentic/ (ohne Tests) darf niemand interne Unterpakete
    von src.agentic importieren — ausschließlich die Fassade src.agentic ist erlaubt."""
    violations = []
    forbidden_prefixes = (
        "src.agentic.agents",
        "src.agentic.engine",
        "src.agentic.tools",
    )

    for py_file in _get_python_files(SRC_DIR):
        # src/agentic überspringen
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
    """src/agentic/engine/ darf auf Modul-Ebene nie aus agents oder tools importieren.
    Funktionslokal ist genau EIN verzögerter Import erlaubt: in jobs.py:53 (_run_job)."""
    engine_dir = SRC_DIR / "agentic" / "engine"
    top_level_violations = []
    delayed_agent_imports = []

    for py_file in _get_python_files(engine_dir):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))

        # 1. Top-Level-Knoten prüfen
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

    # Es darf genau EIN verzögerter Import in jobs.py existieren
    assert len(delayed_agent_imports) == 1, (
        f"Erwartet genau 1 verzögerten Import in engine/ (jobs.py), gefunden {len(delayed_agent_imports)}:\n"
        + "\n".join(f"{f}:{line} -> {target}" for f, line, target in delayed_agent_imports)
    )
    file_name, _, target = delayed_agent_imports[0]
    assert file_name == "jobs.py"
    assert "agentic.agents.task_agent" in target


def test_tools_do_not_import_agents_except_delegation():
    """src/agentic/tools/ darf außer delegation.py (das Agenten-Aufrufe kapselt)
    nie aus src.agentic.agents importieren. Insbesondere tasks.py darf nicht aus agents importieren."""
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
        f"Werkzeuge in tools/ dürfen außer delegation.py nicht aus agents/ importieren:\n"
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
        f"Schemas dürfen keine Logikschichten importieren:\n" + "\n".join(violations)
    )
