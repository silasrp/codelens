from enum import Enum

class JobStatus(str, Enum):
    QUEUED            = "queued"
    CLONED            = "cloned"
    PARSING           = "parsing"
    ANALYZING_SYMBOLS = "analyzing_symbols"
    ANALYZING_MODULES = "analyzing_modules"
    SYNTHESIZING      = "synthesizing"
    EMBEDDING         = "embedding"
    STORING           = "storing"
    COMPLETE          = "complete"
    FAILED            = "failed"

class JobState:
    def __init__(self, item: dict) -> None:
        self.job_id:          str            = item["job_id"]
        self.status:          JobStatus      = JobStatus(item.get("status", "queued"))
        self.progress:        int            = int(item.get("progress", 0))
        self.repo_url:        str | None     = item.get("repo_url")
        self.error_message:   str | None     = item.get("error_message")
        self.result_manifest: str | None     = item.get("result_manifest")
