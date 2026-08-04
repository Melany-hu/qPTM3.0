/**
 * Interactive single-PMID collection job orchestrator.
 * Runs one stage (or stage5→6 chain) per invocation; pauses for user Continue.
 */
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { ingestManualFulltext } from "../ingest/manual-fulltext.js"
import { ingestManualSupplementary } from "../ingest/manual-supp.js"
import { hasUserUploadedSupplementary } from "../ingest/register-supp-job.js"
import { isTabularUpload } from "../ingest/file-kind.js"
import { loadDotEnv } from "../runtime.js"
import type { FulltextRecord } from "../stage2/fulltext.js"
import { fulltextPmidDir } from "../stage2/fulltext.js"
import type { SuppScoutRecord } from "../pipeline/stage4-supp.js"
import { resolveAbstractsForPmids } from "../stage1/resolve-abstracts.js"
import { runStage1Screen } from "./stage1.js"
import { runStage2Discover } from "./stage2.js"
import { runStage2Fulltext } from "./stage2-fulltext.js"
import { runStage3Meta } from "./stage3.js"
import { runStage4SuppScout } from "./stage4-supp.js"
import { runStage5Parse } from "./stage5.js"
import { runStage6DownloadUrls } from "./stage6.js"
import {
  loadAllScreenResults,
  parseCsv,
  stage3LiteratureInfoPath,
} from "../utils/io.js"
import {
  nextStageAfter,
  patchJobState,
  shouldRunStage,
  type AwaitingUpload,
  type CollectionJobState,
  type StageName,
} from "./job-state.js"
import { setDataRoot, stage4SuppDir } from "../utils/io.js"

export interface RunCollectionJobOptions {
  jobId: string
  outDir: string
  pmid: string
  fulltextPath?: string
  supplementaryPath?: string
  resumeFrom?: StageName | "auto"
  concurrency?: number
  model?: string
  onLog?: (msg: string) => void
}

function loadFulltextMeta(pmid: string): FulltextRecord | null {
  const metaPath = join(fulltextPmidDir(pmid), "meta.json")
  if (!existsSync(metaPath)) return null
  try {
    return JSON.parse(readFileSync(metaPath, "utf8")) as FulltextRecord
  } catch {
    return null
  }
}

function needsFulltextUpload(pmid: string): boolean {
  const meta = loadFulltextMeta(pmid)
  if (!meta) return true
  return meta.status === "unavailable" && !meta.hasPdf && !meta.hasXml
}

function needsSupplementaryUpload(pmid: string, scout: SuppScoutRecord | null): boolean {
  const localZip = join(stage4SuppDir(), pmid, "supplementary.zip")
  if (existsSync(localZip)) return false
  if (!scout) return true
  if (scout.verdict === "likely_qptm_table" || scout.verdict === "has_tabular_supp") {
    return false
  }
  return (
    scout.verdict === "unavailable" ||
    scout.zipStatus === "none" ||
    scout.zipStatus === "not_found" ||
    scout.zipStatus === "error"
  )
}

function loadScoutRecord(outDir: string, pmid: string): SuppScoutRecord | null {
  const scoutPath = join(outDir, "stage4", "supp_scout.jsonl")
  if (!existsSync(scoutPath)) return null
  for (const line of readFileSync(scoutPath, "utf8").split("\n")) {
    const t = line.trim()
    if (!t) continue
    try {
      const row = JSON.parse(t) as SuppScoutRecord
      if (row.pmid === pmid) return row
    } catch {
      // skip
    }
  }
  return null
}

function loadStage3Row(pmid: string): Record<string, string> | null {
  const path = stage3LiteratureInfoPath()
  if (!existsSync(path)) return null
  const rows = parseCsv(readFileSync(path, "utf8"))
  if (rows.length < 2) return null
  const header = rows[0].map((h) => h.trim().replace(/^\uFEFF/, ""))
  const pmidIdx = header.findIndex((h) => h.toLowerCase() === "pmid")
  if (pmidIdx < 0) return null
  for (let i = 1; i < rows.length; i++) {
    const cols = rows[i]
    if ((cols[pmidIdx] ?? "").trim() !== pmid) continue
    const row: Record<string, string> = {}
    header.forEach((key, idx) => {
      row[key] = (cols[idx] ?? "").trim()
    })
    return row
  }
  return null
}

