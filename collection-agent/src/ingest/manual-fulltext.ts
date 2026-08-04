/**
 * Ingest user-uploaded fulltext (PDF or JATS XML) into Stage 2 layout.
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { extname, join } from "node:path"
import type { FulltextRecord } from "../stage2/fulltext.js"
import { fulltextPmidDir } from "../stage2/fulltext.js"

export interface IngestFulltextOptions {
  pmid: string
  filePath: string
  title?: string
}

function loadExistingMeta(metaPath: string): Partial<FulltextRecord> {
  if (!existsSync(metaPath)) return {}
  try {
    return JSON.parse(readFileSync(metaPath, "utf8")) as Partial<FulltextRecord>
  } catch {
    return {}
  }
}

export function ingestManualFulltext(options: IngestFulltextOptions): FulltextRecord {
  const pmid = options.pmid.trim()
  if (!pmid) throw new Error("PMID is required")
  if (!existsSync(options.filePath)) {
    throw new Error(`File not found: ${options.filePath}`)
  }

  const dir = fulltextPmidDir(pmid)
  const metaPath = join(dir, "meta.json")
  const prior = loadExistingMeta(metaPath)
  const ext = extname(options.filePath).toLowerCase()

  let hasXml = Boolean(prior.hasXml)
  let hasPdf = Boolean(prior.hasPdf)
  let xmlPath: string | null = prior.xmlPath ?? null
  let pdfPath: string | null = prior.pdfPath ?? null

  if (ext === ".xml") {
    const dest = join(dir, "fulltext.xml")
    copyFileSync(options.filePath, dest)
    hasXml = true
    xmlPath = dest
  } else if (ext === ".pdf") {
    const dest = join(dir, "fulltext.pdf")
    copyFileSync(options.filePath, dest)
    hasPdf = true
    pdfPath = dest
  } else {
    throw new Error(`Unsupported fulltext type: ${ext} (use .pdf or .xml)`)
  }

  const sources = [...new Set([...(prior.sources ?? []), "user_upload"])]
  const status = hasXml && hasPdf ? "ok" : hasXml || hasPdf ? "partial" : "unavailable"
  const fetchedAt = new Date().toISOString()

  const record: FulltextRecord = {
    pmid,
    title: options.title ?? prior.title ?? "",
    status,
    doi: prior.doi ?? null,
    pmcid: prior.pmcid ?? null,
    hasXml,
    hasPdf,
    xmlPath: hasXml ? xmlPath : null,
    pdfPath: hasPdf ? pdfPath : null,
    sources,
    urls: prior.urls ?? [],
    notes: "User-uploaded fulltext",
    fetchedAt,
  }

  writeFileSync(metaPath, JSON.stringify(record, null, 2), "utf8")
  return record
}
