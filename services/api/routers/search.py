from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from config import settings
from models.schemas import SearchRequest, SearchResponse, SearchResult
from services.embedder import SemanticSearchEngine
from qdrant_client.http.exceptions import UnexpectedResponse

logger = logging.getLogger(__name__)

router = APIRouter()
_engine = SemanticSearchEngine(
    voyage_api_key=settings.voyage_api_key or None,
    qdrant_url=settings.qdrant_url,
    qdrant_api_key=settings.qdrant_api_key,
)

@router.post("", response_model=SearchResponse)
async def semantic_search(req: SearchRequest) -> SearchResponse:
    try:
        hits = _engine.search(job_id=req.job_id, query=req.query,
                              top_k=req.top_k, language_filter=req.language_filter)
    except UnexpectedResponse as exc:
        logger.error("Search failed", exc_info=True)
        if exc.status_code == 404:
            raise HTTPException(
                404,
                f"Collection for job {req.job_id} not found in Qdrant. "
                "The embedding step may have failed during analysis — check Lambda logs.",
            )
        raise HTTPException(502, f"Qdrant error ({exc.status_code}): {exc}")
    except Exception as exc:
        logger.error("Search failed", exc_info=True)
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
