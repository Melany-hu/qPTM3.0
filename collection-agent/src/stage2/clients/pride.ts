import { fetchJson } from "../http.js"
import type { AccessionHit } from "../accessions.js"

interface PrideProject {
  accession?: string
  title?: string
}

/** PRIDE search by DOI (pubmed keyword search is unreliable). */
export async function searchPrideByDoi(doi: string): Promise<AccessionHit[]> {
  const url =
    `https://www.ebi.ac.uk/pride/ws/archive/v2/search/projects` +
    `?keyword=${encodeURIComponent(doi)}&pageSize=20`
  try {
    const rows = await fetchJson<PrideProject[]>(url)
    if (!Array.isArray(rows)) return []
    return rows
      .map((r) => r.accession)
      .filter((a): a is string => Boolean(a && /^PXD\d+/i.test(a)))
      .map((id) => ({ id: id.toUpperCase(), source: "PRIDE" as const, via: "pride:doi" }))
  } catch {
    return []
  }
}

export async function searchPrideByKeyword(keyword: string, via: string): Promise<AccessionHit[]> {
  const url =
    `https://www.ebi.ac.uk/pride/ws/archive/v2/search/projects` +
    `?keyword=${encodeURIComponent(keyword)}&pageSize=10`
  try {
    const rows = await fetchJson<PrideProject[]>(url)
    if (!Array.isArray(rows)) return []
    return rows
      .map((r) => r.accession)
      .filter((a): a is string => Boolean(a && /^PXD\d+/i.test(a)))
      .map((id) => ({ id: id.toUpperCase(), source: "PRIDE" as const, via }))
  } catch {
    return []
  }
}
