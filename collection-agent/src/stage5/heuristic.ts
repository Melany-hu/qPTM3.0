/**
 * Stage 5 — heuristic column mapping for qratio fields.
 */
import {
  cleanMappedCondition,
  conditionLabelFromRatioHeader,
  isSilacChannelRatioHeader,
  resolveRowCondition,
  silacBiologySuffixFromHeader,
} from "./condition.js"
import type { SheetInventory } from "./tables.js"

export type RatioLevel = "peptide" | "protein"
export type ValueType = "log2_ratio" | "fold_change" | "intensity" | "other"

export interface MappedRatioColumn {
  column: string
  condition: string
  /** If false, values are treated as fold-change and converted with log2 */
  isLog2: boolean
  level: RatioLevel
  valueType?: ValueType
}

export interface MappedPValueColumn {
  column: string
  condition: string
  level: RatioLevel
}

export interface ColumnMapping {
  entryPath: string
  sheetName: string
  headerRowIndex: number
  confidence: number
  source: "heuristic" | "llm"
  uniprotCol: string | null
  /** Gene symbol / gene name — used when UniProt column is absent */
  geneCol: string | null
  positionCol: string | null
  aminoAcidCol: string | null
  /** Combined site like S123 / T45 / Y89 */
  siteCombinedCol: string | null
  /** MaxQuant probability / modified sequence — AA inferred when aminoAcidCol missing */
  modSeqCol: string | null
  ratioColumns: MappedRatioColumn[]
  pValueColumns: MappedPValueColumn[]
  /** Sheet appears to be intensity/abundance only (no true ratio) */
  intensityOnly?: boolean
  intensityColumns?: string[]
  notes: string
}

function norm(h: string): string {
  return h.toLowerCase().replace(/\s+/g, " ").trim()
}

function findBest(
  headers: string[],
  scorers: Array<(h: string) => number>,
  minScore = 4,
): string | null {
  let best: string | null = null
  let bestScore = 0
  for (const h of headers) {
    const n = norm(h)
    let s = 0
    for (const fn of scorers) s = Math.max(s, fn(n))
    if (s > bestScore) {
      bestScore = s
      best = h
    }
  }
  return bestScore >= minScore ? best : null
}

function scoreUniprot(n: string): number {
  if (/phosphosite|protein\s*\+\s*phospho|gene\s*name\s*\+\s*phospho/i.test(n)) return 0
  if (/^uniprotkb$/i.test(n)) return 11
  if (/^uniprot(\s*id)?$/.test(n) || n === "uniprotid") return 10
  if (/uniprot/.test(n) && !/name|gene/.test(n)) return 9
  if (/ipi\s*accession|accession\s*number/.test(n)) return 9
  if (/^accession$/.test(n) || /protein\s*accession/.test(n)) return 8
  if (/^protein\s*ids?$/.test(n) || /^proteinid$/.test(n)) return 6
  // MaxQuant-style "Proteins" / "protein" column holding accessions
  if (/^proteins?$/.test(n)) return 8
  if (/^protein\s*group\s*ids?$/.test(n)) return 5
  if (/accession/.test(n)) return 5
  return 0
}

function scorePosition(n: string): number {
  if (/phospho_?location/.test(n)) return 10
  if (/site\s*positions?/.test(n)) return 10
  if (/positions?\s+within\s+proteins?/.test(n)) return 10
  if (/^sites?$/.test(n)) return 9
  if (/^positions?$/.test(n) || /^pos$/.test(n)) return 9
  if (/residue\s*positions?/.test(n)) return 9
  if (/modification\s*positions?/.test(n)) return 8
  // Protein-level position preferred over "position in peptide"
  if (/\bpositions?\b/.test(n) && /peptide/.test(n)) return 4
  if (/\bpositions?\b/.test(n) && !/gene|chrom/.test(n)) return 7
  if (/\bsite\b/.test(n) && /pos/.test(n)) return 7
  return 0
}

