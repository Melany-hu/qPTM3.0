import { fetchJson } from "../http.js"

export interface UnpaywallHit {
  doi: string
  isOa: boolean
  pdfUrl: string | null
  source: string | null
  license: string | null
}

interface UnpaywallResponse {
  doi?: string
  is_oa?: boolean
  best_oa_location?: {
    url_for_pdf?: string | null
    url?: string | null
    host_type?: string | null
    license?: string | null
  } | null
  oa_locations?: Array<{
    url_for_pdf?: string | null
    url?: string | null
    host_type?: string | null
    license?: string | null
  }>
}

function pickPdfUrl(data: UnpaywallResponse): {
  pdfUrl: string | null
  source: string | null
  license: string | null
} {
  const locs = [
    data.best_oa_location,
    ...(data.oa_locations ?? []),
  ].filter(Boolean) as NonNullable<UnpaywallResponse["best_oa_location"]>[]

  for (const loc of locs) {
    if (loc?.url_for_pdf) {
      return {
        pdfUrl: loc.url_for_pdf,
        source: loc.host_type ?? null,
        license: loc.license ?? null,
      }
    }
  }
  return { pdfUrl: null, source: null, license: null }
}

/** Unpaywall requires a contact email in the query string. */
export async function lookupUnpaywall(
  doi: string,
  email: string,
): Promise<UnpaywallHit> {
  const cleaned = doi.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")
  const url =
    `https://api.unpaywall.org/v2/${encodeURIComponent(cleaned)}` +
    `?email=${encodeURIComponent(email)}`
  const data = await fetchJson<UnpaywallResponse>(url, { timeoutMs: 25_000 })
  const picked = pickPdfUrl(data)
  return {
    doi: data.doi ?? cleaned,
    isOa: Boolean(data.is_oa),
    pdfUrl: picked.pdfUrl,
    source: picked.source,
    license: picked.license,
  }
}
