/**
 * Resolve PMIDs → AbstractRecord for Stage 1.
 * Prefer local abstracts CSV cache; fetch missing via PubMed / PubTator3.
 */
import { mkdirSync, existsSync, writeFileSync, readFileSync } from "node:fs"
import { join } from "node:path"
import type { AbstractRecord } from "../types.js"
import {
  abstractsDir,
  csvEscape,
  loadAllAbstracts,
  parseCsv,
} from "../utils/io.js"
import { fetchPubmedAbstracts } from "./clients/pubmed.js"
import { fetchPubTator3Abstracts } from "./clients/pubtator3.js"

export type AbstractSource = "pubmed" | "pubtator3" | "auto"

export interface ResolveAbstractsOptions {
  /** pubmed | pubtator3 | auto (pubmed then pubtator3 for misses) */
  source?: AbstractSource
  /** Persist newly fetched rows into data/abstracts/api_fetched.csv */
  cache?: boolean
  onProgress?: (msg: string) => void
}

export interface ResolveAbstractsResult {
  records: AbstractRecord[]
  fromLocal: number
  fetched: number
  missing: string[]
  sourceUsed: AbstractSource
}

const FETCHED_SOURCE_FILE = "api_fetched.csv"

export function fetchedAbstractsPath(): string {
  return join(abstractsDir(), FETCHED_SOURCE_FILE)
}

/** Load PMID list from CSV (PMID column) or plain newline-separated file. */
export function loadPmidListFromFile(path: string): string[] {
  if (!existsSync(path)) throw new Error(`PMID list not found: ${path}`)
  const text = readFileSync(path, "utf8").replace(/^\uFEFF/, "")
  const trimmedLines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  if (trimmedLines.length === 0) return []

  // Plain newline list (optional header "PMID")
  const looksPlain =
    trimmedLines.every((l) => !l.includes(",") || /^pmid$/i.test(l)) ||
    trimmedLines.every((l) => /^\d+$/.test(l.replace(/,/g, "").trim()) || /^pmid$/i.test(l))
  if (looksPlain) {
    return [
      ...new Set(
        trimmedLines
          .map((l) => l.replace(/,/g, "").trim())
          .filter((p) => /^\d+$/.test(p)),
      ),
    ]
  }

  const rows = parseCsv(text)
  if (rows.length === 0) return []
  const header = rows[0].map((h) => h.trim().replace(/^\uFEFF/, ""))
  let pmidIdx = header.findIndex((h) => /^pmid$/i.test(h))
  const hasHeader = pmidIdx >= 0
  if (!hasHeader) pmidIdx = 0
  const start = hasHeader ? 1 : 0

  const out: string[] = []
  for (let i = start; i < rows.length; i++) {
    const pmid = (rows[i][pmidIdx] ?? "").trim()
    if (/^\d+$/.test(pmid)) out.push(pmid)
  }
  return [...new Set(out)]
}

function upsertFetchedCsv(records: AbstractRecord[]): void {
  if (records.length === 0) return
  const dir = abstractsDir()
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  const path = fetchedAbstractsPath()

  const byPmid = new Map<string, AbstractRecord>()
  if (existsSync(path)) {
    const rows = parseCsv(readFileSync(path, "utf8"))
    if (rows.length > 0) {
      const header = rows[0].map((h) => h.trim().replace(/^\uFEFF/, ""))
      const pi = header.findIndex((h) => /^pmid$/i.test(h))
      const ti = header.findIndex((h) => /^title$/i.test(h))
      const ai = header.findIndex((h) => /^abstract$/i.test(h))
      if (pi >= 0 && ti >= 0 && ai >= 0) {
        for (let i = 1; i < rows.length; i++) {
          const pmid = (rows[i][pi] ?? "").trim()
          if (!pmid) continue
          byPmid.set(pmid, {
            pmid,
            title: (rows[i][ti] ?? "").trim(),
            abstract: (rows[i][ai] ?? "").trim(),
            sourceFile: FETCHED_SOURCE_FILE,
          })
        }
      }
    }
  }

  for (const r of records) byPmid.set(r.pmid, { ...r, sourceFile: FETCHED_SOURCE_FILE })

  const lines = ["PMID,Title,Abstract"]
  for (const r of byPmid.values()) {
    lines.push([csvEscape(r.pmid), csvEscape(r.title), csvEscape(r.abstract)].join(","))
  }
  writeFileSync(path, lines.join("\n") + "\n", "utf8")
}

