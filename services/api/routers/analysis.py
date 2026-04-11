from __future__ import annotations
import json, uuid, zipfile, tempfile
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
import git
from config import settings
from models.schemas import AnalysisRequest, JobStatusResponse, SubmitResponse
from services.aws_client import AWSClient

router = APIRouter()
aws    = AWSClient()

@router.post("/submit", response_model=SubmitResponse)
async def submit_repository(req: AnalysisRequest,
                             bg: BackgroundTasks) -> SubmitResponse:
    job_id    = str(uuid.uuid4())
    s3_prefix = f"source/{job_id}"
    await aws.create_job(job_id=job_id, repo_url=str(req.repo_url), branch=req.branch)
    bg.add_task(_clone_and_enqueue, job_id, str(req.repo_url),
                req.branch, s3_prefix, [l.value for l in req.languages])
    return SubmitResponse(job_id=job_id, status="queued")

@router.post("/upload", response_model=SubmitResponse)
async def upload_zip(file: UploadFile = File(...),
                     bg: BackgroundTasks = None) -> SubmitResponse:
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "Only .zip files accepted")
    job_id    = str(uuid.uuid4())
    s3_prefix = f"source/{job_id}"
    contents  = await file.read()
    await aws.create_job(job_id=job_id, repo_url=file.filename)
    bg.add_task(_unzip_and_enqueue, job_id, contents, s3_prefix)
    return SubmitResponse(job_id=job_id, status="queued")

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def job_status(job_id: str) -> JobStatusResponse:
    job = await aws.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return JobStatusResponse(**job)

@router.get("/jobs")
async def list_jobs(limit: int = 20) -> list[dict]:
    return await aws.list_jobs(limit=limit)

# ── Background tasks ────────────────────────────────────────────────────────

async def _clone_and_enqueue(job_id, repo_url, branch, s3_prefix, languages):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            git.Repo.clone_from(repo_url, tmp, branch=branch, depth=1)
            await aws.upload_directory(tmp, s3_prefix)
        await aws.update_job_status(job_id, "cloned", progress=8)
        await _enqueue(job_id, s3_prefix, languages)
    except Exception as exc:
        await aws.update_job_status(job_id, "failed", error=str(exc))

async def _unzip_and_enqueue(job_id, zip_contents, s3_prefix):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            zp = Path(tmp) / "upload.zip"
            zp.write_bytes(zip_contents)
            with zipfile.ZipFile(zp) as zf:
                zf.extractall(tmp)
            await aws.upload_directory(tmp, s3_prefix, exclude={"upload.zip"})
        await aws.update_job_status(job_id, "uploaded", progress=8)
        await _enqueue(job_id, s3_prefix, ["python", "typescript", "javascript"])
    except Exception as exc:
        await aws.update_job_status(job_id, "failed", error=str(exc))

async def _enqueue(job_id, s3_prefix, languages):
    msg = json.dumps({"job_id": job_id, "s3_prefix": s3_prefix,
                      "languages": languages, "incremental": False})
    await aws.send_sqs_message(msg)
    await aws.update_job_status(job_id, "queued", progress=10)
