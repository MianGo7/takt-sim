import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "takt"
DIAGRAMS = ROOT / "docs" / "diagrams"

# Calls in the sequence diagram that belong to the simulation library and not
# to the package: the environment and its method that runs the model.
LIBRARY_CALLS = {"Environment", "run"}


def import_edges() -> set[tuple[str, str]]:
    """Return the imports of every module as pairs of importer and imported name.

    A module of the package is named by its file, and a library by its top-level
    name. The standard library is left out.
    """
    edges = set()
    for path in SOURCE.glob("*.py"):
        if path.stem == "__init__":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")
                if top[0] == "takt":
                    edges.add((path.stem, top[1]))
                elif top[0] not in sys.stdlib_module_names and top[0] != "__future__":
                    edges.add((path.stem, top[0]))
    return edges


def defined_names() -> set[str]:
    names = set()
    for path in SOURCE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef | ast.ClassDef):
                names.add(node.name)
    return names


def test_the_component_diagram_has_exactly_the_imports_of_the_source():
    text = (DIAGRAMS / "package-components.puml").read_text()

    drawn = set(re.findall(r"^(\w+) --> (\w+)$", text, flags=re.MULTILINE))

    assert drawn == import_edges()


def test_the_component_diagram_shows_every_module_of_the_package():
    text = (DIAGRAMS / "package-components.puml").read_text()
    modules = {p.stem for p in SOURCE.glob("*.py") if p.stem != "__init__"}

    declared = set(re.findall(r'^  component "(\w+)" as \w+$', text, flags=re.MULTILINE))

    assert declared == modules


def test_every_function_and_class_in_the_sequence_diagram_exists_in_the_source():
    text = (DIAGRAMS / "replication-sequence.puml").read_text()
    participants = re.findall(r'^participant "(\w+)"', text, flags=re.MULTILINE)
    messages = [line for line in text.splitlines() if not line.startswith("'") and ("->" in line)]
    calls = re.findall(r"\b(\w+)\(", "\n".join(messages))

    unknown = (set(participants) | set(calls)) - defined_names() - LIBRARY_CALLS

    assert unknown == set()
    assert {"run_experiment", "run_line", "Line", "line_indicators"} <= set(participants)
