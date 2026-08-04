import { fetchJson } from "../http.js"
import { extractAccessions, type AccessionHit, sourceFromId } from "../accessions.js"

interface PxIdentifier {
  name?: string
  value?: string
  accession?: string
}

interface PxDataset {
  title?: string
  identifiers?: PxIdentifier[]
  publications?: Array<{ id?: string; idtype?: string }>
}

/**
 * Fetch ProteomeXchange Central JSON for a known accession (PXD/MSV/…).
 * Used to harvest cross-repository mirrors (e.g. PXD ↔ MSV).
 */
export async function fetchPxDataset(accession: string): Promise<AccessionHit[]> {
  const url =
    `https://proteomecentral.proteomexchange.org/cgi/GetDataset` +
    `?ID=${encodeURIComponent(accession)}&outputMode=JSON&test=no`
  try {
    const data = await fetchJson<PxDataset>(url)
    const hits: AccessionHit[] = []
    const seen = new Set<string>()
    const push = (id: string, via: string) => {
      const u = id.toUpperCase()
      if (seen.has(u)) return
      seen.add(u)
      hits.push({ id: u, source: sourceFromId(u), via })
    }
    push(accession, "px:self")
    for (const id of data.identifiers ?? []) {
      const v = id.value?.trim()
      if (!v) continue
      const extracted = extractAccessions(v, "px:identifiers")
      if (extracted.length) {
        for (const e of extracted) push(e.id, e.via)
      }
    }
    return hits
  } catch {
    return [{ id: accession.toUpperCase(), source: sourceFromId(accession), via: "px:lookup-failed" }]
  }
}

/** Expand a set of accessions via PX Central cross-links */
export async function expandViaProteomeXchange(ids: string[]): Promise<AccessionHit[]> {
  const all: AccessionHit[] = []
  for (const id of ids) {
    // PX Central is mainly useful for PXD / MSV style accessions
    if (!/^(PXD|MSV|PDC|PASS)/i.test(id)) continue
    const hits = await fetchPxDataset(id)
    all.push(...hits)
  }
  return all
}
