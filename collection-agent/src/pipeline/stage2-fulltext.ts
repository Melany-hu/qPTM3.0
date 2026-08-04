import {
  appendFileSync,
  existsSync,
  readFileSync,
  writeFileSync,
} from "node:fs"
import { join } from "node:path"
import type { Stage2Manifest } from "../stage2/discover.js"
import {
  fetchFulltextForPmid,
  type FulltextRecord,
} from "../stage2/fulltext.js"
import { loadDotEnv } from "../runtime.js"
import {
  loadIncludePmidsCsv,
  stage2FulltextDir,
  stage2FulltextManualQueuePath,
  stage2FulltextManifestPath,
  stage2FulltextResultsCsvPath,
  stage2ManifestJsonlPath,
} from "../utils/io.js"

function csvEscape(v: string): string {
  if (/[",\n\r]/.test(v)) return `"${v.replace(/"/g, '""')}"`
  return v
}

function loadDiscoverByPmid(): Map<string, Stage2Manifest> {
  const path = stage2ManifestJsonlPath()
  const map = new Map<string, Stage2Manifest>()
  if (!existsSync(path)) return map
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim()
    if (!t) continue
    try {
      const row = JSON.parse(t) as Stage2Manifest
      if (row.pmid) map.set(row.pmid, row)
    } catch {
      // skip
    }
  }
  return map
}

function loadMeta(pmid: string): FulltextRecord | null {
  const metaPath = join(stage2FulltextDir(), pmid, "meta.json")
  if (!existsSync(metaPath)) return null
  try {
    return JSON.parse(readFileSync(metaPath, "utf8")) as FulltextRecord
  } catch {
    return null
  }
}

/** Success = has xml or pdf; keep these when resuming / retrying. */
function isSuccess(meta: FulltextRecord): boolean {
  return Boolean(meta.hasXml || meta.hasPdf)
}

function needsRetry(meta: FulltextRecord): boolean {
  return meta.status === "unavailable" || meta.status === "error" || !isSuccess(meta)
}

function loadPriorManifest(): FulltextRecord[] {
  const path = stage2FulltextManifestPath()
  if (!existsSync(path)) return []
  const out: FulltextRecord[] = []
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim()
    if (!t) continue
    try {
      out.push(JSON.parse(t) as FulltextRecord)
    } catch {
      // skip
    }
  }
  return out
}

export function writeFulltextOutputs(records: FulltextRecord[]): void {
  writeFileSync(
    stage2FulltextManifestPath(),
    records.map((r) => JSON.stringify(r)).join("\n") + "\n",
    "utf8",
  )

  const header = [
    "PMID",
    "Title",
    "status",
    "doi",
    "pmcid",
    "hasXml",
    "hasPdf",
    "sources",
    "notes",
    "error",
    "fetchedAt",
  ]
  const lines = [header.join(",")]
  for (const r of records) {
    lines.push(
      [
        csvEscape(r.pmid),
        csvEscape(r.title),
        csvEscape(r.status),
        csvEscape(r.doi ?? ""),
        csvEscape(r.pmcid ?? ""),
        String(r.hasXml),
        String(r.hasPdf),
        csvEscape(r.sources.join(";")),
        csvEscape(r.notes),
        csvEscape(r.error ?? ""),
        csvEscape(r.fetchedAt),
      ].join(","),
    )
  }
  writeFileSync(stage2FulltextResultsCsvPath(), lines.join("\n") + "\n", "utf8")

  const manual = records.filter(
    (r) => r.status === "unavailable" || r.status === "error" || (!r.hasXml && !r.hasPdf),
  )
  const mHeader = ["PMID", "Title", "doi", "pmcid", "status", "notes", "error"]
  const mLines = [mHeader.join(",")]
  for (const r of manual) {
    mLines.push(
      [
        csvEscape(r.pmid),
        csvEscape(r.title),
        csvEscape(r.doi ?? ""),
        csvEscape(r.pmcid ?? ""),
        csvEscape(r.status),
        csvEscape(r.notes),
        csvEscape(r.error ?? ""),
      ].join(","),
    )
  }
  writeFileSync(stage2FulltextManualQueuePath(), mLines.join("\n") + "\n", "utf8")
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

export interface Stage2FulltextOptions {
  limit?: number
  all?: boolean
  concurrency?: number
  resume?: boolean
  /** Re-fetch PMIDs previously marked unavailable/error (keeps ok/partial with files) */
  retryUnavailable?: boolean
  pmid?: string
  onResult?: (r: FulltextRecord, index: number, total: number) => void
}

export interface Stage2FulltextSummary {
  attempted: number
  ok: number
  partial: number
  unavailable: number
  errors: number
  withXml: number
  withPdf: number
}

export async function runStage2Fulltext(
  options: Stage2FulltextOptions = {},
): Promise<Stage2FulltextSummary> {
  loadDotEnv()
  const concurrency = Math.max(1, options.concurrency ?? 2)
  const retryUnavailable = options.retryUnavailable ?? false
  const resume = options.resume || retryUnavailable
  const discover = loadDiscoverByPmid()
  let inputs = loadIncludePmidsCsv()

  if (options.pmid) {
    inputs = inputs.filter((r) => r.pmid === options.pmid)
  } else if (!options.all) {
    inputs = inputs.slice(0, options.limit ?? 30)
  }

  const prior = resume ? loadPriorManifest() : []
  const priorByPmid = new Map(prior.map((r) => [r.pmid, r]))

  if (!resume) {
    writeFileSync(stage2FulltextManifestPath(), "", "utf8")
  }

  const pending = resume
    ? inputs.filter((r) => {
        const meta = loadMeta(r.pmid) ?? priorByPmid.get(r.pmid) ?? null
        if (!meta) return true
        if (isSuccess(meta)) return false
        if (retryUnavailable && needsRetry(meta)) return true
        // plain --resume: skip anything already attempted
        return false
      })
    : inputs

  if (retryUnavailable) {
    console.error(`Retry unavailable: ${pending.length} PMID(s) to re-fetch`)
  }

  const fresh = await mapPool(pending, concurrency, async (row, index) => {
    const disc = discover.get(row.pmid)
    const record = await fetchFulltextForPmid({
      pmid: row.pmid,
      title: row.title || disc?.title,
      doi: disc?.doi ?? null,
      pmcid: disc?.pmcid ?? null,
      isOpenAccess: disc?.isOpenAccess,
    })
    appendFileSync(stage2FulltextManifestPath(), JSON.stringify(record) + "\n", "utf8")
    options.onResult?.(record, index, pending.length)
    return record
  })

  const byPmid = new Map<string, FulltextRecord>()
  for (const r of prior) {
    // Drop prior unavailable/error when retrying so fresh results win
    if (retryUnavailable && needsRetry(r) && !isSuccess(r)) continue
    byPmid.set(r.pmid, r)
  }
  for (const r of fresh) byPmid.set(r.pmid, r)
  // Also pick up any resume skips that have meta on disk but weren't in prior jsonl
  for (const row of inputs) {
    if (byPmid.has(row.pmid)) continue
    const meta = loadMeta(row.pmid)
    if (!meta) continue
    if (retryUnavailable && needsRetry(meta) && !isSuccess(meta)) continue
    byPmid.set(row.pmid, meta)
  }

  const records = inputs
    .map((r) => byPmid.get(r.pmid))
    .filter((r): r is FulltextRecord => Boolean(r))

  writeFulltextOutputs(records)

  return {
    attempted: records.length,
    ok: records.filter((r) => r.status === "ok").length,
    partial: records.filter((r) => r.status === "partial").length,
    unavailable: records.filter((r) => r.status === "unavailable").length,
    errors: records.filter((r) => r.status === "error").length,
    withXml: records.filter((r) => r.hasXml).length,
    withPdf: records.filter((r) => r.hasPdf).length,
  }
}
