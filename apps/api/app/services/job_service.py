"""
app/services/job_service.py

Thin repository layer around JobDocument.
All job state transitions go through this service so the
router and worker stay decoupled from Beanie internals.
"""

from __future__ import annotations

from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import HTTPException

from app.models.documents import JobDocument, JobErrorCode, JobStatus, JobStep, Platform


class JobService:

    @staticmethod
    async def create(url: str, platform: Platform, user_id: str | None = None) -> JobDocument:
        job = JobDocument(url=url, platform=platform, user_id=user_id)
        await job.insert()
        return job

    @staticmethod
    async def get(job_id: str) -> JobDocument:
        try:
            oid = PydanticObjectId(job_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid job ID")
        job = await JobDocument.get(oid)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @staticmethod
    async def find_existing_queued(url: str) -> JobDocument | None:
        return await JobDocument.find_one(
            {"url": url, "status": {"$in": [JobStatus.QUEUED, JobStatus.PROCESSING]}}
        )

    @staticmethod
    async def set_processing(job: JobDocument, step: JobStep, message: str, progress: int) -> None:
        job.status = JobStatus.PROCESSING
        job.current_step = step
        job.progress_message = message
        job.progress = progress
        if not job.started_at:
            job.started_at = datetime.now(UTC)
        await job.save()

    @staticmethod
    async def set_completed(job: JobDocument, result_id: str) -> None:
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.result_id = result_id
        job.completed_at = datetime.now(UTC)
        await job.save()

    @staticmethod
    async def set_failed(
        job: JobDocument,
        error: str,
        error_code: JobErrorCode = JobErrorCode.UNKNOWN_ERROR,
    ) -> None:
        job.status = JobStatus.FAILED
        job.error = error
        job.error_code = error_code
        job.completed_at = datetime.now(UTC)
        await job.save()
