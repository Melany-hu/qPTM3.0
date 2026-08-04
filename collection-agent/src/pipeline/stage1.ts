import type { AbstractRecord, ScreenResult } from "../types.js"
import { ScreenChain } from "../chains/screen/agent.js"
import { createLlmRuntime, type LlmRuntime } from "../runtime.js"
import {
  type AbstractSource,
  loadPmidListFromFile,
  resolveAbstractsForPmids,
} from "../stage1/resolve-abstracts.js"
import {
  appendScreenResults,
  computeStats,
  exportIncludePmidsCsv,
  exportUncertainPmidsCsv,
  loadAllAbstracts,
  loadGoldPmids,
  loadScreenedPmids,
  removeScreenResultsForPmids,
  writeForceIncludeFromAbstracts,
} from "../utils/io.js"

export interface Stage1Options {
  /** Max abstracts; omit or Infinity with all=true for full pending set */
  limit?: number
  all?: boolean
  /** Only abstracts whose sourceFile contains this substring (e.g. phosphorylation) */
  sourceFile?: string
  /** Single PMID (auto-fetch abstract if not in local CSVs) */
  pmid?: string
  /** CSV / plain list of PMIDs (auto-fetch abstracts for missing) */
  pmidsFile?: string
  /** Abstract API: pubmed | pubtator3 | auto (default auto) */
  abstractSource?: AbstractSource
  /** Re-screen: drop prior decisions for requested PMIDs before running */
  rescreen?: boolean
  /** Skip LLM; force all listed PMIDs into stage1_include_pmids.csv */
  forceInclude?: boolean
  concurrency?: number
  skipGold?: boolean
  model?: string
  /** Checkpoint to disk every N finishes (default 10) */
  flushEvery?: number
  onResult?: (result: ScreenResult, index: number, total: number) => void
  onError?: (abstract: AbstractRecord, error: unknown, index: number) => void
  onLog?: (msg: string) => void
}

export interface Stage1RunSummary {
  modelId: string
  attempted: number
  saved: number
  errors: number
  include: number
  exclude: number
  uncertain: number
  pendingAfter: number
  sourceFileFilter?: string
  abstractsFromLocal?: number
  abstractsFetched?: number
  abstractsMissing?: string[]
}

function getPending(skipGold: boolean, sourceFile?: string): AbstractRecord[] {
  const screened = loadScreenedPmids()
  const gold = loadGoldPmids()
  return loadAllAbstracts().filter((a) => {
    if (screened.has(a.pmid)) return false
    if (skipGold && gold.has(a.pmid)) return false
    if (sourceFile && !a.sourceFile.includes(sourceFile)) return false
    return true
  })
}

function filterPending(
  records: AbstractRecord[],
  skipGold: boolean,
): AbstractRecord[] {
  const screened = loadScreenedPmids()
  const gold = loadGoldPmids()
  return records.filter((a) => {
    if (screened.has(a.pmid)) return false
    if (skipGold && gold.has(a.pmid)) return false
    return true
  })
}

async function mapPool<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length)
  let next = 0

  async function runner() {
    while (true) {
      const i = next++
      if (i >= items.length) return
      results[i] = await worker(items[i], i)
    }
  }

  const n = Math.max(1, Math.min(concurrency, items.length || 1))
  await Promise.all(Array.from({ length: n }, () => runner()))
  return results
}

export interface ForceIncludeSummary {
  requested: number
  written: number
  fromLocal: number
  fetched: number
  missing: string[]
  includePath: string
}

/**
 * Bypass ScreenChain: resolve abstracts for PMIDs and write them all as include
 * (for validation / Stage2–5 testing).
 */
export async function runForceInclude(options: Stage1Options = {}): Promise<ForceIncludeSummary> {
  const log = options.onLog ?? (() => {})
  const pmidList: string[] = []
  if (options.pmid) pmidList.push(options.pmid.trim())
  if (options.pmidsFile) pmidList.push(...loadPmidListFromFile(options.pmidsFile))
  if (pmidList.length === 0) {
    throw new Error("--force-include requires --pmid and/or --pmids-file")
  }

  const resolved = await resolveAbstractsForPmids(pmidList, {
    source: options.abstractSource ?? "auto",
    onProgress: log,
  })
  if (resolved.missing.length > 0) {
    log(`Warning: no abstract for ${resolved.missing.length} PMID(s): ${resolved.missing.join(", ")}`)
  }
  if (resolved.records.length === 0) {
    throw new Error("No abstracts resolved; cannot write force-include list")
  }

  const { includeN, path } = writeForceIncludeFromAbstracts(resolved.records)
  log(`force-include: wrote ${includeN} PMID(s) → ${path}`)

  return {
    requested: pmidList.length,
    written: resolved.records.length,
    fromLocal: resolved.fromLocal,
    fetched: resolved.fetched,
    missing: resolved.missing,
    includePath: path,
  }
}

