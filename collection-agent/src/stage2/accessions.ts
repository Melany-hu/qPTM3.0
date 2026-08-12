/** Proteome repository accession patterns */

export type RepoSource =
  | "PRIDE"
  | "iProX"
  | "jPOST"
  | "MassIVE"
  | "PDC"
  | "ProteomeXchange"
  | "unknown"

export interface AccessionHit {
  id: string
  source: RepoSource
  via: string
}

const PATTERNS: Array<{ re: RegExp; source: RepoSource }> = [
  { re: /\bPXD\d{5,}\b/gi, source: "PRIDE" },
  { re: /\bIPX\d{6,}\b/gi, source: "iProX" },
  { re: /\bJPST\d{5,}\b/gi, source: "jPOST" },
  { re: /\bMSV\d{9}\b/gi, source: "MassIVE" },
  { re: /\bPDC\d{6}\b/gi, source: "PDC" },
]

export function extractAccessions(text: string, via: string): AccessionHit[] {
  if (!text) return []
  const seen = new Set<string>()
  const out: AccessionHit[] = []
  for (const { re, source } of PATTERNS) {
    re.lastIndex = 0
    for (const m of text.matchAll(re)) {
      const id = m[0].toUpperCase()
      if (seen.has(id)) continue
      seen.add(id)
      out.push({ id, source, via })
    }
  }
  return out
}

export function mergeAccessions(...lists: AccessionHit[][]): AccessionHit[] {
  const byId = new Map<string, AccessionHit>()
  for (const list of lists) {
    for (const hit of list) {
      const prev = byId.get(hit.id)
      if (!prev) byId.set(hit.id, hit)
      else if (!prev.via.includes(hit.via)) {
        byId.set(hit.id, { ...prev, via: `${prev.via};${hit.via}` })
      }
    }
  }
  return [...byId.values()]
}

export function sourceFromId(id: string): RepoSource {
  const u = id.toUpperCase()
  if (u.startsWith("PXD")) return "PRIDE"
  if (u.startsWith("IPX")) return "iProX"
  if (u.startsWith("JPST")) return "jPOST"
  if (u.startsWith("MSV")) return "MassIVE"
  if (u.startsWith("PDC")) return "PDC"
  return "unknown"
}

/**
 * Pick identifiers to feed Stage-3 meta extraction.
 *
 * MassIVE PROXI keyword lookup historically dumped ~100 unrelated MSV ids into
 * Stage-2 manifests. Prefer accessions that actually appear in the paper
 * excerpt; if the Stage-2 list looks like that pollution and the text has no
 * IDs, drop the MassIVE bulk rather than poisoning Identifier.
 */
export function selectKnownIdentifiersForMeta(
  repos: Array<{ id: string; source: string; via?: string }>,
  excerpt: string,
): AccessionHit[] {
  const normalized = (repos || [])
    .map((r) => ({
      id: (r.id || "").toUpperCase().trim(),
      source: (r.source as RepoSource) || sourceFromId(r.id || ""),
      via: r.via || "stage2",
    }))
    .filter((r) => r.id)

  const inExcerpt = extractAccessions(excerpt || "", "excerpt")
  if (inExcerpt.length > 0) {
    const repoById = new Map(normalized.map((r) => [r.id, r]))
    const overlap = inExcerpt
      .map((h) => repoById.get(h.id))
      .filter((h): h is AccessionHit => Boolean(h))
    // Prefer Stage-2 metadata for IDs confirmed in text; else trust text regex
    return overlap.length > 0 ? mergeAccessions(overlap) : inExcerpt
  }

  const massive = normalized.filter((r) => r.source === "MassIVE")
  const other = normalized.filter((r) => r.source !== "MassIVE")
  // Heuristic: PROXI keyword dumps are large and almost entirely MassIVE
  if (massive.length > 5 && massive.length >= normalized.length - 1) {
    return other
  }
  return mergeAccessions(normalized)
}
