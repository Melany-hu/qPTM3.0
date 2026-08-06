/**
 * Stage 4 — Supplementary scout for ALL Stage 3 papers.
 * Finds OA supplementary tabular clues for quantitative PTM tables
 * (works with or without MS repository Identifier / PXD/IPX/MSV).
 */
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import {
  fetchEuropePmcMeta,
  fetchEuropePmcSupplementaryZip,
} from "../stage2/clients/europepmc.js"
import {
  fetchDoiSupplementaryFiles,
  packSupplementaryZip,
} from "../stage4/clients/doi-supp.js"
import {
  decideVerdict,
  listAndScoreZip,
  scanLocalXmlSupp,
  type SuppVerdict,
  type ZipFileHit,
} from "../stage4/supp-scout.js"
import { writeBuffer } from "../stage4/zip.js"
import type { LiteratureInfoRow } from "../types.js"
import {
  csvEscape,
  loadStage3Results,
  stage2FulltextDir,
  stage4Dir,
  stage4ManualQueuePath,
  stage4SuppDir,
  stage4SuppJobsPath,
  stage4SuppScoutCsvPath,
  stage4SuppScoutJsonlPath,
  toPortablePath,
} from "../utils/io.js"

export type SuppZipStatus = "ok" | "empty" | "not_found" | "error" | "skipped" | "none"

export interface SuppScoutRecord {
  pmid: string
  title: string
  /** MS repository accession(s) from Stage 3 — may be empty */
  identifier: string
  doi: string | null
  pmcid: string | null
  verdict: SuppVerdict
  zipStatus: SuppZipStatus
  zipPath: string | null
  topFiles: string
  clues: string
  xmlHitCount: number
  zipHitCount: number
  notes: string
  scoutedAt: string
  error?: string
}

export interface Stage4SuppOptions {
  limit?: number
  all?: boolean
  concurrency?: number
  flushEvery?: number
  resume?: boolean
  pmid?: string
  /** If true, only papers whose Stage3 Identifier is empty */
  missingIdentifierOnly?: boolean
  onResult?: (row: SuppScoutRecord, index: number, total: number) => void
  onError?: (pmid: string, error: unknown, index: number) => void
}

export interface Stage4SuppSummary {
  eligible: number
  attempted: number
  saved: number
  skippedDone: number
  byVerdict: Record<string, number>
}

function loadFulltextMeta(pmid: string): {
  doi: string | null
  pmcid: string | null
  title: string
} {
  const metaPath = join(stage2FulltextDir(), pmid, "meta.json")
  if (!existsSync(metaPath)) return { doi: null, pmcid: null, title: "" }
  try {
    const m = JSON.parse(readFileSync(metaPath, "utf8")) as {
      doi?: string | null
      pmcid?: string | null
      title?: string
    }
    return {
      doi: m.doi ?? null,
      pmcid: m.pmcid ?? null,
      title: m.title ?? "",
    }
  } catch {
    return { doi: null, pmcid: null, title: "" }
  }
}

/**
 * When Stage2 meta lacks DOI/PMCID (common after user-uploaded PDF),
 * resolve them from Europe PMC by PMID and persist back into meta.json.
 */
async function resolveMissingIds(
  pmid: string,
  meta: { doi: string | null; pmcid: string | null; title: string },
): Promise<{ doi: string | null; pmcid: string | null; title: string; resolved: boolean }> {
  if (meta.doi && meta.pmcid && meta.title) {
    return { ...meta, resolved: false }
  }
  try {
    const epmc = await fetchEuropePmcMeta(pmid)
    const doi = meta.doi || epmc.doi
    const pmcid = meta.pmcid || epmc.pmcid
    const title = meta.title || epmc.title || ""
    const resolved = Boolean(
      (doi && doi !== meta.doi) || (pmcid && pmcid !== meta.pmcid) || (title && !meta.title),
    )
    if (resolved) {
      const metaPath = join(stage2FulltextDir(), pmid, "meta.json")
      if (existsSync(metaPath)) {
        try {
          const raw = JSON.parse(readFileSync(metaPath, "utf8")) as Record<string, unknown>
          if (!raw.doi && doi) raw.doi = doi
          if (!raw.pmcid && pmcid) raw.pmcid = pmcid
          if (!(raw.title as string)?.trim() && title) raw.title = title
          writeFileSync(metaPath, JSON.stringify(raw, null, 2) + "\n", "utf8")
        } catch {
          // non-fatal — scout can still use in-memory ids
        }
      }
    }
    return { doi, pmcid, title, resolved }
  } catch (err) {
    console.error(
      `  Europe PMC ID lookup failed for PMID ${pmid}:`,
      err instanceof Error ? err.message : String(err),
    )
    return { ...meta, resolved: false }
  }
}

