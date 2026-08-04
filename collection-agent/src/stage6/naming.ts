/** Short organism tag for download URL filenames (human, mouse, rat, …). */
export function shortOrganism(organism: string): string {
  const parts = organism
    .split(/[;,]/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (parts.length === 0) return "unknown"
  const tags = [...new Set(parts.map(shortOneOrganism))]
  return tags.join("+")
}

function shortOneOrganism(organism: string): string {
  const paren = organism.match(/\(([^)]+)\)/)?.[1]?.trim().toLowerCase()
  if (paren) {
    const fromParen = mapOrganismToken(paren)
    if (fromParen) return fromParen
  }
  return mapOrganismToken(organism.toLowerCase()) ?? slugOrganism(organism)
}

function mapOrganismToken(token: string): string | undefined {
  const t = token.toLowerCase()
  if (/\bhuman\b|homo sapiens/.test(t)) return "human"
  if (/\bmouse\b|mus musculus/.test(t)) return "mouse"
  if (/\brat\b|rattus/.test(t)) return "rat"
  if (/\byeast\b|saccharomyces/.test(t)) return "yeast"
  if (/\bzebrafish\b|danio/.test(t)) return "zebrafish"
  if (/\barabidopsis\b/.test(t)) return "arabidopsis"
  return undefined
}

function slugOrganism(organism: string): string {
  const word = organism
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "")
    .slice(0, 12)
  return word || "unknown"
}

const PTM_CODES: Array<{ re: RegExp; code: string }> = [
  { re: /lactyl/i, code: "lact" },
  { re: /phosph/i, code: "phos" },
  { re: /acetyl/i, code: "ace" },
  { re: /ubiquit/i, code: "ubi" },
  { re: /succinyl/i, code: "succ" },
  { re: /crotonyl/i, code: "crot" },
  { re: /glycosyl/i, code: "gly" },
  { re: /methyl/i, code: "meth" },
  { re: /sumoyl/i, code: "sumo" },
  { re: /nitrosyl/i, code: "nitro" },
  { re: /palmitoyl/i, code: "palm" },
  { re: /hydroxybutyryl/i, code: "bhb" },
  { re: /malonyl/i, code: "mal" },
  { re: /glutaryl/i, code: "glut" },
  { re: /propionyl/i, code: "prop" },
  { re: /formyl/i, code: "form" },
  { re: /citrull/i, code: "cit" },
  { re: /proteome|^pro$/i, code: "pro" },
]

/** Short PTM tag(s) for download URL filenames (phos, ace, lact, …). */
export function shortModification(ptms: string): string {
  const parts = ptms
    .split(/[;,]/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (parts.length === 0) return "unknown"
  const tags = [...new Set(parts.map(shortOneModification))]
  return tags.join("+")
}

function shortOneModification(ptm: string): string {
  for (const { re, code } of PTM_CODES) {
    if (re.test(ptm)) return code
  }
  const word = ptm.toLowerCase().replace(/[^a-z]/g, "")
  return word.slice(0, 4) || "unk"
}

/** `{pmid}#{accession}#{organism}#{modification}.txt` */
export function stage6UrlsBasename(
  pmid: string,
  accession: string,
  organism: string,
  modification: string,
): string {
  return `${pmid}#${accession}#${organism}#${modification}.txt`
}
