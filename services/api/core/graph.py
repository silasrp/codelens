"""
Dependency graph construction and analysis using NetworkX.

Nodes = modules, edges = import relationships.
Provides cycle detection, centrality metrics, and a narrative
string suitable for injection into the Pass 3 LLM prompt.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import networkx as nx
    NX = True
except ImportError:
    NX = False

from .parser import ParsedFile


@dataclass
class ModuleNode:
    name: str
    file_path: str
    language: str
    symbol_count: int
    imports: list[str]
    resolved_deps: list[str]


@dataclass
class GraphMetrics:
    node_count: int
    edge_count: int
    cycle_count: int
    most_depended_on: list[tuple[str, int]]
    most_dependencies: list[tuple[str, int]]
    isolated_modules: list[str]
    has_cycles: bool
    cycles: list[list[str]]

    def to_narrative(self) -> str:
        parts = [f"The repository contains {self.node_count} modules "
                 f"with {self.edge_count} import edges."]
        if self.most_depended_on:
            top = ", ".join(f"'{m}' ({d} dependents)"
                            for m, d in self.most_depended_on[:5])
            parts.append(f"Most central modules: {top}.")
        if self.most_dependencies:
            top = ", ".join(f"'{m}' ({d} imports)"
                            for m, d in self.most_dependencies[:5])
            parts.append(f"Modules with most dependencies: {top}.")
        if self.has_cycles:
            cs = "; ".join(" → ".join(c) for c in self.cycles[:3])
            parts.append(f"WARNING: {self.cycle_count} circular dependency cycle(s): {cs}.")
        if self.isolated_modules:
            parts.append(f"Isolated modules: {', '.join(self.isolated_modules[:10])}.")
        return " ".join(parts)


class DependencyGraph:
    def __init__(self) -> None:
        self._graph: Any = nx.DiGraph() if NX else None
        self._modules: dict[str, ModuleNode] = {}
        self._fallback_edges: list[tuple[str, str]] = []

    @classmethod
    def build(cls, parsed_files: list[ParsedFile], repo_root: str = "") -> "DependencyGraph":
        g = cls()
        for pf in parsed_files:
            mod = cls._mod_name(pf.file_path, repo_root)
            resolved = cls._resolve(pf.module_imports, pf.file_path, repo_root, parsed_files)
            g._modules[mod] = ModuleNode(
                name=mod, file_path=pf.file_path, language=pf.language,
                symbol_count=pf.symbol_count, imports=pf.module_imports,
                resolved_deps=resolved,
            )
            if g._graph is not None:
                g._graph.add_node(mod, file_path=pf.file_path,
                                  language=pf.language, symbol_count=pf.symbol_count)

        for mod, node in g._modules.items():
            for dep in node.resolved_deps:
                if dep in g._modules:
                    if g._graph is not None:
                        g._graph.add_edge(mod, dep)
                    else:
                        g._fallback_edges.append((mod, dep))
        return g

    def metrics(self) -> GraphMetrics:
        if self._graph is None:
            return self._fallback_metrics()
        cycles = list(nx.simple_cycles(self._graph))
        return GraphMetrics(
            node_count=self._graph.number_of_nodes(),
            edge_count=self._graph.number_of_edges(),
            cycle_count=len(cycles),
            most_depended_on=sorted(self._graph.in_degree(), key=lambda x: x[1], reverse=True)[:10],
            most_dependencies=sorted(self._graph.out_degree(), key=lambda x: x[1], reverse=True)[:10],
            isolated_modules=list(nx.isolates(self._graph)),
            has_cycles=len(cycles) > 0,
            cycles=cycles[:5],
        )

    def topological_order(self) -> list[str]:
        if self._graph is None:
            return list(self._modules.keys())
        try:
            return list(reversed(list(nx.topological_sort(self._graph))))
        except Exception:
            return sorted(self._modules.keys())

    def module_context(self, module_name: str) -> dict:
        node = self._modules.get(module_name)
        if not node:
            return {}
        if self._graph is not None:
            pred = list(self._graph.predecessors(module_name))
            succ = list(self._graph.successors(module_name))
        else:
            pred = [a for a, b in self._fallback_edges if b == module_name]
            succ = [b for a, b in self._fallback_edges if a == module_name]
        return {"module": module_name, "imported_by": pred,
                "imports": succ, "symbol_count": node.symbol_count}

    def to_adjacency_list(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        edges = self._graph.edges() if self._graph else self._fallback_edges
        for src, dst in edges:
            result[src].append(dst)
        return dict(result)

    @staticmethod
    def _mod_name(file_path: str, repo_root: str) -> str:
        p = Path(file_path)
        if repo_root:
            try:
                p = p.relative_to(repo_root)
            except ValueError:
                pass
        return str(p.with_suffix("")).replace("/", ".").replace("\\", ".")

    @staticmethod
    def _resolve(imports: list[str], file_path: str, repo_root: str,
                 all_files: list[ParsedFile]) -> list[str]:
        known = {DependencyGraph._mod_name(pf.file_path, repo_root) for pf in all_files}
        resolved: list[str] = []
        for imp in imports:
            ident = _parse_import(imp)
            if ident and ident in known:
                resolved.append(ident)
        return resolved

    def _fallback_metrics(self) -> GraphMetrics:
        in_deg: dict[str, int] = defaultdict(int)
        out_deg: dict[str, int] = defaultdict(int)
        for s, d in self._fallback_edges:
            out_deg[s] += 1
            in_deg[d] += 1
        mods = list(self._modules.keys())
        return GraphMetrics(
            node_count=len(mods), edge_count=len(self._fallback_edges),
            cycle_count=0,
            most_depended_on=sorted(in_deg.items(), key=lambda x: x[1], reverse=True)[:10],
            most_dependencies=sorted(out_deg.items(), key=lambda x: x[1], reverse=True)[:10],
            isolated_modules=[m for m in mods if m not in in_deg and m not in out_deg],
            has_cycles=False, cycles=[],
        )


def _parse_import(imp: str) -> str | None:
    imp = imp.strip()
    if imp.startswith("from "):
        parts = imp.split()
        if len(parts) >= 2:
            mod = parts[1].lstrip(".")
            return mod.split(".")[0] if mod else None
    elif imp.startswith("import "):
        parts = imp.split()
        if len(parts) >= 2:
            return parts[1].split(".")[0]
    return None
