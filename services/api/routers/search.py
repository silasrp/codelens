from __future__ import annotations
from fastapi import APIRouter, HTTPException
from models.schemas import SearchRequest, SearchResponse, SearchResult
from services.embedder import SemanticSearchEngine

router = APIRouter()
_engine = SemanticSearchEngine()

@router.post("", response_model=SearchResponse)
async def semantic_search(req: SearchRequest) -> SearchResponse:
    try:
        hits = _engine.search(job_id=req.job_id, query=req.query,
                              top_k=req.top_k, language_filter=req.language_filter)
    except Exception as exc:
        raise HTTPException(500, f"Search failed: {exc}")
    return SearchResponse(
        query=req.query,
        job_id=req.job_id,
        results=[SearchResult(
            chunk_id=h.chunk_id, file_path=h.file_path,
            symbol_names=h.symbol_names, language=h.language,
            score=round(h.score, 4), snippet=h.code_snippet,
            generated_doc=h.generated_doc,
        ) for h in hits],
    )
