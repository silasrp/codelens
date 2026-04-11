"""
Semantic chunker — groups AST symbols into LLM-ready chunks.

Keeps logical units together (class + its methods), respects a
token budget, and prepends import context so the model has full scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from .parser import CodeSymbol, ParsedFile

_CHARS_PER_TOKEN = 3.5
DEFAULT_TOKEN_BUDGET = 3_000


@dataclass
class Chunk:
    chunk_id: str
    file_path: str
    language: str
    symbols: list[CodeSymbol]
    preamble: str = ""
    generated_doc: str | None = None
    pass_level: int = 0

    @property
    def content(self) -> str:
        parts = ([self.preamble, ""] if self.preamble else [])
        for s in self.symbols:
            parts.append(s.source)
        return "\n".join(parts)

    @property
    def estimated_tokens(self) -> int:
        return int(len(self.content) / _CHARS_PER_TOKEN)

    @property
    def primary_symbol(self) -> CodeSymbol:
        return self.symbols[0]

    @property
    def symbol_names(self) -> list[str]:
        return [s.name for s in self.symbols]


@dataclass
class ChunkPlan:
    chunks: list[Chunk]
    skipped_files: list[str] = field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    @property
    def estimated_total_tokens(self) -> int:
        return sum(c.estimated_tokens for c in self.chunks)

    def chunks_for_file(self, file_path: str) -> list[Chunk]:
        return [c for c in self.chunks if c.file_path == file_path]

    def summary(self) -> str:
        files = len({c.file_path for c in self.chunks})
        return (f"ChunkPlan: {self.total_chunks} chunks across {files} files, "
                f"~{self.estimated_total_tokens:,} total tokens")


class SemanticChunker:
    def __init__(self, token_budget: int = DEFAULT_TOKEN_BUDGET) -> None:
        self.token_budget = token_budget

    def chunk_repository(self, parsed_files: list[ParsedFile]) -> ChunkPlan:
        all_chunks: list[Chunk] = []
        skipped: list[str] = []
        for pf in parsed_files:
            try:
                all_chunks.extend(self._chunk_file(pf))
            except Exception as exc:
                skipped.append(f"{pf.file_path}: {exc}")
        return ChunkPlan(chunks=all_chunks, skipped_files=skipped)

    def _chunk_file(self, pf: ParsedFile) -> list[Chunk]:
        if not pf.symbols:
            return []
        import_block = "\n".join(dict.fromkeys(pf.module_imports))
        class_groups: dict[str, list[CodeSymbol]] = {}
        free: list[CodeSymbol] = []

        for sym in pf.symbols:
            if sym.kind == "class":
                class_groups.setdefault(sym.name, []).insert(0, sym)
            elif sym.kind == "method" and sym.parent_name:
                class_groups.setdefault(sym.parent_name, []).append(sym)
            else:
                free.append(sym)

        chunks: list[Chunk] = []
        for group in class_groups.values():
            chunks.extend(self._chunk_group(group, pf.file_path, pf.language, import_block))
        chunks.extend(self._batch_greedy(free, pf.file_path, pf.language, import_block))
        return chunks

    def _chunk_group(self, symbols: list[CodeSymbol], file_path: str,
                     language: str, preamble: str) -> list[Chunk]:
        if not symbols:
            return []
        class_sym = symbols[0]
        candidate = Chunk(chunk_id=class_sym.chunk_id, file_path=file_path,
                          language=language, symbols=symbols, preamble=preamble)
        if candidate.estimated_tokens <= self.token_budget:
            return [candidate]
        class_preamble = preamble + ("\n\n" if preamble else "") + class_sym.source
        chunks = [Chunk(chunk_id=class_sym.chunk_id, file_path=file_path,
                        language=language, symbols=[class_sym], preamble=preamble)]
        chunks.extend(self._batch_greedy(symbols[1:], file_path, language, class_preamble))
        return chunks

    def _batch_greedy(self, symbols: list[CodeSymbol], file_path: str,
                      language: str, preamble: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        batch: list[CodeSymbol] = []
        pre_tokens = int(len(preamble) / _CHARS_PER_TOKEN)
        running = pre_tokens

        for sym in symbols:
            sym_tokens = int(len(sym.source) / _CHARS_PER_TOKEN)
            if sym_tokens + pre_tokens > self.token_budget:
                if batch:
                    chunks.append(self._make(batch, file_path, language, preamble))
                    batch, running = [], pre_tokens
                chunks.append(self._make([sym], file_path, language, preamble))
                continue
            if running + sym_tokens > self.token_budget and batch:
                chunks.append(self._make(batch, file_path, language, preamble))
                batch, running = [], pre_tokens
            batch.append(sym)
            running += sym_tokens

        if batch:
            chunks.append(self._make(batch, file_path, language, preamble))
        return chunks

    def _make(self, symbols: list[CodeSymbol], file_path: str,
              language: str, preamble: str) -> Chunk:
        return Chunk(chunk_id=symbols[0].chunk_id, file_path=file_path,
                     language=language, symbols=symbols, preamble=preamble)
