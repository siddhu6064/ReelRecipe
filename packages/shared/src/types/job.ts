// packages/shared/src/types/job.ts

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'

export type JobStep =
  | 'fetching_video'
  | 'transcribing'
  | 'extracting_recipe'
  | 'fetching_nutrition'
  | 'finalizing'

export type JobErrorCode =
  | 'UNSUPPORTED_PLATFORM'
  | 'VIDEO_UNAVAILABLE'
  | 'PRIVATE_VIDEO'
  | 'TRANSCRIPT_FAILED'
  | 'NO_RECIPE_FOUND'
  | 'EXTRACTION_FAILED'
  | 'RATE_LIMITED'
  | 'UNKNOWN_ERROR'

export interface JobStatusResponse {
  jobId: string
  status: JobStatus
  progress: number           // 0–100
  currentStep: JobStep | null
  progressMessage: string | null
  error: string | null
  errorCode: JobErrorCode | null
  /** ID of the created RecipeDocument — set when status === 'completed' */
  resultId: string | null
  completedAt: string | null
}