export async function runCollectionJob(options: RunCollectionJobOptions): Promise<CollectionJobState> {
  loadDotEnv()
  setDataRoot(options.outDir)
  const log = options.onLog ?? (() => {})
  const pmid = options.pmid.trim()
  const concurrency = options.concurrency ?? 2
  const resumeFrom = options.resumeFrom ?? "auto"

  let state = patchJobState(options.outDir, {
    jobId: options.jobId,
    pmid,
    status: "running",
    awaitingUpload: null,
    nextStage: null,
    message: "Starting collection agent…",
    stages: {},
  })

  const markStage = (stage: StageName, status: CollectionJobState["stages"][StageName]) => {
    state = patchJobState(options.outDir, {
      jobId: options.jobId,
      pmid,
      currentStage: stage,
      stages: { [stage]: status },
    })
  }

  const pauseContinue = (
    completedStage: StageName,
    message: string,
    summaryPatch: Record<string, unknown> = {},
  ): CollectionJobState => {
    const next = nextStageAfter(completedStage)
    return patchJobState(options.outDir, {
      jobId: options.jobId,
      pmid,
      status: next ? "awaiting_continue" : "completed",
      currentStage: completedStage,
      nextStage: next,
      awaitingUpload: null,
      message,
      summary: summaryPatch,
    })
  }

  const awaitUpload = (kind: AwaitingUpload, message: string, next: StageName): CollectionJobState => {
    return patchJobState(options.outDir, {
      jobId: options.jobId,
      pmid,
      status: "awaiting_upload",
      awaitingUpload: kind,
      nextStage: next,
      message,
    })
  }

  try {
    if (options.fulltextPath && existsSync(options.fulltextPath)) {
      log(`Ingesting user fulltext for ${pmid}`)
      ingestManualFulltext({ pmid, filePath: options.fulltextPath })
    }

    if (options.supplementaryPath && existsSync(options.supplementaryPath)) {
      if (!isTabularUpload(options.supplementaryPath)) {
        throw new Error(`Unsupported supplementary file: ${options.supplementaryPath}`)
      }
      log(`Ingesting user supplementary tables for ${pmid}`)
      ingestManualSupplementary({ pmid, filePath: options.supplementaryPath })
    }

    // ── Paper overview (before Stage 1) ─────────────────────────────────────
    if (!state.summary?.paper && shouldRunStage(resumeFrom, "stage1")) {
      const resolved = await resolveAbstractsForPmids([pmid], {
        source: "auto",
        onProgress: log,
      })
      const paper = resolved.records[0]
      if (paper) {
        state = patchJobState(options.outDir, {
          jobId: options.jobId,
          pmid,
          summary: {
            paper: {
              pmid,
              title: paper.title,
              abstract: paper.abstract,
            },
          },
          message: `Paper loaded: ${paper.title}`,
        })
      }
    }

    // ── Stage 1: PTM relevance screening ────────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage1")) {
      markStage("stage1", "running")
      log("Stage 1: PTM relevance screening")
      const s1 = await runStage1Screen({
        pmid,
        all: true,
        rescreen: true,
        concurrency: 1,
        model: options.model,
        onLog: log,
      })
      const screen = loadAllScreenResults().find((r) => r.pmid === pmid)
      const paper = (state.summary?.paper as Record<string, string>) ?? {}

      if (screen?.decision === "exclude") {
        return patchJobState(options.outDir, {
          jobId: options.jobId,
          pmid,
          status: "rejected",
          currentStage: "stage1",
          nextStage: null,
          message:
            `Screening result: this paper does not appear to contain quantitative PTM proteomics data. ` +
            `Reason: ${screen.reason}`,
          stages: { stage1: "completed" },
          summary: { stage1: s1, stage1Screen: screen, paper },
        })
      }

      if (screen?.decision === "uncertain") {
        return pauseContinue(
          "stage1",
          `Screening is uncertain for this paper (confidence ${screen.confidence}). ` +
            `Reason: ${screen.reason} ` +
            `Click Continue if you still want to proceed with data collection.`,
          { stage1: s1, stage1Screen: screen, paper },
        )
      }

      markStage("stage1", "completed")
      const ptmHint =
        screen?.ptmTypes?.length ? ` Detected PTM types: ${screen.ptmTypes.join(", ")}.` : ""
      return pauseContinue(
        "stage1",
        `This paper contains quantitative PTM proteomics data.${ptmHint} ` +
          `Click Continue to fetch the full text.`,
        { stage1: s1, stage1Screen: screen, paper },
      )
    }

    // ── Stage 2: Full text acquisition ──────────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage2")) {
      markStage("stage2", "running")
      log("Stage 2: repository ID discovery (internal)")
      const s2discover = await runStage2Discover({
        pmid,
        all: true,
        concurrency,
        resume: true,
      })

      if (!needsFulltextUpload(pmid)) {
        log("Stage 2: full text already present")
        markStage("stage2", "completed")
        state = patchJobState(options.outDir, {
          jobId: options.jobId,
          pmid,
          summary: { stage2Discover: s2discover, stage2Fulltext: { skipped: true } },
        })
        return pauseContinue(
          "stage2",
          "Full text is available (user upload or open-access fetch). " +
            "Click Continue to extract literature metadata.",
        )
      }

      log("Stage 2: open-access full text fetch")
      const s2ft = await runStage2Fulltext({
        pmid,
        all: true,
        concurrency,
        resume: true,
      })
      state = patchJobState(options.outDir, {
        jobId: options.jobId,
        pmid,
        summary: { stage2Discover: s2discover, stage2Fulltext: s2ft },
      })

      if (needsFulltextUpload(pmid)) {
        markStage("stage2", "failed")
        return awaitUpload(
          "fulltext",
          "Open-access full text could not be retrieved automatically. " +
            "Please upload a PDF or JATS XML file, then click Continue.",
          "stage2",
        )
      }

      markStage("stage2", "completed")
      return pauseContinue(
        "stage2",
        "Full text retrieved successfully. Click Continue to extract literature metadata.",
      )
    }

    // ── Stage 3: Literature metadata ────────────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage3")) {
      markStage("stage3", "running")
      log("Stage 3: literature metadata extraction")
      const s3 = await runStage3Meta({
        pmid,
        all: true,
        concurrency,
        model: options.model,
      })
      const stage3Row = loadStage3Row(pmid)
      markStage("stage3", "completed")
      return pauseContinue(
        "stage3",
        "Literature metadata extracted. Review the table below and click Continue to scout supplementary tables.",
        { stage3: s3, stage3Row },
      )
    }

    // ── Stage 4: Supplementary scout ────────────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage4")) {
      const userSuppUploaded = hasUserUploadedSupplementary(pmid)
      if (userSuppUploaded) {
        markStage("stage4", "skipped")
        return pauseContinue(
          "stage4",
          "User-uploaded supplementary tables detected. Click Continue to parse quantitative data.",
        )
      }

      markStage("stage4", "running")
      log("Stage 4: supplementary table scout")
      const s4 = await runStage4SuppScout({
        pmid,
        all: true,
        concurrency,
        resume: false,
      })
      markStage("stage4", "completed")
      const scout = loadScoutRecord(options.outDir, pmid)

      if (needsSupplementaryUpload(pmid, scout)) {
        return awaitUpload(
          "supplementary",
          "Supplementary quantitative tables could not be downloaded automatically. " +
            "Please upload a ZIP, Excel, or CSV/TSV file, then click Continue.",
          "stage5",
        )
      }

      const verdict = scout?.verdict ?? "found"
      return pauseContinue(
        "stage4",
        `Supplementary tables located (${verdict}). Click Continue to parse quantitative data.`,
        { stage4: s4, stage4Scout: scout },
      )
    }

    // ── Stage 5 + 6: Parse tables → MS download URLs (auto chain) ───────────
    if (shouldRunStage(resumeFrom, "stage5")) {
      markStage("stage5", "running")
      log("Stage 5: parse quantitative tables")
      const s5 = await runStage5Parse({
        pmid,
        all: true,
        allJobs: true,
        likelyOnly: false,
        concurrency,
        resume: true,
        model: options.model,
      })
      markStage("stage5", "completed")

      const rowCount = (s5 as { totalRows?: number }).totalRows ?? 0
      if (rowCount <= 0) {
        return patchJobState(options.outDir, {
          jobId: options.jobId,
          pmid,
          status: "completed",
          currentStage: "stage5",
          nextStage: null,
          message:
            "No quantitative PTM site-level ratios were parsed from the supplementary tables. " +
            "Please check the table format or upload a different file.",
          summary: { stage5: s5, qratioRowCount: 0 },
        })
      }

      markStage("stage6", "running")
      log("Stage 6: MS repository download URLs")
      let s6: unknown
      try {
        s6 = await runStage6DownloadUrls({
          pmid,
          all: true,
          concurrency,
          resume: true,
        })
        markStage("stage6", "completed")
      } catch (err) {
        log(`Stage 6 warning: ${err instanceof Error ? err.message : String(err)}`)
        markStage("stage6", "failed")
        s6 = { error: err instanceof Error ? err.message : String(err) }
      }

      return patchJobState(options.outDir, {
        jobId: options.jobId,
        pmid,
        status: "completed",
        awaitingUpload: null,
        nextStage: null,
        currentStage: null,
        message:
          `Collection complete. Parsed ${rowCount} qratio row(s). ` +
          `Download literature metadata and qratio tables below.`,
        summary: { stage5: s5, stage6: s6, qratioRowCount: rowCount },
      })
    }

    // Resume after supplementary upload may jump straight to stage5
    if (shouldRunStage(resumeFrom, "stage6") && !shouldRunStage(resumeFrom, "stage5")) {
      markStage("stage6", "running")
      const s6 = await runStage6DownloadUrls({
        pmid,
        all: true,
        concurrency,
        resume: true,
      })
      markStage("stage6", "completed")
      return patchJobState(options.outDir, {
        jobId: options.jobId,
        pmid,
        status: "completed",
        nextStage: null,
        currentStage: null,
        message: "MS repository download links extracted. Collection complete.",
        summary: { stage6: s6 },
      })
    }

    return patchJobState(options.outDir, {
      jobId: options.jobId,
      pmid,
      status: "completed",
      nextStage: null,
      currentStage: null,
      message: "Collection job finished.",
    })
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    log(`Job error: ${message}`)
    return patchJobState(options.outDir, {
      jobId: options.jobId,
      pmid,
      status: "error",
      error: message,
      message: `Collection failed: ${message}`,
    })
  }
}