function scoreAmino(n: string): number {
  if (/amino\s*acids?/.test(n)) return 10
  if (/^aa$/.test(n) || /^residue$/.test(n)) return 9
  if (/modified\s*residue/.test(n)) return 8
  if (/\bresidue\b/.test(n) && !/position/.test(n)) return 6
  return 0
}

/** MaxQuant-style probability / modified-sequence columns (AA can be inferred). */
function scoreModSequence(n: string): number {
  if (/lactylation\s*probabilities/.test(n)) return 10
  if (/phosphorylation\s*probabilities|modification\s*probabilities/.test(n)) return 9
  if (/modified\s*sequence|mod\.?\s*sequence/.test(n)) return 8
  if (/probabilities/.test(n) && /(lactyl|phospho|acetyl|ubiquit|glyco)/.test(n)) return 8
  return 0
}

function scoreGene(n: string): number {
  if (/^hgnc$/.test(n)) return 10
  if (/^gene\s*names?$/.test(n)) return 10
  if (/^gene\s*symbols?$/.test(n)) return 10
  if (/^gene\s*ids?$/.test(n)) return 8
  if (/^genes?$/.test(n)) return 8
  if (/gene\s*name/.test(n)) return 7
  if (/gene\s*symbol/.test(n)) return 7
  return 0
}

function scoreSiteCombined(n: string): number {
  if (/uniprot.*phosphosite|phosphosite.*uniprot|protein\s*\+\s*phosphosite|gene\s*name\s*\+\s*phosphosite/i.test(n))
    return 11
  if (/modification\s*sites?/.test(n)) return 10
  if (/^phosphosite/.test(n)) return 10
  if (/p[Rr]\s*residue/.test(n)) return 9
  if (/^sites?$/.test(n)) return 8
  if (/phospho.?site|ptm.?site|mod.?site/.test(n)) return 9
  if (/site\s*id/.test(n)) return 5
  return 0
}

function isLog2Header(n: string): boolean {
  return /log\s*2|log2|2\s*log|2log/.test(n)
}

/** Intensity / abundance columns — must NOT be treated as ratios. */
export function scoreIntensity(n: string): number {
  if (/ratio|log\s*2|log2|fold\s*change|\bfc\b/.test(n)) return 0
  if (/peak\s*area|peakarea/.test(n)) return 10
  if (/normalized\s*abundance|abundance/.test(n)) return 9
  if (/\bintensity\b/.test(n)) return 9
  // bare timepoint / channel labels like 0/5, 5/5 without ratio wording
  if (/^\d+\s*\/\s*\d+$/.test(n)) return 8
  if (/^(l|m|h|light|medium|heavy)$/.test(n)) return 5
  return 0
}

