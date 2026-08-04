/**
 * PubTator3 publication export — title/abstract by PMID (BioC JSON).
 * Docs: https://www.ncbi.nlm.nih.gov/research/pubtator3/api
 */
import { fetchJson } from "../../stage2/http.js"
import type { PubmedAbstract } from "./pubmed.js"

interface BiocPassage {
  infons?: { type?: string }
  text?: string
}

interface BiocDoc {
  id?: string | number
  pmid?: string | number
  passages?: BiocPassage[]
}

interface PubTatorExport {
  PubTator3?: BiocDoc[]
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

function docPmid(doc: BiocDoc): string {
  if (doc.pmid != null && String(doc.pmid).trim()) return String(doc.pmid).trim()
  if (doc.id != null && String(doc.id).trim()) return String(doc.id).trim()
  return ""
}

function passageText(doc: BiocDoc, type: string): string {
  const parts: string[] = []
  for (const p of doc.passages ?? []) {
    const t = String(p.infons?.type ?? "").toLowerCase()
    if (t === type && p.text?.trim()) parts.push(p.text.trim())
  }
  return parts.join(" ").trim()
}

export function parsePubTatorBiocJson(data: PubTatorExport): PubmedAbstract[] {
  const out: PubmedAbstract[] = []
  for (const doc of data.PubTator3 ?? []) {
    const pmid = docPmid(doc)
    if (!pmid) continue
    out.push({
      pmid,
      title: passageText(doc, "title"),
      abstract: passageText(doc, "abstract"),
    })
  }
  return out
}

/**
 * Batch-fetch title/abstract via PubTator3 biocjson export.
 * Keep batches modest; API accepts comma-separated pmids.
 */
export async function fetchPubTator3Abstracts(
  pmids: string[],
  opts: { batchSize?: number; pauseMs?: number } = {},
): Promise<Map<string, PubmedAbstract>> {
  const unique = [...new Set(pmids.map((p) => p.trim()).filter(Boolean))]
  const out = new Map<string, PubmedAbstract>()
  if (unique.length === 0) return out

  const batchSize = Math.max(1, Math.min(opts.batchSize ?? 50, 100))
  const pauseMs = opts.pauseMs ?? 200

  for (let i = 0; i < unique.length; i += batchSize) {
    if (i > 0) await sleep(pauseMs)
    const batch = unique.slice(i, i + batchSize)
    const url =
      `https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson` +
      `?pmids=${encodeURIComponent(batch.join(","))}`
    const data = await fetchJson<PubTatorExport>(url, { timeoutMs: 60_000 })
    for (const rec of parsePubTatorBiocJson(data)) {
      out.set(rec.pmid, rec)
    }
  }
  return out
}
