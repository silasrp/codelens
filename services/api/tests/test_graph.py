"""Unit tests for the dependency graph builder."""

from __future__ import annotations
import pytest
from core.parser import ASTParser
from core.graph import DependencyGraph

UTILS_PY = "def format_date(ts: int) -> str:\n    return str(ts)\n"

MODELS_PY = """
from utils import format_date

class User:
    def __init__(self, name: str) -> None:
        self.name = name
"""

SERVICES_PY = """
from models import User
from utils import format_date

def create_user(name: str) -> User:
    return User(name)
"""

CYCLIC_A = "from cyclic_b import something\ndef a(): pass\n"
CYCLIC_B = "from cyclic_a import a\ndef something(): pass\n"


class TestDependencyGraph:
    def setup_method(self) -> None:
        self.parser = ASTParser()

    def _parse(self, files: dict[str, str]):
        out = []
        for path, src in files.items():
            pf = self.parser.parse_file(path, src)
            if pf:
                out.append(pf)
        return out

    def test_builds_without_error(self):
        parsed = self._parse({"utils.py": UTILS_PY, "models.py": MODELS_PY})
        assert DependencyGraph.build(parsed) is not None

    def test_correct_node_count(self):
        parsed = self._parse({"utils.py": UTILS_PY, "models.py": MODELS_PY,
                              "services.py": SERVICES_PY})
        assert DependencyGraph.build(parsed).metrics().node_count == 3

    def test_resolves_internal_import(self):
        parsed = self._parse({"utils.py": UTILS_PY, "models.py": MODELS_PY})
        adj    = DependencyGraph.build(parsed).to_adjacency_list()
        assert "utils" in adj.get("models", [])

    def test_most_depended_on_is_utils(self):
        parsed = self._parse({"utils.py": UTILS_PY, "models.py": MODELS_PY,
                              "services.py": SERVICES_PY})
        top = [m for m, _ in DependencyGraph.build(parsed).metrics().most_depended_on]
        assert "utils" in top

    def test_topological_order(self):
        parsed = self._parse({"utils.py": UTILS_PY, "models.py": MODELS_PY,
                              "services.py": SERVICES_PY})
        order = DependencyGraph.build(parsed).topological_order()
        if "utils" in order and "models" in order:
            assert order.index("utils") < order.index("models")

    def test_detects_cycles(self):
        parsed = self._parse({"cyclic_a.py": CYCLIC_A, "cyclic_b.py": CYCLIC_B})
        assert DependencyGraph.build(parsed).metrics().has_cycles

    def test_narrative_non_empty(self):
        parsed = self._parse({"utils.py": UTILS_PY, "models.py": MODELS_PY})
        narrative = DependencyGraph.build(parsed).metrics().to_narrative()
        assert isinstance(narrative, str) and len(narrative) > 20

    def test_module_context_neighbours(self):
        parsed = self._parse({"utils.py": UTILS_PY, "models.py": MODELS_PY,
                              "services.py": SERVICES_PY})
        ctx = DependencyGraph.build(parsed).module_context("models")
        assert "services" in ctx.get("imported_by", [])
        assert "utils"    in ctx.get("imports", [])
