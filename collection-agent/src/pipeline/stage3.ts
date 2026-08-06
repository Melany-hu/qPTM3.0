import { existsSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { MetaChain } from "../chains/meta/agent.js"
import { createLlmRuntime, type LlmRuntime } from "../runtime.js"
import type { Stage2Manifest } from "../stage2/discover.js"
import type { FulltextRecord } from "../stage2/fulltext.js"
import { loadFulltextExcerpt } from "../stage3/text.js"
import type { LiteratureInfoRow } from "../types.js"
import {
  appendStage3Results,
  loadIncludePmidsCsv,
  loadStage3DonePmids,
  stage2FulltextDir,
  stage2FulltextManifestPath,
  stage2ManifestJsonlPath,
  stage3LiteratureInfoPath,
  stage3ManualQueuePath,
  stage3ResultsCsvPath,
  stage3ResultsJsonlPath,
} from "../utils/io.js"

export interface Stage3Options {
  limit?: number
  all?: boolean
  concurrency?: number
  flushEvery?: number
  model?: string
  /** Prefer XML-only papers (skip PDF-only abstract fallback) */
  xmlOnly?: boolean
  pmid?: string
  onResult?: (row: LiteratureInfoRow, index: number, total: number) => void
  onError?: (pmid: string, error: unknown, index: number) => void
}

export interface Stage3RunSummary {
  modelId: string
  eligible: number
  attempted: number
  saved: number
  errors: number
  ok: number
  partial: number
  skippedDone: number
}

export interface Stage3Input {
  pmid: string
  title: string
  abstract: string
  hasXml: boolean
  hasPdf: boolean
  repositories: Array<{ id: string; source: string }>
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

function loadFulltextByPmid(): Map<string, FulltextRecord> {
  const map = new Map<string, FulltextRecord>()
  const manifestPath = stage2FulltextManifestPath()
  if (existsSync(manifestPath)) {
    for (const line of readFileSync(manifestPath, "utf8").split("\n")) {
      const t = line.trim()
      if (!t) continue
      try {
        const row = JSON.parse(t) as FulltextRecord
        if (row.pmid) map.set(row.pmid, row)
      } catch {
        // skip
      }
    }
  }
  // Also scan meta.json for any success not in manifest
  // (lightweight: only when manifest missing entry we already have dirs)
  return map
}

function hasLocalFulltext(pmid: string, ft: FulltextRecord | undefined): {
  hasXml: boolean
  hasPdf: boolean
} {
  const dir = join(stage2FulltextDir(), pmid)
  const hasXml = Boolean(ft?.hasXml) || existsSync(join(dir, "fulltext.xml"))
  const hasPdf =
    Boolean(ft?.hasPdf) ||
    existsSync(join(dir, "fulltext.pdf")) ||
    existsSync(join(dir, `${pmid}.pdf`))
  return { hasXml, hasPdf }
}

export function loadStage3EligibleInputs(options: {
  xmlOnly?: boolean
  pmid?: string
} = {}): Stage3Input[] {
  const includes = loadIncludePmidsCsv()
  const byPmid = new Map(includes.map((r) => [r.pmid, r]))
  const discover = loadDiscoverByPmid()
  const fulltext = loadFulltextByPmid()

  const dirPmids = existsSync(stage2FulltextDir())
    ? readdirSync(stage2FulltextDir(), { withFileTypes: true })
        .filter((d) => d.isDirectory() && /^\d+$/.test(d.name))
        .map((d) => d.name)
    : []

  const pmids = options.pmid
    ? [options.pmid]
    : [...new Set([...fulltext.keys(), ...dirPmids, ...byPmid.keys()])]

  const out: Stage3Input[] = []
  for (const pmid of pmids) {
    const { hasXml, hasPdf } = hasLocalFulltext(pmid, fulltext.get(pmid))
    if (!hasXml && !hasPdf) continue
    if (options.xmlOnly && !hasXml) continue

    const inc = byPmid.get(pmid)
    const disc = discover.get(pmid)
    const ft = fulltext.get(pmid)
    out.push({
      pmid,
      title: inc?.title || ft?.title || disc?.title || "",
      abstract: inc?.abstract ?? "",
      hasXml,
      hasPdf,
      repositories: (disc?.repositories ?? []).map((r) => ({
        id: r.id,
        source: r.source,
      })),
    })
  }
  // Prefer XML papers first (richer extraction)
  out.sort((a, b) => Number(b.hasXml) - Number(a.hasXml) || a.pmid.localeCompare(b.pmid))
  return out
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

/**
 * Stage 3 orchestrator: eligible fulltexts → MetaChain → literature_info.csv
 * Already-extracted PMIDs in stage3_results.jsonl are skipped (resume).
 */
export async function runStage3Meta(options: Stage3Options = {}): Promise<Stage3RunSummary> {
  const concurrency = Math.max(1, options.concurrency ?? 2)
  const flushEvery = Math.max(1, options.flushEvery ?? 10)

  const runtime: LlmRuntime = await createLlmRuntime({ model: options.model })
  const chain = new MetaChain(runtime)

  const done = loadStage3DonePmids()
  const allEligible = loadStage3EligibleInputs({
    xmlOnly: options.xmlOnly,
    pmid: options.pmid,
  })
  const skippedDone = allEligible.filter((e) => done.has(e.pmid)).length
  let eligible = allEligible.filter((e) => !done.has(e.pmid))

  if (!options.all && !options.pmid) {
    const limit = options.limit ?? 20
    eligible = eligible.slice(0, limit)
  }

  const buffer: LiteratureInfoRow[] = []
  let writeLock: Promise<void> = Promise.resolve()
  let saved = 0
  let errors = 0
  let ok = 0
  let partial = 0

  const flushBuffer = () => {
    if (buffer.length === 0) return
    const chunk = buffer.splice(0, buffer.length)
    writeLock = writeLock.then(() => {
      appendStage3Results(chunk)
    })
  }

  const enqueue = (row: LiteratureInfoRow, isError: boolean) => {
    buffer.push(row)
    saved++
    if (isError) errors++
    if (row.status === "ok") ok++
    else if (row.status === "partial") partial++
    if (buffer.length >= flushEvery) flushBuffer()
  }

  await mapPool(eligible, concurrency, async (item, index) => {
    try {
      const excerpt = await loadFulltextExcerpt(item.pmid, item.abstract)
      if (!excerpt.excerpt.trim()) {
        const empty: LiteratureInfoRow = {
          pmid: item.pmid,
          title: item.title,
          sample: "",
          sampleType: "",
          organism: "",
          ptms: "",
          labelMethod: "",
          condition: "",
          detailCondition: "",
          conditionSampleMap: "",
          enrichmentMethod: "",
          massSpectrometer: "",
          msDataSource: item.repositories.map((r) => r.source).filter(Boolean)[0] ?? "",
          identifier: item.repositories.map((r) => r.id).join("; "),
          status: "error",
          confidence: 0,
          textSource: excerpt.textSource,
          notes: excerpt.notes || "no extractable text",
          extractedAt: new Date().toISOString(),
          error: "no extractable text",
        }
        options.onResult?.(empty, index, eligible.length)
        enqueue(empty, true)
        return null
      }

      const row = await chain.run({
        pmid: item.pmid,
        title: item.title,
        excerpt: excerpt.excerpt,
        textSource: excerpt.textSource,
        knownIdentifiers: item.repositories,
      })
      if (excerpt.notes) {
        row.notes = row.notes ? `${row.notes}; ${excerpt.notes}` : excerpt.notes
      }
      options.onResult?.(row, index, eligible.length)
      enqueue(row, false)
    } catch (err) {
      options.onError?.(item.pmid, err, index)
      const fallback: LiteratureInfoRow = {
        pmid: item.pmid,
        title: item.title,
        sample: "",
        sampleType: "",
        organism: "",
        ptms: "",
        labelMethod: "",
        condition: "",
        detailCondition: "",
        conditionSampleMap: "",
        enrichmentMethod: "",
        massSpectrometer: "",
        msDataSource: item.repositories.map((r) => r.source).filter(Boolean)[0] ?? "",
        identifier: item.repositories.map((r) => r.id).join("; "),
        status: "error",
        confidence: 0,
        textSource: item.hasXml ? "xml" : item.hasPdf ? "abstract" : "none",
        notes: `MetaChain error: ${err instanceof Error ? err.message : String(err)}`,
        extractedAt: new Date().toISOString(),
        error: err instanceof Error ? err.message : String(err),
      }
      enqueue(fallback, true)
    }
    return null
  })

  flushBuffer()
  await writeLock

  return {
    modelId: runtime.modelId,
    eligible: allEligible.length,
    attempted: eligible.length,
    saved,
    errors,
    ok,
    partial,
    skippedDone,
  }
}

export function stage3OutputPaths() {
  return {
    jsonl: stage3ResultsJsonlPath(),
    csv: stage3ResultsCsvPath(),
    literatureInfo: stage3LiteratureInfoPath(),
    manual: stage3ManualQueuePath(),
  }
}
