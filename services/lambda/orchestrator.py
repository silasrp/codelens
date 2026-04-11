"""
Multi-pass LLM analysis orchestrator — uses OpenAI GPT-4o.

Pass 1 — per-symbol docstrings (parallel, rate-limited)
Pass 2 — per-module summaries (sequential, upstream context injected)
Pass 3 — architecture narrative (single call, full graph + all summaries)

Rate limiting: three-layer approach via RateLimiter —
  1. Token budgeting (sliding 60s window)
  2. Concurrency semaphore
  3. Exponential backoff + jitter on 429
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable

import openai

# Make the shared core importable when running inside Lambda
_api_path = Path(__file__).parent.parent / "api"
sys.path.insert(0, str(_api_path))
sys.path.insert(0, str(_api_path / "services"))

from core.parser import ASTParser, ParsedFile
from core.chunker import SemanticChunker, Chunk, ChunkPlan
from core.graph import DependencyGraph
from state import JobStatus
from prompts import build_pass_one_prompt, build_pass_two_prompt, build_pass_three_prompt
from rate_limiter import RateLimiter, RateLimitConfig

logger = logging.getLogger(__name__)

MODEL              = "gpt-4o"
PASS_ONE_MAX_TOKENS   = 400
PASS_TWO_MAX_TOKENS   = 800
PASS_THREE_MAX_TOKENS = 2000

# Conservative config for free-tier / Tier-1 accounts (30k TPM limit).
# Raise tpm_limit and max_concurrent once your account is upgraded.
_RATE_CONFIG = RateLimitConfig(
    max_concurrent      = 3,       # max simultaneous in-flight requests
    tpm_limit           = 25_000,  # stay 5k below the 30k hard limit
    tpm_request_ceiling = 0.8,
    max_retries         = 6,
    base_delay          = 2.0,
    max_delay           = 60.0,
)


def _make_limiter() -> RateLimiter:
    return RateLimiter(
        client=openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", "")),
        model=MODEL,
        config=_RATE_CONFIG,
    )


class AnalysisOrchestrator:
    def __init__(
        self,
        job_id: str,
        source_map: dict[str, str],
        supported_languages: list[str],
        on_progress: Callable[[int, JobStatus], None] | None = None,
    ) -> None:
        self.job_id = job_id
        self.source_map = source_map
        self.supported_languages = supported_languages
        self.on_progress = on_progress or (lambda pct, phase: None)

        self._parser  = ASTParser()
        self._chunker = SemanticChunker()

        self._parsed_files: list[ParsedFile] = []
        self._chunk_plan:   ChunkPlan | None  = None
        self._graph:        DependencyGraph | None = None

        self._pass_one_results: dict[str, str] = {}
        self._pass_two_results: dict[str, str] = {}
        self._architecture_doc: str = ""

    # ── Phase 0: Parse + chunk ──────────────────────────────────────────────

    def parse_and_chunk(self) -> None:
        logger.info("[%s] Parsing %d files", self.job_id, len(self.source_map))
        for rel_path, content in self.source_map.items():
            if not self._parser.can_parse(rel_path):
                continue
            parsed = self._parser.parse_file(rel_path, content)
            if parsed and parsed.symbol_count > 0:
                self._parsed_files.append(parsed)

        self._chunk_plan = self._chunker.chunk_repository(self._parsed_files)
        self._graph      = DependencyGraph.build(self._parsed_files)
        logger.info("[%s] %s", self.job_id, self._chunk_plan.summary())

    # ── Pass 1: Per-symbol docstrings (async, rate-limited) ─────────────────

    def run_pass_one(self) -> None:
        if not self._chunk_plan:
            raise RuntimeError("Call parse_and_chunk() first")
        logger.info("[%s] Pass 1: %d chunks", self.job_id, len(self._chunk_plan.chunks))
        asyncio.run(self._pass_one_async(self._chunk_plan.chunks))

    async def _pass_one_async(self, chunks: list[Chunk]) -> None:
        # One RateLimiter instance shared across all Pass 1 coroutines so the
        # token window and semaphore are global — not per-coroutine.
        limiter = _make_limiter()

        SYSTEM = (
            "You are an expert code documentation writer. "
            "Respond with concise, accurate technical documentation only."
        )

        async def analyse(chunk: Chunk) -> None:
            try:
                result = await limiter.chat(
                    system=SYSTEM,
                    user=build_pass_one_prompt(chunk),
                    max_tokens=PASS_ONE_MAX_TOKENS,
                )
                self._pass_one_results[chunk.chunk_id] = result
                chunk.generated_doc = result
                chunk.pass_level    = 1
            except Exception as exc:
                logger.warning("Pass 1 failed for %s: %s", chunk.chunk_id, exc)
                self._pass_one_results[chunk.chunk_id] = ""

        await asyncio.gather(*[analyse(c) for c in chunks])

    # ── Pass 2: Per-module summaries ────────────────────────────────────────

    def run_pass_two(self) -> None:
        if not self._chunk_plan or not self._graph:
            raise RuntimeError("Call parse_and_chunk() first")
        asyncio.run(self._pass_two_async())

    async def _pass_two_async(self) -> None:
        limiter      = _make_limiter()
        ordered      = self._graph.topological_order()
        files_by_mod = {
            DependencyGraph._mod_name(pf.file_path, ""): pf
            for pf in self._parsed_files
        }

        SYSTEM = (
            "You are a senior software engineer writing internal technical "
            "documentation. Focus on design intent, not mechanical descriptions."
        )

        # Pass 2 must respect topological order (dependencies before dependents)
        # so we process sequentially, not in parallel.
        for mod in ordered:
            pf = files_by_mod.get(mod)
            if not pf:
                continue
            file_chunks = self._chunk_plan.chunks_for_file(pf.file_path)
            if not file_chunks:
                continue

            chunk_docs = {c.chunk_id: self._pass_one_results.get(c.chunk_id, "")
                          for c in file_chunks}
            ctx      = self._graph.module_context(mod)
            upstream = {dep: self._pass_two_results[dep]
                        for dep in ctx.get("imports", [])
                        if dep in self._pass_two_results}

            try:
                summary = await limiter.chat(
                    system=SYSTEM,
                    user=build_pass_two_prompt(pf, chunk_docs, ctx, upstream),
                    max_tokens=PASS_TWO_MAX_TOKENS,
                )
                self._pass_two_results[mod] = summary
                logger.info("[%s] Pass 2 done: %s", self.job_id, mod)
            except Exception as exc:
                logger.warning("Pass 2 failed for %s: %s", mod, exc)
                self._pass_two_results[mod] = ""

    # ── Pass 3: Architecture narrative ─────────────────────────────────────

    def run_pass_three(self) -> None:
        if not self._graph:
            raise RuntimeError("Call parse_and_chunk() first")
        asyncio.run(self._pass_three_async())

    async def _pass_three_async(self) -> None:
        limiter = _make_limiter()
        metrics = self._graph.metrics()

        SYSTEM = (
            "You are a staff engineer writing the architecture section of a system "
            "design document. Be specific about patterns, trade-offs, and coupling. "
            "Write for experienced engineers joining this codebase."
        )

        try:
            self._architecture_doc = await limiter.chat(
                system=SYSTEM,
                user=build_pass_three_prompt(
                    graph_narrative=metrics.to_narrative(),
                    module_summaries=self._pass_two_results,
                    adjacency=self._graph.to_adjacency_list(),
                ),
                max_tokens=PASS_THREE_MAX_TOKENS,
            )
            logger.info("[%s] Pass 3 done: %d chars", self.job_id, len(self._architecture_doc))
        except Exception as exc:
            logger.error("Pass 3 failed: %s", exc)
            self._architecture_doc = "Architecture analysis unavailable."

    # ── Embedding + indexing ────────────────────────────────────────────────

    def embed_and_index(self) -> None:
        if not self._chunk_plan:
            return
        try:
            from services.embedder import ChunkEmbedder
            ChunkEmbedder().upsert_chunks(
                job_id=self.job_id,
                chunks=self._chunk_plan.chunks,
                pass_one_docs=self._pass_one_results,
            )
            logger.info("[%s] Embedded %d chunks", self.job_id, len(self._chunk_plan.chunks))
        except Exception as exc:
            logger.warning("Embedding failed (non-fatal): %s", exc)

    # ── Finalise ────────────────────────────────────────────────────────────

    def finalise(self) -> dict:
        docs: dict[str, str] = {}
        for mod, summary in self._pass_two_results.items():
            if summary:
                docs[f"modules/{mod}.md"] = f"# {mod}\n\n{summary}\n"
        docs["ARCHITECTURE.md"] = self._architecture_doc
        manifest = {
            "job_id": self.job_id,
            "module_count": len(self._pass_two_results),
            "total_chunks": len(self._chunk_plan.chunks) if self._chunk_plan else 0,
            "dependency_graph": self._graph.to_adjacency_list() if self._graph else {},
            "modules": list(self._pass_two_results.keys()),
        }
        docs["manifest.json"] = json.dumps(manifest, indent=2)
        return {
            "total_chunks": manifest["total_chunks"],
            "module_count": manifest["module_count"],
            "s3_key": "",
            "_docs_payload": docs,
        }
