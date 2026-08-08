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
  setDataRoot,
  stage2FulltextDir,
  stage3LiteratureInfoPath,
  stage4SuppDir,
  stage5Dir,
  stage6Dir,
} from "../utils/io.js"
import {
  nextStageAfter,
  patchJobState,
  shouldRunStage,
  type AwaitingUpload,
  type CollectionJobState,
  type StageName,
} from "./job-state.js"
import {
  messageFulltextMissing,
  messageFulltextOk,
  messageInclude,
  messageMsUrlsComplete,
  messageParseEmpty,
  messageParseOk,
  messageRejected,
  messageSuppMissing,
  messageSuppOk,
  messageUncertain,
  messageUserSuppReady,
  UI_SEG,
} from "./user-messages.js"

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

/** Artifact availability for the interactive UI (download chips). */
function artifactSummary(pmid: string): Record<string, unknown> {
  const ftDir = join(stage2FulltextDir(), pmid)
  const hasPdf = existsSync(join(ftDir, "fulltext.pdf"))
  const hasXml = existsSync(join(ftDir, "fulltext.xml"))
  const hasZip = existsSync(join(stage4SuppDir(), pmid, "supplementary.zip"))
  const hasQratio = existsSync(join(stage5Dir(), "qratio.csv"))
  const hasMsUrls = existsSync(join(stage6Dir(), "urls_all.csv"))
  const fulltextUserUpload = (() => {
    const metaPath = join(ftDir, "meta.json")
    if (!existsSync(metaPath)) return false
    try {
      const meta = JSON.parse(readFileSync(metaPath, "utf8")) as {
        sources?: string[]
        notes?: string
      }
      if (Array.isArray(meta.sources) && meta.sources.includes("user_upload")) return true
      const notes = String(meta.notes || "").toLowerCase()
      return notes.includes("user-uploaded") || notes.includes("user_upload")
    } catch {
      return false
    }
  })()
  const supplementaryUserUpload = existsSync(
    join(stage4SuppDir(), pmid, "source_user_upload.txt"),
  )
  return {
    artifacts: {
      fulltextKind: hasPdf ? "pdf" : hasXml ? "xml" : null,
      hasSupplementary: hasZip,
      hasQratio,
      hasMsUrls,
      fulltextUserUpload,
      supplementaryUserUpload,
    },
  }
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
    // Keep the UI focused on the stage being resumed (avoid flashing prior stage).
    ...(resumeFrom !== "auto"
      ? { currentStage: resumeFrom as StageName }
      : {}),
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
    nextOverride?: StageName | null,
  ): CollectionJobState => {
    const next = nextOverride !== undefined ? nextOverride : nextStageAfter(completedStage)
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

  const awaitUpload = (
    kind: AwaitingUpload,
    message: string,
    next: StageName,
    summaryPatch: Record<string, unknown> = {},
  ): CollectionJobState => {
    return patchJobState(options.outDir, {
      jobId: options.jobId,
      pmid,
      status: "awaiting_upload",
      awaitingUpload: kind,
      nextStage: next,
      message,
      summary: summaryPatch,
    })
  }

  try {
    if (options.fulltextPath && existsSync(options.fulltextPath)) {
      log(`Ingesting user fulltext for ${pmid}`)
      await ingestManualFulltext({ pmid, filePath: options.fulltextPath })
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

      const thinking1: { step: string; message: string }[] = []
      const emit1 = (step: string, message: string) => {
        thinking1.push({ step, message })
        patchJobState(options.outDir, {
          jobId: options.jobId, pmid,
          status: "running", currentStage: "stage1",
          message: "Scanning abstract for PTM relevance…",
          summary: { stage1Thinking: [...thinking1] },
        })
      }
      emit1("start", "Starting PTM relevance screening")
      emit1("classify", "Classifying abstract with LLM...")

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

      emit1("result", `Decision: ${screen?.decision || "unknown"}, confidence: ${screen?.confidence ?? "N/A"}`)
      emit1("done", `PTM types: ${(screen?.ptmTypes || []).join(", ") || "none"}`)

      if (screen?.decision === "exclude") {
        return patchJobState(options.outDir, {
          jobId: options.jobId,
          pmid,
          status: "rejected",
          currentStage: "stage1",
          nextStage: null,
          offerContribute: false,
          message: messageRejected({
            title: (paper.title as string) || screen.title,
            reason: screen.reason,
            ptmTypes: screen.ptmTypes,
          }),
          stages: { stage1: "completed" },
          summary: { stage1: s1, stage1Screen: screen, paper, stage1Thinking: thinking1 },
        })
      }

      if (screen?.decision === "uncertain") {
        return pauseContinue(
          "stage1",
          messageUncertain({
            title: (paper.title as string) || screen.title,
            abstract: paper.abstract as string | undefined,
            reason: screen.reason,
            confidence: screen.confidence,
          }),
          { stage1: s1, stage1Screen: screen, paper, stage1Thinking: thinking1, ...artifactSummary(pmid) },
        )
      }

      markStage("stage1", "completed")
      const hasFulltext = !needsFulltextUpload(pmid)
      // PDF/XML already present (user upload or prior fetch): skip Stage 2 UI → Stage 3 next.
      if (hasFulltext) {
        log("Stage 1: full text already present — skip Stage 2 pause, next is Stage 3")
        let s2discover: unknown = { skipped: true }
        try {
          s2discover = await runStage2Discover({
            pmid,
            all: true,
            concurrency,
            resume: true,
          })
        } catch (err) {
          log(`Stage 2 discover (silent): ${err instanceof Error ? err.message : String(err)}`)
        }
        markStage("stage2", "skipped")
        return pauseContinue(
          "stage1",
          messageInclude({
            title: (paper.title as string) || screen?.title,
            abstract: paper.abstract as string | undefined,
            ptmTypes: screen?.ptmTypes,
            hasFulltext: true,
          }),
          {
            stage1: s1,
            stage1Screen: screen,
            paper,
            stage2Discover: s2discover,
            stage2Fulltext: { skipped: true },
            stage1Thinking: thinking1,
            ...artifactSummary(pmid),
          },
          "stage3",
        )
      }
      return pauseContinue(
        "stage1",
        messageInclude({
          title: (paper.title as string) || screen?.title,
          abstract: paper.abstract as string | undefined,
          ptmTypes: screen?.ptmTypes,
          hasFulltext: false,
        }),
        { stage1: s1, stage1Screen: screen, paper, stage1Thinking: thinking1, ...artifactSummary(pmid) },
      )
    }

    // ── Stage 2: Full text acquisition ──────────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage2")) {
      markStage("stage2", "running")
      log("Stage 2: repository ID discovery (internal)")

      const thinking2: { step: string; message: string }[] = []
      const emit2 = (step: string, message: string) => {
        thinking2.push({ step, message })
        patchJobState(options.outDir, {
          jobId: options.jobId, pmid,
          status: "running", currentStage: "stage2",
          message: "Acquiring full text…",
          summary: { stage2Thinking: [...thinking2] },
        })
      }
      emit2("discover", "Discovering repository identifiers...")

      const s2discover = await runStage2Discover({
        pmid,
        all: true,
        concurrency,
        resume: true,
      })

      if (!needsFulltextUpload(pmid)) {
        // Full text already on disk — do not pause for Continue; fall through to Stage 3.
        log("Stage 2: full text already present — continue to Stage 3")
        emit2("skip", "Full text already present")
        markStage("stage2", "skipped")
        state = patchJobState(options.outDir, {
          jobId: options.jobId,
          pmid,
          summary: {
            stage2Discover: s2discover,
            stage2Fulltext: { skipped: true },
            stage2Thinking: thinking2,
            ...artifactSummary(pmid),
          },
        })
      } else {
        log("Stage 2: open-access full text fetch")
        emit2("fetch", "Fetching full text from open-access sources...")
        const s2ft = await runStage2Fulltext({
          pmid,
          all: true,
          concurrency,
          resume: true,
        })
        emit2("result", needsFulltextUpload(pmid) ? "Full text not available — awaiting user upload" : "Full text acquired")
        state = patchJobState(options.outDir, {
          jobId: options.jobId,
          pmid,
          summary: { stage2Discover: s2discover, stage2Fulltext: s2ft, stage2Thinking: thinking2, ...artifactSummary(pmid) },
        })

        if (needsFulltextUpload(pmid)) {
          markStage("stage2", "failed")
          return awaitUpload("fulltext", messageFulltextMissing(), "stage2", { stage2Thinking: thinking2, ...artifactSummary(pmid) })
        }

        markStage("stage2", "completed")
        return pauseContinue("stage2", messageFulltextOk("oa"), { stage2Thinking: thinking2, ...artifactSummary(pmid) })
      }
    }

    // ── Stage 3: Literature metadata ────────────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage3")) {
      markStage("stage3", "running")
      log("Stage 3: literature metadata extraction")

      const thinking3: { step: string; message: string }[] = []
      const emit3 = (step: string, message: string) => {
        thinking3.push({ step, message })
        patchJobState(options.outDir, {
          jobId: options.jobId, pmid,
          status: "running", currentStage: "stage3",
          message: "Extracting experimental metadata…",
          summary: { stage3Thinking: [...thinking3] },
        })
      }
      emit3("start", "Starting metadata extraction")
      emit3("extract", "Extracting experimental metadata from full text with LLM...")

      const s3 = await runStage3Meta({
        pmid,
        all: true,
        concurrency,
        model: options.model,
        onProgress: (step, message) => emit3(step, message),
      })
      const stage3Row = loadStage3Row(pmid)

      emit3("result", `Metadata extracted: ${stage3Row?.Sample || "unknown sample"}, ${stage3Row?.Organism || "unknown organism"}, PTM: ${stage3Row?.PTMs || "unknown"}`)
      markStage("stage3", "completed")
      return pauseContinue(
        "stage3",
        [
          "Literature metadata extracted. Review the table below.",
          UI_SEG.AFTER_META,
          "Click Continue to scout supplementary quantitative tables.",
        ].join("\n"),
        { stage3: s3, stage3Row, stage3Thinking: thinking3, ...artifactSummary(pmid) },
      )
    }

    // ── Stage 4: Supplementary scout ────────────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage4")) {
      const userSuppUploaded = hasUserUploadedSupplementary(pmid)
      if (userSuppUploaded) {
        markStage("stage4", "skipped")
        const scout = loadScoutRecord(options.outDir, pmid)
        return pauseContinue(
          "stage4",
          messageUserSuppReady(),
          { stage4Scout: scout, stage4Source: "user_upload", stage4Thinking: [{ step: "skip", message: "User already uploaded supplementary files" }], ...artifactSummary(pmid) },
        )
      }

      markStage("stage4", "running")
      log("Stage 4: supplementary table scout")

      const thinking4: { step: string; message: string }[] = []
      const emit4 = (step: string, message: string) => {
        thinking4.push({ step, message })
        patchJobState(options.outDir, {
          jobId: options.jobId, pmid,
          status: "running", currentStage: "stage4",
          message: "Scouting supplementary tables…",
          summary: { stage4Thinking: [...thinking4] },
        })
      }
      emit4("start", "Starting supplementary material scout")
      emit4("scan", "Scanning publisher supplementary materials for quantitative tables...")

      const s4 = await runStage4SuppScout({
        pmid,
        all: true,
        concurrency,
        resume: false,
      })
      markStage("stage4", "completed")
      const scout = loadScoutRecord(options.outDir, pmid)

      const topFiles = scout?.topFiles || ""
      emit4("result", topFiles ? `Found candidate files: ${topFiles}` : "No quantitative supplementary tables found")

      if (needsSupplementaryUpload(pmid, scout)) {
        return awaitUpload(
          "supplementary",
          messageSuppMissing(),
          "stage5",
          { stage4: s4, stage4Scout: scout, stage4Thinking: thinking4, ...artifactSummary(pmid) },
        )
      }

      return pauseContinue(
        "stage4",
        messageSuppOk(),
        { stage4: s4, stage4Scout: scout, stage4Thinking: thinking4, ...artifactSummary(pmid) },
      )
    }

    // ── Stage 5: Parse quantitative tables ──────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage5")) {
      markStage("stage5", "running")
      log("Stage 5: parse quantitative tables")
      const thinking: unknown[] = []
      patchJobState(options.outDir, {
        jobId: options.jobId,
        pmid,
        status: "running",
        currentStage: "stage5",
        message: "Parsing quantitative tables…",
        summary: { stage5Thinking: [] },
      })
      const s5 = await runStage5Parse({
        pmid,
        all: true,
        allJobs: true,
        likelyOnly: false,
        concurrency,
        resume: true,
        model: options.model,
        onThinking: (step) => {
          thinking.push(step)
          const trimmed = thinking.slice(-60)
          patchJobState(options.outDir, {
            jobId: options.jobId,
            pmid,
            status: "running",
            currentStage: "stage5",
            // Keep a stable user-facing status; detailed steps live in stage5Thinking (plan panel).
            message: "Parsing quantitative tables…",
            summary: { stage5Thinking: trimmed },
          })
        },
      })
      markStage("stage5", "completed")

      const rowCount = (s5 as { totalRows?: number }).totalRows ?? 0
      const proteinFilled = Number((s5 as { totalProteomeRows?: number }).totalProteomeRows || 0) || undefined

      // Extract sheet usage info from the thinking log.
      // Prefer the parsed steps' entryPath entries (they keep the real filename,
      // e.g. "srep42053-s5.xls") over regex-parsing the summary line, whose lazy
      // match stops at the first "." and would drop the ".xls" extension.
      const parsedFiles = new Set<string>()
      for (const s of thinking as unknown as Array<{
        step?: string
        entryPath?: string
      }>) {
        if (s?.step === "parsed" && s?.entryPath) parsedFiles.add(s.entryPath)
      }
      let sheetsUsed = ""
      if (parsedFiles.size > 0) {
        sheetsUsed = [...parsedFiles].join("; ")
      } else {
        const summaryStep = thinking.find((s: any) => s?.step === "summary" && s?.message?.includes("extracted")) as { message?: string } | undefined
        const sheetsSummary = summaryStep?.message || ""
        const siteMatch = sheetsSummary.match(/from (\d+) sheet\(s\): (.+?)\. Tried/)
        sheetsUsed = siteMatch ? siteMatch[2] : ""
      }

      if (rowCount <= 0) {
        return patchJobState(options.outDir, {
          jobId: options.jobId,
          pmid,
          status: "awaiting_upload",
          currentStage: "stage5",
          nextStage: "stage5",
          awaitingUpload: "supplementary",
          offerContribute: false,
          message: messageParseEmpty(),
          summary: {
            stage5: s5,
            qratioRowCount: 0,
            stage5Thinking: thinking.slice(-60),
            needsTableHints: true,
            ...artifactSummary(pmid),
          },
        })
      }

      return patchJobState(options.outDir, {
        jobId: options.jobId,
        pmid,
        status: "awaiting_continue",
        currentStage: "stage5",
        nextStage: "stage6",
        awaitingUpload: null,
        offerContribute: true,
        contribution: { willing: null },
        message: messageParseOk(rowCount, {
          proteinFilled,
          sheetsUsed,
        }),
        summary: {
          stage5: s5,
          qratioRowCount: rowCount,
          stage5Thinking: thinking.slice(-60),
          offerContribute: true,
          allowTableHints: true,
          needsTableHints: false,
          stage3Row: loadStage3Row(pmid),
          ...artifactSummary(pmid),
        },
      })
    }

    // ── Stage 6: MS repository download URLs ────────────────────────────────
    if (shouldRunStage(resumeFrom, "stage6")) {
      markStage("stage6", "running")
      log("Stage 6: MS repository download URLs")

      const thinking6: { step: string; message: string }[] = []
      const emit6 = (step: string, message: string) => {
        thinking6.push({ step, message })
        patchJobState(options.outDir, {
          jobId: options.jobId, pmid,
          status: "running", currentStage: "stage6",
          message: "Resolving MS repository download URLs…",
          summary: { stage6Thinking: [...thinking6] },
        })
      }
      emit6("start", "Starting MS repository URL resolution")
      emit6("resolve", "Querying PRIDE, iProX, jPOST, and CPTAC (PDC) for download links...")

      let s6: { totalUrls?: number; error?: string; [k: string]: unknown }
      try {
        s6 = (await runStage6DownloadUrls({
          pmid,
          all: true,
          concurrency,
          resume: true,
        })) as { totalUrls?: number }
        emit6("result", `Found ${s6.totalUrls ?? 0} download URL(s)`)
        markStage("stage6", "completed")
      } catch (err) {
        log(`Stage 6 warning: ${err instanceof Error ? err.message : String(err)}`)
        emit6("error", `Resolution failed: ${err instanceof Error ? err.message : String(err)}`)
        markStage("stage6", "failed")
        s6 = { error: err instanceof Error ? err.message : String(err), totalUrls: 0 }
      }

      const priorRows = Number((state.summary?.qratioRowCount as number) || 0)
      const rowCount = priorRows > 0 ? priorRows : 0
      const priorContribution = state.contribution
      const alreadyChose =
        priorContribution?.willing === true || priorContribution?.willing === false
      const stage3Row = loadStage3Row(pmid)
      const identifier = stage3Row?.Identifier || stage3Row?.identifier || ""
      return patchJobState(options.outDir, {
        jobId: options.jobId,
        pmid,
        status: "completed",
        awaitingUpload: null,
        nextStage: null,
        currentStage: "stage6",
        // Keep Stage5 contribution choice; only offer again if user never answered.
        offerContribute: alreadyChose ? false : rowCount > 0,
        ...(alreadyChose
          ? {}
          : { contribution: { willing: null } }),
        message: messageMsUrlsComplete({
          rowCount,
          totalUrls: s6.totalUrls,
          statusNote: s6.error ? `Note: ${s6.error}` : undefined,
          offerContribute: !alreadyChose && rowCount > 0,
        }),
        summary: {
          stage6: { ...s6, identifier },
          stage6Thinking: thinking6,
          qratioRowCount: rowCount,
          offerContribute: alreadyChose ? false : rowCount > 0,
          ...artifactSummary(pmid),
        },
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