function scoreRatio(n: string): number {
  // Hard reject intensity / abundance / peak area
  if (scoreIntensity(n) >= 8) return 0
  if (/variability|count|unique|razor|sequence\s*coverage|stdev|std\.?\s*dev|peptides$/.test(n))
    return 0
  // Inverse of a ratio is redundant when the forward ratio exists
  if (/^1\s*\/\s*/.test(n) || /1\s*\/\s*(nomolized|normalized)/.test(n)) return 3
  // Reject bare timepoint headers (0/5) — those are intensities in many supp tables
  if (/^\d+\s*\/\s*\d+$/.test(n) && !/ratio|log|fold|fc/.test(n)) return 0
  let s = 0
  if (/(log\s*2|log2|2log|2\s*log)/.test(n) && /(ratio|fc|fold)/.test(n)) s = 10
  else if (/^ratio\b/.test(n) || /\bratio\b/.test(n)) s = 8
  else if (/\bfold\s*change\b|\bfc\b/.test(n)) s = 7
  else if (/(log\s*2|log2|2log)/.test(n)) s = 6
  else if (/\baverage\b/.test(n) && /\//.test(n) && /phospho|protein|ratio/.test(n)) s = 7
  else if (/\baverage\b/.test(n) && /(phospho|ratio)/.test(n)) s = 6
  // typo "nomolized" common in some supp tables
  if (/(normalized|nomolized)/.test(n) && s > 0) s += 2
  if (/protein/.test(n) && !/phospho|peptide|site|within/.test(n)) s -= 1
  if (/peptide|site|mod|phospho/.test(n) && s > 0) s += 1
  return s
}

function scorePValue(n: string): number {
  if (/variability|count|intensity/.test(n)) return 0
  if (/significance/.test(n)) return 8
  if (/adj\.?\s*p|q[- ]?value|fdr/.test(n)) return 9
  if (/p[- ]?value|pval|\bp\b/.test(n)) return 8
  return 0
}

function conditionFromRatioHeader(h: string, sheetName = ""): string {
  return conditionLabelFromRatioHeader(h, sheetName)
}

function isSilacRatioMetadataSuffix(suffix: string): boolean {
  return /^(variability|count|significance|shift)\b/i.test(suffix.trim())
}

function ratioDedupKey(h: string, cond: string, level: RatioLevel): string {
  const silacSuffix = silacBiologySuffixFromHeader(h)
  if (silacSuffix && !isSilacRatioMetadataSuffix(silacSuffix)) {
    return `${level}:silac:${silacSuffix.toLowerCase().replace(/[\s_]+/g, "")}`
  }
  return `${level}:${pairConditionKey(cond)}`
}

function ratioIsLog2(h: string): boolean {
  const n = norm(h)
  // SILAC "Ratio H/L …" columns are linear heavy/light ratios, not log2FC
  if (isSilacChannelRatioHeader(n)) return false
  return isLog2Header(n)
}

function pairConditionKey(cond: string): string {
  return cond
    .toLowerCase()
    .replace(/[()\[\]\s]+/g, "")
    .replace(/^m\/l$|^h\/l$|^l\/h$|^h\/m$|^l\/m$|^m\/h$/i, (m) => m.toLowerCase())
}

/** Map ratio/p-value column conditions onto Stage3 Condition / Detail. */
export function alignConditionsToStage3(
  mapping: ColumnMapping,
  stage3Condition: string,
  detailCondition = "",
): ColumnMapping {
  if ((!stage3Condition.trim() && !detailCondition.trim()) || mapping.ratioColumns.length === 0) {
    return mapping
  }

  const originals = mapping.ratioColumns.map(
    (r) => cleanMappedCondition(r.condition || r.column) || (r.condition || r.column),
  )
  const alignedLabels = mapping.ratioColumns.map((r) =>
    resolveRowCondition(r.condition || r.column, stage3Condition, detailCondition),
  )

  // If distinct table conditions were collapsed onto one Stage3 label, restore originals
  const byAligned = new Map<string, Set<string>>()
  for (let i = 0; i < alignedLabels.length; i++) {
    const key = alignedLabels[i].toLowerCase().replace(/\s+/g, "")
    const set = byAligned.get(key) ?? new Set<string>()
    set.add(originals[i].toLowerCase().replace(/\s+/g, ""))
    byAligned.set(key, set)
  }
  const collapsed = new Set<string>()
  for (const [aligned, originalsSet] of byAligned) {
    if (originalsSet.size > 1) collapsed.add(aligned)
  }

  const ratioColumns = mapping.ratioColumns.map((r, i) => {
    const key = alignedLabels[i].toLowerCase().replace(/\s+/g, "")
    const condition = collapsed.has(key) ? originals[i] : alignedLabels[i]
    return { ...r, condition }
  })

  const pValueColumns = mapping.pValueColumns.map((p) => {
    const original = cleanMappedCondition(p.condition || p.column) || (p.condition || p.column)
    let condition = resolveRowCondition(p.condition || p.column, stage3Condition, detailCondition)
    const key = condition.toLowerCase().replace(/\s+/g, "")
    if (collapsed.has(key)) {
      const matchRatio = ratioColumns.find((r) => {
        const rc = r.condition.toLowerCase().replace(/\s+/g, "")
        const oc = original.toLowerCase().replace(/\s+/g, "")
        return rc === oc || oc.includes(rc) || rc.includes(oc)
      })
      condition = matchRatio?.condition || original
    }
    return { ...p, condition }
  })

  return { ...mapping, ratioColumns, pValueColumns }
}

/**
 * Build heuristic mapping for one sheet. confidence in [0,1].
 */
export function heuristicMapSheet(
  entryPath: string,
  sheet: SheetInventory,
): ColumnMapping {
  const headers = sheet.headers.filter(Boolean)
  const uniprotCol = findBest(headers, [scoreUniprot], 5)
  const geneCol = findBest(headers, [scoreGene], 7)
  const positionCol = findBest(headers, [scorePosition], 5)
  const aminoAcidCol = findBest(headers, [scoreAmino], 5)
  const siteCombinedCol = findBest(headers, [scoreSiteCombined], 6)
  const modSeqCol = findBest(headers, [scoreModSequence], 7)

  const intensityColumns = headers.filter((h) => scoreIntensity(norm(h)) >= 8)

  const ratioCandidates: Array<{ h: string; score: number; level: RatioLevel }> = []
  for (const h of headers) {
    const n = norm(h)
    const s = scoreRatio(n)
    if (s < 6) continue
    const level: RatioLevel =
      /protein/.test(n) && !/peptide|site|nomolized|normalized|h\/l|l\/h/.test(n)
        ? "protein"
        : "peptide"
    ratioCandidates.push({ h, score: s, level })
  }
  ratioCandidates.sort((a, b) => b.score - a.score)

  const ratioColumns: MappedRatioColumn[] = []
  const seenCond = new Set<string>()
  for (const r of ratioCandidates) {
    const cond = conditionFromRatioHeader(r.h, sheet.name)
    const key = ratioDedupKey(r.h, cond, r.level)
    if (seenCond.has(key)) continue
    const n = norm(r.h)
    if (!/(normalized|nomolized)/.test(n)) {
      const better = ratioCandidates.find(
        (x) =>
          x.level === r.level &&
          /(normalized|nomolized)/.test(norm(x.h)) &&
          ratioDedupKey(x.h, conditionFromRatioHeader(x.h, sheet.name), x.level) === key,
      )
      if (better) {
        ratioColumns.push({
          column: better.h,
          condition: conditionFromRatioHeader(better.h, sheet.name),
          isLog2: ratioIsLog2(better.h),
          level: better.level,
          valueType: ratioIsLog2(better.h) ? "log2_ratio" : "fold_change",
        })
        seenCond.add(key)
        continue
      }
    }
    ratioColumns.push({
      column: r.h,
      condition: cond,
      isLog2: ratioIsLog2(r.h),
      level: r.level,
      valueType: ratioIsLog2(r.h) ? "log2_ratio" : "fold_change",
    })
    seenCond.add(key)
  }

  // Prefer a single peptide SILAC/normalized ratio; drop protein ratio if same H/L biology
  let peptideRatios = ratioColumns.filter((r) => r.level === "peptide").slice(0, 12)
  let proteinRatios = ratioColumns.filter((r) => r.level === "protein").slice(0, 8)
  if (peptideRatios.length > 0) {
    const pepKeys = new Set(peptideRatios.map((r) => pairConditionKey(r.condition)))
    proteinRatios = proteinRatios.filter((r) => {
      const k = pairConditionKey(r.condition)
      // "protein" alone or same H/L channel → redundant with peptide ratio
      if (k === "protein" || pepKeys.has(k)) return false
      return true
    })
  }
  const finalRatios = [...peptideRatios, ...proteinRatios]

  const pValueColumns: MappedPValueColumn[] = []
  for (const h of headers) {
    const n = norm(h)
    if (scorePValue(n) < 7) continue
    const level: RatioLevel = /protein/.test(n) && !/peptide|site/.test(n) ? "protein" : "peptide"
    let cond = ""
    for (const r of finalRatios) {
      if (r.level !== level) continue
      const rc = pairConditionKey(r.condition)
      if (rc && pairConditionKey(h).includes(rc.replace("/", ""))) {
        cond = r.condition
        break
      }
      const rm = r.column.match(/ratio\s+(\S+)/i)
      const pm = h.match(/ratio\s+(\S+)/i)
      if (rm && pm && rm[1].toLowerCase() === pm[1].toLowerCase()) {
        cond = r.condition
        break
      }
    }
    if (!cond && finalRatios.length === 1) cond = finalRatios[0].condition
    if (!cond) cond = conditionFromRatioHeader(h, sheet.name)
    pValueColumns.push({ column: h, condition: cond, level })
  }

  const hasSite = Boolean(positionCol || siteCombinedCol || aminoAcidCol || modSeqCol)
  const intensityOnly = finalRatios.length === 0 && intensityColumns.length > 0

  let confidence = 0
  if (uniprotCol) confidence += 0.3
  else if (geneCol) confidence += 0.22
  if (positionCol || siteCombinedCol) confidence += 0.3
  else if (aminoAcidCol) confidence += 0.1
  if (aminoAcidCol || siteCombinedCol || modSeqCol) confidence += 0.1
  if (finalRatios.length > 0) confidence += 0.3
  if (pValueColumns.length > 0) confidence += 0.05
  if (!hasSite) confidence -= 0.35
  if (intensityOnly) confidence = Math.min(confidence, 0.4)
  confidence = Math.max(0, Math.min(1, confidence))

  // Prefer siteCombined when position missing; keep both if useful
  let siteCol = siteCombinedCol
  if (positionCol && siteCombinedCol && positionCol === siteCombinedCol) siteCol = null
  // When site is in a combined GENE_S123 column, keep HGNC/gene for gene→UniProt lookup
  const keepGeneCol = Boolean(siteCol && geneCol)
  const accessionCol =
    uniprotCol && siteCol && uniprotCol === siteCol ? null : uniprotCol

  const notesParts: string[] = []
  if (!accessionCol && geneCol) notesParts.push("gene→UniProt")
  else if (keepGeneCol) notesParts.push("gene→UniProt")
  else if (!accessionCol) notesParts.push("no UniProt column")
  if (!positionCol && !siteCombinedCol && !aminoAcidCol && !modSeqCol) notesParts.push("no_site_level")
  else if (!aminoAcidCol && modSeqCol) notesParts.push("AA←modSeq")
  if (finalRatios.length === 0) notesParts.push("no ratio column")
  if (intensityOnly) notesParts.push("intensity_only")
  if (intensityColumns.length > 0 && finalRatios.length === 0) {
    notesParts.push(`intensity_cols=${intensityColumns.slice(0, 6).join("|")}`)
  }
  if (finalRatios.length > 1) notesParts.push(`${finalRatios.length} ratio conditions`)

  return {
    entryPath,
    sheetName: sheet.name,
    headerRowIndex: sheet.headerRowIndex ?? 0,
    confidence,
    source: "heuristic",
    uniprotCol: accessionCol,
    geneCol: keepGeneCol || !accessionCol ? geneCol : null,
    positionCol,
    aminoAcidCol,
    siteCombinedCol: positionCol && !siteCombinedCol ? null : siteCol,
    modSeqCol: aminoAcidCol ? null : modSeqCol,
    ratioColumns: finalRatios,
    pValueColumns: pValueColumns.slice(0, 24),
    intensityOnly,
    intensityColumns,
    notes: notesParts.join("; "),
  }
}

/** High enough to parse without LLM */
export const HEURISTIC_HIGH = 0.72
/** Worth attempting parse after LLM fails if still usable */
export const HEURISTIC_MIN_PARSE = 0.55

/** Parsable into qratio with UniProt (or gene→UniProt) + true ratio cols + site signal */
export function mappingIsParsable(m: ColumnMapping): boolean {
  if (m.intensityOnly) return false
  if (m.ratioColumns.some((r) => r.valueType === "intensity")) return false
  const hasSite = Boolean(m.positionCol || m.siteCombinedCol || m.aminoAcidCol || m.modSeqCol)
  const hasId = Boolean(m.uniprotCol || m.geneCol)
  return hasId && m.ratioColumns.length > 0 && hasSite
}

export function mappingNeedsManual(m: ColumnMapping): boolean {
  if (m.intensityOnly) return false
  if (!mappingIsParsable(m)) return true
  if (m.confidence < 0.45) return true
  return false
}
