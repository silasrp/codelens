from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from services.aws_client import AWSClient

router = APIRouter()
aws    = AWSClient()

@router.get("/{job_id}/architecture", response_class=PlainTextResponse)
async def get_architecture(job_id: str) -> str:
    try:
        return await aws.get_object_text(f"results/{job_id}/ARCHITECTURE.md")
    except Exception:
        raise HTTPException(404, "Architecture doc not found")

@router.get("/{job_id}/modules")
async def list_modules(job_id: str) -> list[dict]:
    try:
        keys = await aws.list_objects(f"results/{job_id}/modules/")
        return [{"module_name": k.split("/")[-1].replace(".md", ""),
                 "url": f"/api/docs/{job_id}/module/{k.split('/')[-1].replace('.md','')}"}
                for k in keys]
    except Exception as exc:
        raise HTTPException(500, str(exc))

@router.get("/{job_id}/module/{module_name}", response_class=PlainTextResponse)
async def get_module(job_id: str, module_name: str) -> str:
    try:
        return await aws.get_object_text(f"results/{job_id}/modules/{module_name}.md")
    except Exception:
        raise HTTPException(404, f"Module '{module_name}' not found")

@router.get("/{job_id}/manifest")
async def get_manifest(job_id: str) -> dict:
    try:
        raw = await aws.get_object_text(f"results/{job_id}/manifest.json")
        return json.loads(raw)
    except Exception:
        raise HTTPException(404, "Manifest not found")