function loadDonePmids(): Set<string> {
  const path = stage4SuppScoutJsonlPath()
  const done = new Set<string>()
  if (!existsSync(path)) return done
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim()
    if (!t) continue
    try {
      const row = JSON.parse(t) as SuppScoutRecord
      if (row.pmid) done.add(row.pmid)
    } catch {
      // skip
    }
  }
  return done
}

function loadAllScoutRecords(): SuppScoutRecord[] {
  const path = stage4SuppScoutJsonlPath()
  if (!existsSync(path)) return []
  const out: SuppScoutRecord[] = []
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim()
    if (!t) continue
    try {
      out.push(JSON.parse(t) as SuppScoutRecord)
    } catch {
      // skip
    }
  }
  return out
}

export function rebuildStage4Outputs(): void {
  stage4Dir()
  const results = loadAllScoutRecords()

  const header = [
    "PMID",
    "Title",
    "Identifier",
    "doi",
    "pmcid",
    "verdict",
    "zipStatus",
    "topFiles",
    "clues",
    "xmlHitCount",
    "zipHitCount",
    "notes",
    "scoutedAt",
    "error",
  ]
  const lines = [header.join(",")]
  for (const r of results) {
    lines.push(
      [
        csvEscape(r.pmid),
        csvEscape(r.title),
        csvEscape(r.identifier),
        csvEscape(r.doi ?? ""),
        csvEscape(r.pmcid ?? ""),
        csvEscape(r.verdict),
        csvEscape(r.zipStatus),
        csvEscape(r.topFiles),
        csvEscape(r.clues),
        String(r.xmlHitCount),
        String(r.zipHitCount),
        csvEscape(r.notes),
        csvEscape(r.scoutedAt),
        csvEscape(r.error ?? ""),
      ].join(","),
    )
  }
  writeFileSync(stage4SuppScoutCsvPath(), lines.join("\n") + "\n", "utf8")

  const jobs = results.filter(
    (r) => r.verdict === "likely_qptm_table" || r.verdict === "has_tabular_supp",
  )
  writeFileSync(
    stage4SuppJobsPath(),
    jobs.map((r) => JSON.stringify(r)).join("\n") + (jobs.length ? "\n" : ""),
    "utf8",
  )

  const manual = results.filter(
    (r) =>
      r.verdict === "unavailable" ||
      (r.zipStatus === "error" && r.verdict !== "likely_qptm_table" && r.verdict !== "has_tabular_supp"),
  )
  const mHeader = ["PMID", "Title", "Identifier", "pmcid", "verdict", "zipStatus", "notes", "error"]
  const mLines = [mHeader.join(",")]
  for (const r of manual) {
    mLines.push(
      [
        csvEscape(r.pmid),
        csvEscape(r.title),
        csvEscape(r.identifier),
        csvEscape(r.pmcid ?? ""),
        csvEscape(r.verdict),
        csvEscape(r.zipStatus),
        csvEscape(r.notes),
        csvEscape(r.error ?? ""),
      ].join(","),
    )
  }
  writeFileSync(stage4ManualQueuePath(), mLines.join("\n") + "\n", "utf8")
}

