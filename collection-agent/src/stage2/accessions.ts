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
