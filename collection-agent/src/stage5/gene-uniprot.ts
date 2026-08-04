/**
 * Gene symbol → UniProt accession (for Stage5 sheets without UniProt column).
 * Uses UniProt REST search + on-disk cache under stage5/cache/.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { stage5Dir } from "../utils/io.js"

const TAX_HINTS: Array<{ re: RegExp; taxId: number; name: string }> = [
  { re: /mus\s*musculus|\bmouse\b/i, taxId: 10090, name: "mouse" },
  { re: /homo\s*sapiens|\bhuman\b/i, taxId: 9606, name: "human" },
  { re: /rattus\s*norvegicus|\brat\b/i, taxId: 10116, name: "rat" },
  { re: /saccharomyces\s*cerevisiae|\byeast\b/i, taxId: 559292, name: "yeast" },
  { re: /arabidopsis\s*thaliana/i, taxId: 3702, name: "arabidopsis" },
  { re: /danio\s*rerio|\bzebrafish\b/i, taxId: 7955, name: "zebrafish" },
  { re: /gallus\s*gallus|\bchicken\b/i, taxId: 9031, name: "chicken" },
  { re: /bos\s*taurus|\bcow\b|\bbovine\b/i, taxId: 9913, name: "bovine" },
  { re: /sus\s*scrofa|\bpig\b/i, taxId: 9823, name: "pig" },
]

export function organismToTaxId(organism: string): number | null {
  const s = (organism || "").trim()
  if (!s) return null
  for (const h of TAX_HINTS) {
    if (h.re.test(s)) return h.taxId
  }
  return null
}

export function normalizeGeneSymbol(raw: string): string {
  return raw
    .split(/[;,\s|/]+/)
    .map((x) => x.trim())
    .filter(Boolean)[0]
    ?.replace(/^gene[:=\s]+/i, "")
    .trim() ?? ""
}

function cachePath(taxId: number): string {
  const dir = join(stage5Dir(), "cache")
  mkdirSync(dir, { recursive: true })
  return join(dir, `gene_uniprot_${taxId}.json`)
}

function loadCache(taxId: number): Record<string, string | null> {
  const p = cachePath(taxId)
  if (!existsSync(p)) return {}
  try {
    return JSON.parse(readFileSync(p, "utf8")) as Record<string, string | null>
  } catch {
    return {}
  }
}

function saveCache(taxId: number, cache: Record<string, string | null>): void {
  writeFileSync(cachePath(taxId), JSON.stringify(cache, null, 0), "utf8")
}

async function fetchUniprotForGene(gene: string, taxId: number): Promise<string | null> {
  const tryQueries = [
    `(gene_exact:${gene}) AND (organism_id:${taxId}) AND (reviewed:true)`,
    `(gene_exact:${gene}) AND (organism_id:${taxId})`,
    `(gene:${gene}) AND (organism_id:${taxId}) AND (reviewed:true)`,
    `(gene:${gene}) AND (organism_id:${taxId})`,
  ]
  for (const q of tryQueries) {
    const url =
      `https://rest.uniprot.org/uniprotkb/search?query=${encodeURIComponent(q)}` +
      `&fields=accession,gene_names&format=json&size=5`
    const ctrl = new AbortController()
    const t = setTimeout(() => ctrl.abort(), 20_000)
    try {
      const res = await fetch(url, {
        signal: ctrl.signal,
        headers: { Accept: "application/json" },
      })
      if (!res.ok) continue
      const data = (await res.json()) as {
        results?: Array<{ primaryAccession?: string; genes?: Array<{ geneName?: { value?: string } }> }>
      }
      const results = data.results ?? []
      if (results.length === 0) continue
      const gLower = gene.toLowerCase()
      const exact = results.find((r) =>
        (r.genes ?? []).some((x) => (x.geneName?.value || "").toLowerCase() === gLower),
      )
      const hit = exact ?? results[0]
      const acc = hit.primaryAccession?.trim()
      if (acc) return acc.toUpperCase()
    } catch {
      // try next query
    } finally {
      clearTimeout(t)
    }
  }
  return null
}

/**
 * Map unique gene symbols → UniProt accessions for a given organism string.
 * Unmapped genes are omitted from the returned Map.
 */
export async function mapGenesToUniprot(
  genes: string[],
  organism: string,
  opts: { concurrency?: number; onProgress?: (done: number, total: number) => void } = {},
): Promise<Map<string, string>> {
  const taxId = organismToTaxId(organism)
  const out = new Map<string, string>()
  if (taxId == null) return out
  const tax = taxId

  const uniq = [
    ...new Set(
      genes
        .map(normalizeGeneSymbol)
        .filter((g) => g.length >= 1 && !/^(na|n\/a|null|-)$/i.test(g)),
    ),
  ].slice(0, 300)
  if (uniq.length === 0) return out

  const cache = loadCache(tax)
  const missing: string[] = []
  for (const g of uniq) {
    const key = g.toLowerCase()
    if (key in cache) {
      const v = cache[key]
      if (v) {
        out.set(g, v)
        out.set(key, v)
      }
    } else {
      missing.push(g)
    }
  }

  const concurrency = Math.max(1, Math.min(opts.concurrency ?? 4, 8))
  let done = uniq.length - missing.length
  opts.onProgress?.(done, uniq.length)

  let i = 0
  async function worker() {
    while (true) {
      const idx = i++
      if (idx >= missing.length) return
      const g = missing[idx]
      const acc = await fetchUniprotForGene(g, tax)
      cache[g.toLowerCase()] = acc
      if (acc) {
        out.set(g, acc)
        out.set(g.toLowerCase(), acc)
      }
      done++
      opts.onProgress?.(done, uniq.length)
      // gentle rate limit
      await new Promise((r) => setTimeout(r, 80))
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, missing.length || 1) }, () => worker()))
  saveCache(tax, cache)
  return out
}