function appendScoutResults(rows: SuppScoutRecord[]): void {
  if (rows.length === 0) return
  writeFileSync(
    stage4SuppScoutJsonlPath(),
    // append-safe: read existing is handled by caller merging; we append
    rows.map((r) => JSON.stringify(r)).join("\n") + "\n",
    {
      encoding: "utf8",
      flag: "a",
    },
  )
  rebuildStage4Outputs()
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

export function loadStage4Inputs(options: {
  pmid?: string
  missingIdentifierOnly?: boolean
} = {}): LiteratureInfoRow[] {
  let rows = loadStage3Results()
  if (options.pmid) rows = rows.filter((r) => r.pmid === options.pmid)
  if (options.missingIdentifierOnly) {
    rows = rows.filter((r) => !(r.identifier ?? "").trim())
  }
  // Prefer papers without Identifier first, then rest
  rows.sort((a, b) => {
    const ae = (a.identifier ?? "").trim() ? 1 : 0
    const be = (b.identifier ?? "").trim() ? 1 : 0
    if (ae !== be) return ae - be
    return a.pmid.localeCompare(b.pmid)
  })
  return rows
}

async function scoutOne(row: LiteratureInfoRow): Promise<SuppScoutRecord> {
  const meta0 = loadFulltextMeta(row.pmid)
  const resolved = await resolveMissingIds(row.pmid, meta0)
  const title = row.title || resolved.title
  const pmcid = resolved.pmcid
  const doi = resolved.doi
  const scoutedAt = new Date().toISOString()
  const xml = scanLocalXmlSupp(row.pmid)

  let zipStatus: SuppZipStatus = "none"
  let zipPath: string | null = null
  let zipHits: ZipFileHit[] = []
  let error: string | undefined
  let viaDoi = false
  const noteBits: string[] = []
  if (resolved.resolved) {
    noteBits.push(
      `ids_from_europepmc${pmcid ? `:${pmcid}` : ""}${doi ? `:${doi}` : ""}`,
    )
  }

  const pmidDir = join(stage4SuppDir(), row.pmid)
  const localZip = join(pmidDir, "supplementary.zip")
  const listingPath = join(pmidDir, "listing.json")

  if (existsSync(localZip) && existsSync(listingPath)) {
    zipStatus = "skipped"
    zipPath = localZip
    try {
      zipHits = JSON.parse(readFileSync(listingPath, "utf8")) as ZipFileHit[]
    } catch {
      zipHits = listAndScoreZip(localZip)
    }
    // Heuristic: prior DOI packs write a marker
    viaDoi = existsSync(join(pmidDir, "source_doi.txt"))
  } else {
    // 1) Europe PMC OA ZIP when PMCID present (looked up by PMID if meta lacked it)
    if (pmcid) {
      const fetched = await fetchEuropePmcSupplementaryZip(pmcid)
      zipStatus = fetched.status === "ok" ? "ok" : fetched.status
      if (fetched.status === "ok" && fetched.buffer) {
        mkdirSync(pmidDir, { recursive: true })
        writeBuffer(localZip, fetched.buffer)
        zipPath = localZip
        zipHits = listAndScoreZip(localZip)
        writeFileSync(listingPath, JSON.stringify(zipHits, null, 2), "utf8")
        noteBits.push("source=europepmc")
      } else if (fetched.error) {
        error = fetched.error
        noteBits.push(`epmc=${fetched.status}`)
      } else {
        noteBits.push(`epmc=${fetched.status}`)
      }
    }

    // 2) DOI publisher fallback (works for many non-OA Nature/Springer pages)
    const needDoi =
      Boolean(doi) &&
      zipHits.length === 0 &&
      zipStatus !== "ok"
    if (needDoi && doi) {
      console.error(`  DOI supplementary fallback for ${row.pmid} (${doi})…`)
      const doiFetch = await fetchDoiSupplementaryFiles(doi)
      noteBits.push(`doi=${doiFetch.status}`)
      if (doiFetch.notes) noteBits.push(doiFetch.notes)
      if (doiFetch.status === "ok" && doiFetch.files.length > 0) {
        mkdirSync(pmidDir, { recursive: true })
        // Keep raw files for debugging
        const filesDir = join(pmidDir, "files")
        mkdirSync(filesDir, { recursive: true })
        for (const f of doiFetch.files) {
          writeBuffer(join(filesDir, f.filename), f.buffer)
        }
        packSupplementaryZip(localZip, doiFetch.files)
        zipPath = localZip
        zipStatus = "ok"
        zipHits = listAndScoreZip(localZip)
        writeFileSync(listingPath, JSON.stringify(zipHits, null, 2), "utf8")
        writeFileSync(join(pmidDir, "source_doi.txt"), doi, "utf8")
        viaDoi = true
        error = undefined
        noteBits.push(`doiFiles=${doiFetch.files.length}`)
      } else if (doiFetch.error) {
        error = error ? `${error}; ${doiFetch.error}` : doiFetch.error
      }
    } else if (!pmcid && !doi) {
      zipStatus = zipStatus === "ok" ? zipStatus : "none"
      noteBits.push("no_pmcid_or_doi_after_lookup")
    }
  }

  const { verdict, notes } = decideVerdict({
    hasPmcid: Boolean(pmcid),
    zipStatus,
    xml,
    zipHits,
    viaDoi,
  })

  const topFiles = zipHits
    .slice(0, 8)
    .map((h) => `${h.path}[${h.kind} score=${h.score}]`)
    .join(" | ")
  const clues = [
    ...xml.textClues,
    ...xml.hits.flatMap((h) => h.clues.map((c) => `xml:${c}`)),
    ...zipHits.slice(0, 8).flatMap((h) => h.clues.map((c) => `zip:${c}`)),
  ]
    .slice(0, 30)
    .join(";")

  return {
    pmid: row.pmid,
    title,
    identifier: row.identifier ?? "",
    doi,
    pmcid,
    verdict,
    zipStatus,
    zipPath: zipPath ? toPortablePath(zipPath) : null,
    topFiles,
    clues,
    xmlHitCount: xml.hits.length,
    zipHitCount: zipHits.length,
    notes: [...noteBits, notes].filter(Boolean).join(" | "),
    scoutedAt,
    error,
  }
}

export async function runStage4SuppScout(
  options: Stage4SuppOptions = {},
): Promise<Stage4SuppSummary> {
  const concurrency = Math.max(1, options.concurrency ?? 2)
  const flushEvery = Math.max(1, options.flushEvery ?? 10)
  const resume = options.resume !== false && !options.pmid // --pmid always re-scouts
  const done = resume ? loadDonePmids() : new Set<string>()
  const allEligible = loadStage4Inputs({
    pmid: options.pmid,
    missingIdentifierOnly: options.missingIdentifierOnly,
  })
  const skippedDone = options.pmid ? 0 : allEligible.filter((e) => done.has(e.pmid)).length
  let pending = options.pmid
    ? allEligible
    : allEligible.filter((e) => !done.has(e.pmid))

  // When re-scouting a single PMID, drop prior scout row and local cache so DOI fallback can run
  // — but keep user-uploaded supplementary tables.
  if (options.pmid) {
    const pmidDir = join(stage4SuppDir(), options.pmid)
    const userUploadMarker = join(pmidDir, "source_user_upload.txt")
    if (!existsSync(userUploadMarker)) {
      if (existsSync(stage4SuppScoutJsonlPath())) {
        const kept = loadAllScoutRecords().filter((r) => r.pmid !== options.pmid)
        writeFileSync(
          stage4SuppScoutJsonlPath(),
          kept.map((r) => JSON.stringify(r)).join("\n") + (kept.length ? "\n" : ""),
          "utf8",
        )
      }
      for (const name of ["supplementary.zip", "listing.json", "source_doi.txt"]) {
        const p = join(pmidDir, name)
        try {
          if (existsSync(p)) unlinkSync(p)
        } catch {
          // ignore
        }
      }
    }
  }

  if (!options.all && !options.pmid) {
    pending = pending.slice(0, options.limit ?? 20)
  }
  const buffer: SuppScoutRecord[] = []
  let writeLock: Promise<void> = Promise.resolve()
  let saved = 0
  const byVerdict: Record<string, number> = {}

  const flush = () => {
    if (buffer.length === 0) return
    const chunk = buffer.splice(0, buffer.length)
    writeLock = writeLock.then(() => {
      appendScoutResults(chunk)
    })
  }

  await mapPool(pending, concurrency, async (item, index) => {
    try {
      const row = await scoutOne(item)
      options.onResult?.(row, index, pending.length)
      buffer.push(row)
      saved++
      byVerdict[row.verdict] = (byVerdict[row.verdict] ?? 0) + 1
      if (buffer.length >= flushEvery) flush()
    } catch (err) {
      options.onError?.(item.pmid, err, index)
      const fallback: SuppScoutRecord = {
        pmid: item.pmid,
        title: item.title,
        identifier: item.identifier ?? "",
        doi: null,
        pmcid: null,
        verdict: "unavailable",
        zipStatus: "error",
        zipPath: null,
        topFiles: "",
        clues: "",
        xmlHitCount: 0,
        zipHitCount: 0,
        notes: `scout error: ${err instanceof Error ? err.message : String(err)}`,
        scoutedAt: new Date().toISOString(),
        error: err instanceof Error ? err.message : String(err),
      }
      buffer.push(fallback)
      saved++
      byVerdict.unavailable = (byVerdict.unavailable ?? 0) + 1
      if (buffer.length >= flushEvery) flush()
    }
    return null
  })

  flush()
  await writeLock

  return {
    eligible: allEligible.length,
    attempted: pending.length,
    saved,
    skippedDone,
    byVerdict,
  }
}

export function stage4OutputPaths() {
  return {
    jsonl: stage4SuppScoutJsonlPath(),
    csv: stage4SuppScoutCsvPath(),
    jobs: stage4SuppJobsPath(),
    manual: stage4ManualQueuePath(),
    suppDir: stage4SuppDir(),
  }
}
