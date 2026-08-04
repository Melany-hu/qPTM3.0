import { fetchJson } from "../http.js"
import { extractAccessions, type AccessionHit } from "../accessions.js"

/**
 * MassIVE PROXI datasets endpoint — keyword search is noisy.
 * Prefer resolving known MSV accessions; also try DOI when provided.
 */
export async function lookupMassiveByAccession(msvId: string): Promise<AccessionHit[]> {
  const id = msvId.toUpperCase()
  if (!/^MSV\d+$/.test(id)) return []
  const url =
    `https://massive.ucsd.edu/ProteoSAFe/proxi/v0.1/datasets` +
    `?resultType=full&keyword=${encodeURIComponent(id)}`
  try {
    const rows = await fetchJson<unknown[]>(url)
    if (!Array.isArray(rows) || rows.length === 0) {
      return [{ id, source: "MassIVE", via: "massive:assumed" }]
    }
    const blob = JSON.stringify(rows)
    const hits = extractAccessions(blob, "massive:proxi")
    if (!hits.some((h) => h.id === id)) {
      hits.unshift({ id, source: "MassIVE", via: "massive:proxi" })
    }
    return hits
  } catch {
    return [{ id, source: "MassIVE", via: "massive:lookup-failed" }]
  }
}

export async function searchMassiveByDoi(doi: string): Promise<AccessionHit[]> {
  // PROXI keyword with DOI often returns unrelated pages; keep conservative:
  // only accept hits that also mention the DOI string in payload.
  const url =
    `https://massive.ucsd.edu/ProteoSAFe/proxi/v0.1/datasets` +
    `?resultType=full&keyword=${encodeURIComponent(doi)}`
  try {
    const rows = await fetchJson<unknown[]>(url, { timeoutMs: 25_000 })
    if (!Array.isArray(rows)) return []
    const hits: AccessionHit[] = []
    for (const row of rows.slice(0, 20)) {
      const blob = JSON.stringify(row)
      if (!blob.includes(doi) && !blob.toLowerCase().includes(doi.toLowerCase())) continue
      hits.push(...extractAccessions(blob, "massive:doi"))
    }
    return hits
  } catch {
    return []
  }
}
