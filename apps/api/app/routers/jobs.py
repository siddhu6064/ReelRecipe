"""
app/routers/jobs.py

GET  /api/jobs/:job_id   — polling fallback
WS   /ws/jobs/:job_id   — real-time progress via WebSocket
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.documents import JobStatus
from app.services.job_service import JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
ws_router = APIRouter(prefix="/ws", tags=["websocket"])

POLL_INTERVAL_SECONDS = 1.0
TERMINAL_STATES = {JobStatus.COMPLETED, JobStatus.FAILED}


def _job_payload(job) -> dict:
    return {
        "jobId": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "currentStep": job.current_step,
        "progressMessage": job.progress_message,
        "error": job.error,
        "errorCode": job.error_code,
        # ReelRecipes: resultId points at a RecipeDocument, not a TripDocument
        "resultId": job.result_id,
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/{job_id}", summary="Poll job status")
async def get_job(job_id: str) -> dict:
    """
    REST polling endpoint for mobile clients and WebSocket fallback.
    Returns current job state including progress 0–100 and step message.
    """
    job = await JobService.get(job_id)
    return {"ok": True, "data": _job_payload(job)}


@ws_router.websocket("/jobs/{job_id}")
async def job_status_websocket(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket endpoint for real-time recipe extraction progress.
    Sends a JSON status message every second until the job reaches
    a terminal state (completed or failed), then closes.
    """
    await websocket.accept()
    try:
        while True:
            try:
                job = await JobService.get(job_id)
            except Exception as exc:
                await websocket.send_text(
                    json.dumps({"ok": False, "error": {"code": "JOB_NOT_FOUND", "message": str(exc)}})
                )
                break

            await websocket.send_text(json.dumps({"ok": True, "data": _job_payload(job)}))

            if job.status in TERMINAL_STATES:
                break

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
