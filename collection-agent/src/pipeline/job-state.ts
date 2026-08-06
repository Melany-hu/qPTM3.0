/**
 * Job state file for UI / API polling (written beside per-job outDir).
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

export type JobStatus =
  | "pending"
  | "running"
  | "awaiting_continue"
  | "awaiting_upload"
  | "completed"
  | "rejected"
  | "error"

export type AwaitingUpload = "fulltext" | "supplementary"

export type StageName = "stage1" | "stage2" | "stage3" | "stage4" | "stage5" | "stage6"

export const STAGE_ORDER: StageName[] = [
  "stage1",
  "stage2",
  "stage3",
  "stage4",
  "stage5",
  "stage6",
]

export interface CollectionJobState {
  jobId: string
  pmid: string
  status: JobStatus
  currentStage: StageName | null
  /** Stage to run when the user clicks Continue */
  nextStage: StageName | null
  awaitingUpload: AwaitingUpload | null
  message: string
  stages: Partial<Record<StageName, "pending" | "running" | "completed" | "skipped" | "failed">>
  summary: Record<string, unknown>
  /** Ask user to contribute curated tables to qPTM after a successful parse */
  offerContribute?: boolean
  contribution?: {
    willing: boolean | null
    respondedAt?: string
    note?: string
  }
  error?: string
  updatedAt: string
}

export function jobStatePath(outDir: string): string {
  return join(outDir, "job.json")
}

export function readJobState(outDir: string): CollectionJobState | null {
  const path = jobStatePath(outDir)
  if (!existsSync(path)) return null
  try {
    return JSON.parse(readFileSync(path, "utf8")) as CollectionJobState
  } catch {
    return null
  }
}

export function writeJobState(outDir: string, state: CollectionJobState): void {
  mkdirSync(outDir, { recursive: true })
  const next: CollectionJobState = {
    ...state,
    updatedAt: new Date().toISOString(),
  }
  writeFileSync(jobStatePath(outDir), JSON.stringify(next, null, 2), "utf8")
}

export function patchJobState(
  outDir: string,
  patch: Partial<CollectionJobState> & { jobId: string; pmid: string },
): CollectionJobState {
  const prior = readJobState(outDir)
  const merged: CollectionJobState = {
    jobId: patch.jobId,
    pmid: patch.pmid,
    status: patch.status ?? prior?.status ?? "pending",
    // Allow explicit null to clear stage pointers (do not use ?? — null would keep prior)
    currentStage:
      patch.currentStage !== undefined ? patch.currentStage : (prior?.currentStage ?? null),
    nextStage: patch.nextStage !== undefined ? patch.nextStage : (prior?.nextStage ?? null),
    awaitingUpload:
      patch.awaitingUpload !== undefined ? patch.awaitingUpload : (prior?.awaitingUpload ?? null),
    message: patch.message ?? prior?.message ?? "",
    stages: { ...(prior?.stages ?? {}), ...(patch.stages ?? {}) },
    summary: { ...(prior?.summary ?? {}), ...(patch.summary ?? {}) },
    offerContribute:
      patch.offerContribute !== undefined
        ? patch.offerContribute
        : prior?.offerContribute,
    contribution:
      patch.contribution !== undefined ? patch.contribution : prior?.contribution,
    error: patch.error !== undefined ? patch.error : prior?.error,
    updatedAt: new Date().toISOString(),
  }
  writeJobState(outDir, merged)
  return merged
}

export function nextStageAfter(stage: StageName): StageName | null {
  const idx = STAGE_ORDER.indexOf(stage)
  if (idx < 0 || idx >= STAGE_ORDER.length - 1) return null
  return STAGE_ORDER[idx + 1]
}

export function shouldRunStage(
  resumeFrom: StageName | "auto",
  stage: StageName,
): boolean {
  if (resumeFrom === "auto") return true
  const fromIdx = STAGE_ORDER.indexOf(resumeFrom)
  const stageIdx = STAGE_ORDER.indexOf(stage)
  if (fromIdx < 0) return true
  return stageIdx >= fromIdx
}
