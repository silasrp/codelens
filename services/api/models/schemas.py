from __future__ import annotations
from enum import Enum
from pydantic import AnyHttpUrl, BaseModel, Field

class Language(str, Enum):
    python     = "python"
    typescript = "typescript"
    javascript = "javascript"

class AnalysisRequest(BaseModel):
    repo_url:    AnyHttpUrl
    branch:      str      = "main"
    languages:   list[Language] = [Language.python, Language.typescript, Language.javascript]
    incremental: bool = False

class SubmitResponse(BaseModel):
    job_id: str
    status: str

class JobStatus(str, Enum):
    queued            = "queued"
    cloned            = "cloned"
    parsing           = "parsing"
    analyzing_symbols = "analyzing_symbols"
    analyzing_modules = "analyzing_modules"
    synthesizing      = "synthesizing"
    embedding         = "embedding"
    storing           = "storing"
    complete          = "complete"
    failed            = "failed"

class JobStatusResponse(BaseModel):
    job_id:          str
    status:          JobStatus
    progress:        int       = Field(0, ge=0, le=100)
    repo_url:        str | None = None
    error_message:   str | None = None
    result_manifest: str | None = None

class SearchRequest(BaseModel):
    job_id:          str
    query:           str  = Field(..., min_length=1, max_length=500)
    top_k:           int  = Field(5, ge=1, le=20)
    language_filter: Language | None = None

class SearchResult(BaseModel):
    chunk_id:     str
    file_path:    str
    symbol_names: list[str]
    language:     str
    score:        float
    snippet:      str
    generated_doc: str

class SearchResponse(BaseModel):
    query:   str
    results: list[SearchResult]
    job_id:  str
