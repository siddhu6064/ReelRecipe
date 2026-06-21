"""
app/workers/job_worker.py

ARQ background worker — one function per job type.

extract_recipe_job pipeline:
  1. Detect platform → adapter.fetch(url) → AdapterOutput
  2. Whisper fallback if no captions
  3. GPT-4o extraction → structured recipe dict
  4. Nutritionix macro fetch (non-blocking)
  5. Persist RecipeDocument → mark job COMPLETED with result_id
"""

from __future__ import annotations

import logging

from arq.connections import RedisSettings

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


async def extract_recipe_job(ctx: dict, job_id: str) -> None:  # noqa: ARG001
    """
    Main ARQ task.  Orchestrates the full recipe extraction pipeline.
    On unrecoverable errors the job is marked FAILED (not retried —
    recipe extraction failures are user-visible and should be surfaced).
    """
    from app.config.database import connect_db
    from app.models.documents import JobErrorCode, JobStep
    from app.services.job_service import JobService

    await connect_db()
    job = await JobService.get(job_id)

    try:
        # ── Step 1: fetch video signals ──────────────────────
        await JobService.set_processing(
            job, JobStep.FETCHING_VIDEO, "Fetching video…", progress=10
        )

        from app.adapters.registry import get_adapter
        from app.adapters.base import CaptionsSource

        adapter = get_adapter(job.platform)
        output = await adapter.fetch(job.url)

        # Persist video metadata onto the job for debugging
        job.transcript = output.transcript
        await job.save()

        # ── Step 2: Whisper fallback if no captions ──────────
        transcript = output.best_signal_text

        if not transcript or output.captions_source == CaptionsSource.NONE:
            await JobService.set_processing(
                job, JobStep.TRANSCRIBING, "Transcribing audio with Whisper…", progress=25
            )
            from app.services.extraction.whisper import transcribe_url
            transcript, _segments, _src = await transcribe_url(job.url)
            job.transcript = transcript
            await job.save()

        if not transcript:
            await JobService.set_failed(
                job,
                error="No usable transcript found for this video.",
                error_code=JobErrorCode.TRANSCRIPT_FAILED,
            )
            return

        # ── Step 3: GPT-4o recipe extraction ─────────────────
        await JobService.set_processing(
            job, JobStep.EXTRACTING_RECIPE, "Extracting recipe with AI…", progress=50
        )

        from app.services.extractor import extract_recipe

        try:
            recipe_data = await extract_recipe(
                transcript=transcript,
                source_url=job.url,
                video_title=output.title,
                thumbnail_url=output.thumbnail_url,
            )
        except ValueError as exc:
            await JobService.set_failed(
                job,
                error=str(exc),
                error_code=JobErrorCode.NO_RECIPE_FOUND,
            )
            return

        # Store extraction provenance on job
        job.extraction_model = recipe_data.pop("extraction_model", None)
        job.extraction_tokens = recipe_data.pop("extraction_tokens", 0)
        await job.save()

        # ── Step 4: Nutritionix macros (non-blocking) ────────
        await JobService.set_processing(
            job, JobStep.FETCHING_NUTRITION, "Fetching nutrition data…", progress=80
        )

        from app.services.nutrition import fetch_nutrition

        nutrition = await fetch_nutrition(
            ingredients=recipe_data.get("ingredients", []),
            servings=recipe_data.get("servings", 2),
        )
        if nutrition:
            recipe_data["nutrition"] = nutrition

        # ── Step 5: persist RecipeDocument ───────────────────
        await JobService.set_processing(
            job, JobStep.FINALIZING, "Saving recipe…", progress=95
        )

        from app.models.documents import RecipeDocument

        # Snapshot the raw AI extraction before saving — enables "Reset to original"
        from app.models.documents import RecipeIngredient, RecipeStep
        original_ingredients = [
            RecipeIngredient(**i) if isinstance(i, dict) else i
            for i in recipe_data.get("ingredients", [])
        ]
        original_steps = [
            RecipeStep(**s) if isinstance(s, dict) else s
            for s in recipe_data.get("steps", [])
        ]

        recipe = RecipeDocument(
            user_id=job.user_id or "anonymous",
            job_id=str(job.id),
            source_url=job.url,
            platform=job.platform,
            video_title=output.title,
            thumbnail_url=output.thumbnail_url,
            extraction_model=job.extraction_model,
            extraction_tokens=job.extraction_tokens,
            # Snapshot — written once, never overwritten by edits
            original_title=recipe_data.get("title"),
            original_servings=recipe_data.get("servings"),
            original_ingredients=original_ingredients,
            original_steps=original_steps,
            **recipe_data,
        )
        await recipe.insert()

        await JobService.set_completed(job, result_id=str(recipe.id))
        logger.info("recipe_extracted", job_id=job_id, recipe_id=str(recipe.id))

        # ── Push notification — non-blocking, failure never crashes worker ──
        if job.user_id:
            from app.models.documents import UserDocument
            from app.services.push_service import send_recipe_ready
            user = await UserDocument.find_one({"clerk_id": job.user_id})
            if user and user.push_token:
                await send_recipe_ready(
                    push_token=user.push_token,
                    recipe_title=recipe.title,
                    recipe_id=str(recipe.id),
                )

    except Exception as exc:
        logger.exception("extract_recipe_job_failed", job_id=job_id, error=str(exc))
        await JobService.set_failed(
            job,
            error=str(exc),
            error_code=JobErrorCode.UNKNOWN_ERROR,
        )


# ── ARQ Worker Settings ────────────────────────────────────────


class WorkerSettings:
    functions = [extract_recipe_job]
    max_jobs = 10
    job_timeout = 300   # 5 min max per job
    keep_result = 3600  # keep result in Redis for 1 h

    @property
    def redis_settings(self) -> RedisSettings:
        return RedisSettings.from_dsn(get_settings().redis_url)
