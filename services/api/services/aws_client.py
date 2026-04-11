"""Async-friendly AWS client for the FastAPI layer."""

from __future__ import annotations

import asyncio
import os
import time
from functools import partial
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config


class AWSClient:
    def __init__(self) -> None:
        endpoint = os.environ.get("AWS_ENDPOINT_URL")
        region   = os.environ.get("AWS_DEFAULT_REGION", "eu-west-2")
        kwargs: dict[str, Any] = {"region_name": region}
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        cfg = Config(retries={"max_attempts": 3, "mode": "adaptive"})

        self._dynamodb = boto3.resource("dynamodb", **kwargs, config=cfg)
        self._sqs      = boto3.client("sqs",      **kwargs)
        self._s3       = boto3.client("s3",        **kwargs)

        self._table     = self._dynamodb.Table(os.environ["DYNAMODB_TABLE"])
        self._queue_url = os.environ["SQS_QUEUE_URL"]
        self._bucket    = os.environ["S3_BUCKET"]

    # ── Jobs ────────────────────────────────────────────────────────────────

    async def create_job(self, job_id: str, repo_url: str, branch: str = "main") -> None:
        now = str(int(time.time()))
        await self._run(self._table.put_item, Item={
            "job_id":     job_id,
            "status":     "queued",
            "progress":   0,
            "repo_url":   repo_url,
            "branch":     branch,
            "created_at": now,
            "expires_at": int(time.time()) + 30 * 24 * 60 * 60,
        })

    async def get_job(self, job_id: str) -> dict | None:
        resp = await self._run(self._table.get_item, Key={"job_id": job_id})
        return resp.get("Item")

    async def list_jobs(self, limit: int = 20) -> list[dict]:
        resp  = await self._run(self._table.scan, Limit=limit)
        items = resp.get("Items", [])
        return sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)

    async def update_job_status(self, job_id: str, status: str,
                                progress: int | None = None,
                                error: str | None = None) -> None:
        expr   = "SET #s = :s"
        names  = {"#s": "status"}
        values: dict[str, Any] = {":s": status}
        if progress is not None:
            expr += ", progress = :p"; values[":p"] = progress
        if error:
            expr += ", error_message = :e"; values[":e"] = error
        await self._run(
            self._table.update_item,
            Key={"job_id": job_id},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

    # ── SQS ─────────────────────────────────────────────────────────────────

    async def send_sqs_message(self, body: str) -> str:
        resp = await self._run(self._sqs.send_message,
                               QueueUrl=self._queue_url, MessageBody=body)
        return resp["MessageId"]

    # ── S3 ──────────────────────────────────────────────────────────────────

    async def upload_directory(self, local_dir: str, s3_prefix: str,
                               exclude: set[str] | None = None) -> int:
        exclude = exclude or set()
        allowed = {".py",".ts",".tsx",".js",".jsx",".json",
                   ".yaml",".yml",".toml",".md",".rs",".go",".java"}
        skip_dirs = {".git","node_modules","__pycache__",".venv","dist","build"}
        count = 0
        for fp in Path(local_dir).rglob("*"):
            if not fp.is_file(): continue
            if fp.name in exclude: continue
            if fp.suffix not in allowed: continue
            if any(p in fp.parts for p in skip_dirs): continue
            key = f"{s3_prefix}/{fp.relative_to(local_dir)}"
            await self._run(self._s3.upload_file, str(fp), self._bucket, key)
            count += 1
        return count

    async def get_object_text(self, s3_key: str) -> str:
        resp = await self._run(self._s3.get_object, Bucket=self._bucket, Key=s3_key)
        return resp["Body"].read().decode("utf-8", errors="replace")

    async def list_objects(self, prefix: str) -> list[str]:
        keys: list[str] = []
        pager = self._s3.get_paginator("list_objects_v2")
        pages = await asyncio.get_running_loop().run_in_executor(
            None, lambda: list(pager.paginate(Bucket=self._bucket, Prefix=prefix))
        )
        for page in pages:
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    async def _run(self, fn, *args, **kwargs) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))
