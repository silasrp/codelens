"""AWS Lambda handler — triggered by SQS, runs the full analysis pipeline."""

from __future__ import annotations

import json
import logging
import os
import traceback
from typing import Any

import boto3

from orchestrator import AnalysisOrchestrator
from state import JobState, JobStatus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-2"))
_s3       = boto3.client("s3")
_table    = _dynamodb.Table(os.environ["DYNAMODB_TABLE"])
_bucket   = os.environ["S3_BUCKET"]


def handler(event: dict, context: Any) -> dict:
    for record in event.get("Records", []):
        job_id = "<unknown>"
        try:
            body   = json.loads(record["body"])
            job_id = body["job_id"]
            logger.info("Starting job %s", job_id)
            _set_status(job_id, JobStatus.PARSING, 5)
            _run(job_id, body)
        except Exception as exc:
            logger.error("Job %s failed:\n%s", job_id, traceback.format_exc())
            _set_status(job_id, JobStatus.FAILED, 0, error=str(exc))
    return {"batchItemFailures": []}


def _run(job_id: str, payload: dict) -> None:
    s3_prefix     = payload["s3_prefix"]
    languages     = payload.get("languages", ["python", "typescript", "javascript"])
    changed_files = payload.get("changed_files")

    _set_status(job_id, JobStatus.PARSING, 10)
    source_map = _download_source(s3_prefix)
    if changed_files:
        source_map = {k: v for k, v in source_map.items() if k in changed_files}

    orch = AnalysisOrchestrator(
        job_id=job_id,
        source_map=source_map,
        supported_languages=languages,
        on_progress=lambda pct, phase: _set_status(job_id, phase, pct),
    )

    _set_status(job_id, JobStatus.PARSING, 15)
    orch.parse_and_chunk()

    _set_status(job_id, JobStatus.ANALYZING_SYMBOLS, 30)
    orch.run_pass_one()

    _set_status(job_id, JobStatus.ANALYZING_MODULES, 60)
    orch.run_pass_two()

    _set_status(job_id, JobStatus.SYNTHESIZING, 80)
    orch.run_pass_three()

    _set_status(job_id, JobStatus.EMBEDDING, 85)
    orch.embed_and_index()

    _set_status(job_id, JobStatus.STORING, 92)
    manifest = orch.finalise()
    _upload_results(job_id, manifest)

    _set_status(job_id, JobStatus.COMPLETE, 100, manifest=manifest)
    logger.info("Job %s complete — %d chunks, %d modules",
                job_id, manifest["total_chunks"], manifest["module_count"])


def _set_status(job_id: str, status: JobStatus, progress: int,
                error: str | None = None, manifest: dict | None = None) -> None:
    expr   = "SET #s = :s, progress = :p"
    names  = {"#s": "status"}
    values: dict[str, Any] = {":s": status.value, ":p": progress}
    if error:
        expr += ", error_message = :e"
        values[":e"] = error
    if manifest:
        expr += ", result_manifest = :m"
        values[":m"] = json.dumps(manifest)
    _table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def _download_source(s3_prefix: str) -> dict[str, str]:
    source: dict[str, str] = {}
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            key      = obj["Key"]
            relative = key[len(s3_prefix):].lstrip("/")
            body     = _s3.get_object(Bucket=_bucket, Key=key)["Body"].read()
            source[relative] = body.decode("utf-8", errors="replace")
    logger.info("Downloaded %d files from s3://%s/%s", len(source), _bucket, s3_prefix)
    return source


def _upload_results(job_id: str, manifest: dict) -> None:
    docs = manifest.pop("_docs_payload", {})
    for filename, content in docs.items():
        key = f"results/{job_id}/{filename}"
        _s3.put_object(
            Bucket=_bucket, Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/markdown" if filename.endswith(".md") else "application/json",
        )
    manifest["s3_key"] = f"results/{job_id}/"
