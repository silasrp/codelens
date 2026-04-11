"""Unit tests for AST parser and semantic chunker — no network calls."""

from __future__ import annotations
import pytest
from core.parser import ASTParser
from core.chunker import SemanticChunker

PYTHON_SAMPLE = '''
import os
from pathlib import Path

class DataLoader:
    """Loads training data from disk."""

    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)

    def load(self, split: str) -> list[dict]:
        """Load a dataset split."""
        path = self.data_dir / f"{split}.json"
        with open(path) as f:
            import json
            return json.load(f)

    def _validate_split(self, split: str) -> None:
        valid = {"train", "val", "test"}
        if split not in valid:
            raise ValueError(f"Unknown split: {split!r}")


def preprocess(text: str, lowercase: bool = True) -> str:
    """Normalise text for model input."""
    if lowercase:
        text = text.lower()
    return text.strip()


def batch(items: list, size: int) -> list[list]:
    """Yield successive n-sized chunks from a list."""
    return [items[i : i + size] for i in range(0, len(items), size)]
'''.strip()

TYPESCRIPT_SAMPLE = '''
import { readFileSync } from "fs";

interface Config { apiUrl: string; timeout: number; }

function loadConfig(path: string): Config {
    const raw = readFileSync(path, "utf-8");
    return JSON.parse(raw) as Config;
}

const fetchWithRetry = async (url: string, retries = 3): Promise<Response> => {
    for (let i = 0; i < retries; i++) {
        try { return await fetch(url); }
        catch (err) { if (i === retries - 1) throw err; }
    }
    throw new Error("unreachable");
};
'''.strip()


class TestASTParser:
    def setup_method(self) -> None:
        self.parser = ASTParser()

    def test_can_parse_python(self):
        assert self.parser.can_parse("module.py")

    def test_can_parse_typescript(self):
        assert self.parser.can_parse("App.tsx")
        assert self.parser.can_parse("client.ts")

    def test_rejects_unsupported(self):
        assert not self.parser.can_parse("image.png")
        assert not self.parser.can_parse("styles.css")

    def test_extracts_class(self):
        pf = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        assert pf is not None
        names = [s.name for s in pf.symbols if s.kind == "class"]
        assert "DataLoader" in names

    def test_extracts_methods(self):
        pf = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        assert pf is not None
        names = [s.name for s in pf.symbols if s.kind == "method"]
        assert "load" in names
        assert "_validate_split" in names

    def test_extracts_free_functions(self):
        pf = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        assert pf is not None
        names = [s.name for s in pf.symbols if s.kind == "function"]
        assert "preprocess" in names
        assert "batch" in names

    def test_names_are_not_keywords(self):
        """Regression: name_node.text must be used, not raw line split."""
        pf = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        assert pf is not None
        for sym in pf.symbols:
            assert sym.name not in ("def", "class", "async")

    def test_extracts_imports(self):
        pf = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        assert pf is not None
        combined = " ".join(pf.module_imports)
        assert "os" in combined or "pathlib" in combined

    def test_typescript_extracts_functions(self):
        pf = self.parser.parse_file("client.ts", TYPESCRIPT_SAMPLE)
        assert pf is not None
        names = [s.name for s in pf.symbols if s.kind == "function"]
        assert "loadConfig" in names or "fetchWithRetry" in names

    def test_chunk_id_is_stable(self):
        pf1 = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        pf2 = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        assert [s.chunk_id for s in pf1.symbols] == [s.chunk_id for s in pf2.symbols]

    def test_line_numbers_populated(self):
        pf = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        assert pf is not None
        for sym in pf.symbols:
            assert sym.start_line >= 1
            assert sym.end_line >= sym.start_line


class TestSemanticChunker:
    def setup_method(self) -> None:
        self.parser  = ASTParser()
        self.chunker = SemanticChunker(token_budget=1000)

    def test_produces_chunks(self):
        pf   = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        plan = self.chunker.chunk_repository([pf])
        assert plan.total_chunks > 0

    def test_no_chunk_exceeds_budget(self):
        pf   = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        plan = self.chunker.chunk_repository([pf])
        for chunk in plan.chunks:
            assert chunk.estimated_tokens < self.chunker.token_budget * 2

    def test_chunks_contain_symbols(self):
        pf   = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        plan = self.chunker.chunk_repository([pf])
        for chunk in plan.chunks:
            assert len(chunk.symbols) >= 1

    def test_file_filter(self):
        pf1  = self.parser.parse_file("a.py", PYTHON_SAMPLE)
        pf2  = self.parser.parse_file("b.py", PYTHON_SAMPLE)
        plan = self.chunker.chunk_repository([pf1, pf2])
        assert all(c.file_path == "a.py" for c in plan.chunks_for_file("a.py"))
        assert all(c.file_path == "b.py" for c in plan.chunks_for_file("b.py"))

    def test_method_chunks_have_preamble(self):
        pf   = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        plan = self.chunker.chunk_repository([pf])
        method_chunks = [c for c in plan.chunks
                         if any(s.kind == "method" for s in c.symbols)]
        for chunk in method_chunks:
            assert chunk.preamble

    def test_empty_file_no_chunks(self):
        pf   = self.parser.parse_file("empty.py", "# comment")
        plan = self.chunker.chunk_repository([pf] if pf else [])
        assert plan.total_chunks == 0

    def test_summary_string(self):
        pf   = self.parser.parse_file("loader.py", PYTHON_SAMPLE)
        plan = self.chunker.chunk_repository([pf])
        assert "chunks" in plan.summary()
        assert "tokens" in plan.summary()