/**
 * Deterministic Stage-1 orchestrator:
 * for each pending abstract → ScreenChain.run → append results (checkpointed)
 */
export async function runStage1Screen(options: Stage1Options = {}): Promise<Stage1RunSummary> {
  const concurrency = Math.max(1, options.concurrency ?? 1)
  const skipGold = options.skipGold ?? false
  const flushEvery = Math.max(1, options.flushEvery ?? 10)
  const sourceFile = options.sourceFile
  const log = options.onLog ?? (() => {})

  let abstractsFromLocal: number | undefined
  let abstractsFetched: number | undefined
  let abstractsMissing: string[] | undefined

  let pending: AbstractRecord[]
  const pmidList: string[] = []
  if (options.pmid) pmidList.push(options.pmid.trim())
  if (options.pmidsFile) pmidList.push(...loadPmidListFromFile(options.pmidsFile))

  if (options.rescreen && pmidList.length > 0) {
    const removed = removeScreenResultsForPmids(pmidList, { refreshExports: false })
    log(`--rescreen: removed ${removed} prior Stage-1 row(s) for ${pmidList.length} PMID(s)`)
  }

  if (pmidList.length > 0) {
    const resolved = await resolveAbstractsForPmids(pmidList, {
      source: options.abstractSource ?? "auto",
      onProgress: log,
    })
    abstractsFromLocal = resolved.fromLocal
    abstractsFetched = resolved.fetched
    abstractsMissing = resolved.missing
    if (resolved.missing.length > 0) {
      log(`Warning: no abstract for ${resolved.missing.length} PMID(s): ${resolved.missing.join(", ")}`)
    }
    pending = filterPending(resolved.records, skipGold)
    // Explicit PMID mode ignores --file / default pending pool; --all means all listed
    if (!options.all && !options.pmid && options.pmidsFile) {
      const limit = options.limit ?? 20
      pending = pending.slice(0, limit)
    }
  } else {
    pending = getPending(skipGold, sourceFile)
    if (!options.all) {
      const limit = options.limit ?? 20
      pending = pending.slice(0, limit)
    }
  }

  const runtime: LlmRuntime = await createLlmRuntime({ model: options.model })
  const chain = new ScreenChain(runtime)

  const buffer: ScreenResult[] = []
  let writeLock: Promise<void> = Promise.resolve()
  let saved = 0
  let errors = 0
  let include = 0
  let exclude = 0
  let uncertain = 0

  const flushBuffer = () => {
    if (buffer.length === 0) return
    const chunk = buffer.splice(0, buffer.length)
    writeLock = writeLock.then(() => {
      appendScreenResults(chunk)
    })
  }

  const enqueueResult = (result: ScreenResult, isError: boolean) => {
    buffer.push(result)
    saved++
    if (isError) errors++
    if (result.decision === "include") include++
    else if (result.decision === "exclude") exclude++
    else uncertain++
    if (buffer.length >= flushEvery) flushBuffer()
  }

  await mapPool(pending, concurrency, async (abs, index) => {
    try {
      const result = await chain.run(abs)
      options.onResult?.(result, index, pending.length)
      enqueueResult(result, false)
    } catch (err) {
      options.onError?.(abs, err, index)
      const fallback: ScreenResult = {
        pmid: abs.pmid,
        title: abs.title,
        decision: "uncertain",
        confidence: 0,
        ptmTypes: [],
        organisms: [],
        isQuantitativeMs: false,
        hasSiteLevelDataHint: false,
        quantificationMethods: [],
        dataSourceHint: "unknown",
        reason: `ScreenChain error: ${err instanceof Error ? err.message : String(err)}`,
        sourceFile: abs.sourceFile,
        screenedAt: new Date().toISOString(),
      }
      enqueueResult(fallback, true)
    }
    return null
  })

  flushBuffer()
  await writeLock

  exportIncludePmidsCsv()
  exportUncertainPmidsCsv()

  const stats = computeStats()
  return {
    modelId: runtime.modelId,
    attempted: pending.length,
    saved,
    errors,
    include,
    exclude,
    uncertain,
    pendingAfter: stats.pending,
    sourceFileFilter: sourceFile,
    abstractsFromLocal,
    abstractsFetched,
    abstractsMissing,
  }
}
