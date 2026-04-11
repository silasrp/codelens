"""
Prompt templates for the three-pass LLM analysis.
Model-agnostic — works with OpenAI, Anthropic, or any chat API.
"""

from __future__ import annotations
from textwrap import dedent
from core.chunker import Chunk
from core.parser import ParsedFile


def build_pass_one_prompt(chunk: Chunk) -> str:
    symbol_list = "\n".join(
        f"- `{s.name}` ({s.kind})"
        + (f" — existing docstring: {s.docstring}" if s.docstring else "")
        for s in chunk.symbols
    )
    return dedent(f"""
    You are documenting a {chunk.language} codebase. Analyse the code and write documentation.

    ## Symbols in this chunk
    {symbol_list}

    ## Code
    ```{chunk.language}
    {chunk.content}
    ```

    ## Instructions
    For each symbol write:
    1. A one-sentence summary of what it does (not how)
    2. Any non-obvious behaviour, side effects, or constraints
    3. For functions/methods: what it returns and under what conditions

    Format:

    ### `<symbol_name>`
    <documentation>

    Be precise and concise. Start each description with an imperative verb.
    Do not repeat the code. Do not write "This function...".
    """).strip()


def build_pass_two_prompt(
    pf: ParsedFile,
    chunk_docs: dict[str, str],
    module_ctx: dict,
    upstream_summaries: dict[str, str],
) -> str:
    symbol_docs = "\n\n".join(
        f"**{cid[:8]}**\n{doc}"
        for cid, doc in chunk_docs.items() if doc
    )
    imported_by = module_ctx.get("imported_by", [])
    imports_mods = module_ctx.get("imports", [])
    upstream = ""
    if upstream_summaries:
        upstream = "## Dependency summaries\n"
        for dep, summary in list(upstream_summaries.items())[:5]:
            upstream += f"\n### `{dep}`\n{summary[:400]}\n"

    return dedent(f"""
    You are writing internal technical documentation for a {pf.language} module.

    ## Module: `{pf.module_name}` ({pf.file_path})
    **Imported by:** {', '.join(imported_by) if imported_by else 'nothing (entry point or leaf)'}
    **Imports:** {', '.join(imports_mods) if imports_mods else 'no internal modules'}
    **Symbol count:** {pf.symbol_count}

    {upstream}

    ## Per-symbol documentation (Pass 1 output)
    {symbol_docs}

    ## Instructions
    Write a module-level summary covering:
    1. **Purpose** — What problem does this module solve?
    2. **Responsibilities** — What is in scope and out of scope?
    3. **Key abstractions** — Most important types, functions, classes and how they relate.
    4. **Design decisions** — Notable patterns or trade-offs visible in the code.
    5. **Integration** — How this module fits the larger system.

    Write in continuous prose, not bullet points. Be specific. 3–5 paragraphs.
    """).strip()


def build_pass_three_prompt(
    graph_narrative: str,
    module_summaries: dict[str, str],
    adjacency: dict[str, list[str]],
) -> str:
    summaries = ""
    for mod, summary in list(module_summaries.items()):
        if summary:
            summaries += f"\n\n### `{mod}`\n{summary[:600]}"

    adj_lines = [f"  {src} → [{', '.join(dsts)}]"
                 for src, dsts in list(adjacency.items())[:30]]
    adj = "\n".join(adj_lines) or "  (no internal dependencies resolved)"

    return dedent(f"""
    You are a staff engineer writing ARCHITECTURE.md for a software project.

    ## Dependency graph
    {graph_narrative}

    ## Adjacency list (A → [modules A imports])
    {adj}

    ## Module summaries
    {summaries}

    ## Instructions
    Write a comprehensive ARCHITECTURE.md covering:

    1. **System overview** — What does this codebase do?
    2. **Layer structure** — Major subsystems, using the dependency graph to identify layers.
    3. **Key data flows** — 1–2 end-to-end flows using specific module names.
    4. **Coupling analysis** — Central modules, concerning patterns, circular dependencies.
    5. **Recommended reading order** — For a new engineer joining the team.

    Write in technical prose. Reference actual module names. Minimum 600 words.
    """).strip()