async function fetchBatch(
  source: "pubmed" | "pubtator3",
  pmids: string[],
): Promise<Map<string, { pmid: string; title: string; abstract: string }>> {
  return source === "pubmed" ? fetchPubmedAbstracts(pmids) : fetchPubTator3Abstracts(pmids)
}

function takeHits(
  pmids: string[],
  map: Map<string, { pmid: string; title: string; abstract: string }>,
): { hits: AbstractRecord[]; miss: string[] } {
  const hits: AbstractRecord[] = []
  const miss: string[] = []
  for (const pmid of pmids) {
    const rec = map.get(pmid)
    if (rec && (rec.title || rec.abstract)) {
      hits.push({
        pmid,
        title: rec.title,
        abstract: rec.abstract,
        sourceFile: FETCHED_SOURCE_FILE,
      })
    } else {
      miss.push(pmid)
    }
  }
  return { hits, miss }
}

/**
 * Resolve abstracts for an explicit PMID list.
 * Local `data/abstracts/*.csv` wins; missing ones are fetched and optionally cached.
 */
export async function resolveAbstractsForPmids(
  pmids: string[],
  options: ResolveAbstractsOptions = {},
): Promise<ResolveAbstractsResult> {
  const source: AbstractSource = options.source ?? "auto"
  const cache = options.cache !== false
  const log = options.onProgress ?? (() => {})

  const wanted = [...new Set(pmids.map((p) => p.trim()).filter(Boolean))]
  const local = new Map(loadAllAbstracts().map((a) => [a.pmid, a]))

  const records: AbstractRecord[] = []
  const needFetch: string[] = []
  for (const pmid of wanted) {
    const hit = local.get(pmid)
    if (hit && (hit.title || hit.abstract)) {
      records.push(hit)
    } else {
      needFetch.push(pmid)
    }
  }

  let fetched = 0
  let stillMissing: string[] = []

  if (needFetch.length > 0) {
    const primary: "pubmed" | "pubtator3" = source === "pubtator3" ? "pubtator3" : "pubmed"
    log(`Fetching ${needFetch.length} abstract(s) via ${primary}…`)
    const newly: AbstractRecord[] = []

    const primaryMap = await fetchBatch(primary, needFetch)
    const first = takeHits(needFetch, primaryMap)
    newly.push(...first.hits)

    if (first.miss.length > 0 && source === "auto") {
      const secondary = primary === "pubmed" ? "pubtator3" : "pubmed"
      log(`${primary} miss ${first.miss.length}; trying ${secondary}…`)
      const secondMap = await fetchBatch(secondary, first.miss)
      const second = takeHits(first.miss, secondMap)
      newly.push(...second.hits)
      stillMissing = second.miss
    } else {
      stillMissing = first.miss
    }

    fetched = newly.length
    if (cache && newly.length > 0) {
      upsertFetchedCsv(newly)
      log(`Cached ${newly.length} abstract(s) → ${fetchedAbstractsPath()}`)
    }
    records.push(...newly)
  }

  const byPmid = new Map(records.map((r) => [r.pmid, r]))
  const ordered = wanted.map((p) => byPmid.get(p)).filter((r): r is AbstractRecord => !!r)

  return {
    records: ordered,
    fromLocal: wanted.length - needFetch.length,
    fetched,
    missing: stillMissing,
    sourceUsed: source,
  }
}
