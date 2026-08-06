/**
 * Align Stage5 Condition labels using Stage3 Condition + Detail condition.
 *
 * Rules:
 * - Cryptic table/sheet labels ("Is 6 h vs. sham", "B4/B1") → match onto
 *   richer Stage3 fragments or phrases mined from Detail condition
 *   (e.g. "6 h cerebral ischemia/Sham").
 * - Fine-grained table labels (MI_30/SHAM) that add timepoints beyond Stage3
 *   → keep the table label.
 * - Generic / SILAC channel headers → Stage3 (or detail-derived) candidates.
 */
/**
 * MaxQuant-style SILAC headers: "Ratio H/L …", "Ratio M/L …" (linear H/L ratio, not log2FC).
 */
export function isSilacChannelRatioHeader(h: string): boolean {
  return /(?:^|\s)ratio\s+[hml]\s*\/\s*[hml]\b/i.test((h || "").trim())
}

/** Biology suffix after SILAC channel ratio, e.g. "WT_10min" from "Ratio H/L normalized WT_10min". */
export function silacBiologySuffixFromHeader(h: string): string {
  const n = (h || "").trim()
  let m = n.match(/(?:^|\s)ratio\s+[hml]\s*\/\s*[hml](?:\s+normalized)?\s+(.+)$/i)
  if (m) return m[1].trim()
  m = n.match(/mean\s+ratio\s+[hml]\s*\/\s*[hml](?:\s+normalized)?\s+(.+)$/i)
  if (m) return m[1].trim()
  return ""
}

export function formatSilacBiologyLabel(suffix: string): string {
  return suffix.replace(/_/g, " ").replace(/\s+/g, " ").trim()
}

function isSilacRatioMetadataSuffix(suffix: string): boolean {
  return /^(variability|count|significance|shift)\b/i.test(suffix.trim())
}

/** Condition label from a ratio column header (shared by heuristic + proteome). */
export function conditionLabelFromRatioHeader(h: string, sheetName = ""): string {
  const n = (h || "").trim()
  const silacSuffix = silacBiologySuffixFromHeader(n)
  if (silacSuffix && !isSilacRatioMetadataSuffix(silacSuffix)) {
    return formatSilacBiologyLabel(silacSuffix)
  }

  // Proteome Discoverer: "Abundance Ratio: (Heavy) / (Light)"
  let m = n.match(
    /abundance\s*ratio\s*:?\s*\(?\s*(heavy|light|medium)\s*\)?\s*\/\s*\(?\s*(heavy|light|medium)/i,
  )
  if (m) return `${m[1]}/${m[2]}`

  m = n.match(/ratio\s+([^/\s]+)\s*\/\s*([^/\s]+)/i)
  let base = ""
  if (m) base = `${m[1]}/${m[2]}`
  else {
    m = n.match(
      /^(.+?)\s*\/\s*(.+?)(?:\s+(?:adj\.?\s*)?(?:p[- ]?value|pvalue|q[- ]?value|fdr|ratio|fc|fold(?:\s*change)?))?$/i,
    )
    if (m) {
      const left = m[1].replace(/\b(normalized|peptide|protein|site|log2?)\b/gi, "").trim()
      const right = m[2].replace(/\b(normalized|peptide|protein|site|log2?)\b/gi, "").trim()
      if (left && right && left.length < 60 && right.length < 60) base = `${left}/${right}`
    }
  }
  if (!base) {
    m = n.match(/(?:log2?(?:\s*ratio)?|fc|fold(?:\s*change)?)\s*[:_\-]?\s*(.+)$/i)
    if (m) {
      const rest = m[1].replace(/\b(normalized|peptide|protein|site)\b/gi, "").trim()
      if (rest.length > 1 && rest.length < 80) base = rest
    }
  }
  if (!base) base = cleanMappedCondition(n) || n
  base = base.replace(/^\(+/, "").replace(/\)+$/, "").replace(/^[:\-\s]+/, "").trim()
  if (/^B\d+\s*\/\s*B\d+$/i.test(base) && sheetName && /vs\.?/i.test(sheetName)) {
    return sheetName.replace(/\s+/g, " ").trim()
  }
  return base
}

export function isChannelLabel(cond: string): boolean {
  const c = cond.trim().replace(/^[:\-\s]+/, "")
  if (!c) return false
  if (/^(m\/l|h\/l|h\/m|l\/h|l\/m|m\/h|heavy\/light|light\/heavy|medium\/light|heavy\/medium)$/i.test(c))
    return true
  if (/\(?heavy\)?\s*\/\s*\(?light\)?/i.test(c) || /\(?light\)?\s*\/\s*\(?heavy\)?/i.test(c)) return true
  if (/^(L|M|H|Light|Medium|Heavy)$/i.test(c)) return true
  if (/^\.\d+$/.test(c)) return true
  if (/^B\d+\s*\/\s*B\d+$/i.test(c)) return true
  return false
}

/**
 * Generic spreadsheet headers that are NOT biological conditions
 * (e.g. "(Fold Change)", "Log2Ratio", "FC", "Ratio").
 */
export function isGenericRatioLabel(cond: string): boolean {
  const c = cond.trim().replace(/^[(\[]|[)\]]$/g, "").trim()
  if (!c) return true
  if (/^(fold\s*change|fc|log2?(?:\s*fc|\s*ratio)?|ratio|change|pvalue|p[- ]?value|q[- ]?value|fdr)$/i.test(c))
    return true
  if (/^(log2?\s*)?(fold[- ]?change|ratio)(\s*\(.*\))?$/i.test(c)) return true
  if (/^(avg|mean|median)?\s*(log2?)?\s*(fc|fold|ratio)\b/i.test(c) && !/[\/_]/.test(c)) return true
  return false
}

/**
 * MaxQuant / spreadsheet technical ratio labels (not biological treatment contrasts).
 * e.g. "mod/base", "modified/unmodified", "label/parent".
 */
export function isTechnicalRatioLabel(cond: string): boolean {
  const raw = cleanMappedCondition(cond).toLowerCase().replace(/\s+/g, "")
  if (!raw || !raw.includes("/")) return false
  const [left, right] = raw.split("/")
  if (!left || !right) return false
  const tech = new Set([
    "mod",
    "modified",
    "base",
    "unmod",
    "unmodified",
    "parent",
    "label",
    "heavy",
    "light",
    "medium",
    "silac",
  ])
  if (tech.has(left) && tech.has(right)) return true
  if ((left === "mod" || left === "modified") && (right === "base" || right === "unmod" || right === "unmodified"))
    return true
  if ((left === "label" || left === "heavy" || left === "light") && (right === "base" || right === "parent"))
    return true
  return false
}

/**
 * Spreadsheet placeholder contrasts (A/B, AvsB, Group1/Group2) that carry no biology —
 * replace with Stage3 Condition when available.
 */
export function isPlaceholderGroupLabel(cond: string): boolean {
  const s = cleanMappedCondition(cond).trim()
  if (!s) return false
  // A/B, A / B, A_B (single-letter arms)
  if (/^[A-Za-z]\s*[\/_]\s*[A-Za-z]$/.test(s)) return true
  // A vs B / AvsB / A-versus-B
  if (/^[A-Za-z]\s*(?:vs\.?|versus)\s*[A-Za-z]$/i.test(s)) return true
  if (/^[A-Za-z]vs\.?[A-Za-z]$/i.test(s)) return true
  // Group A / Group B, SampleA/SampleB, Cond1/Cond2
  if (
    /^(?:group|sample|cond(?:ition)?|set|batch|arm|cohort)\s*[A-Za-z0-9]+\s*[\/_]\s*(?:group|sample|cond(?:ition)?|set|batch|arm|cohort)?\s*[A-Za-z0-9]+$/i.test(
      s,
    )
  ) {
    return true
  }
  // Bare numeric / G1/G2 arms
  if (/^(?:g)?\d{1,2}\s*[\/_]\s*(?:g)?\d{1,2}$/i.test(s)) return true
  return false
}

/** Sheet / batch style labels that should be expanded via Detail condition. */
export function isCrypticCondition(cond: string): boolean {
  const s = cleanMappedCondition(cond)
  if (!s) return true
  if (
    isChannelLabel(s) ||
    isGenericRatioLabel(s) ||
    isTechnicalRatioLabel(s) ||
    isPlaceholderGroupLabel(s)
  ) {
    return true
  }
  if (/\bvs\.?\b/i.test(s)) return true
  if (/^(is|rep|exp|group|batch|condition)\b/i.test(s)) return true
  // short title without A/B slash biology
  if (!/[\/_]/.test(s) && s.length <= 40 && /\b(sham|ctrl|control|vehicle)\b/i.test(s)) return true
  return false
}

/** Strip trailing Ratio / P value noise from column-derived labels. */
export function cleanMappedCondition(mapped: string): string {
  return mapped
    .replace(/\s*(?:adj\.?\s*)?(?:p[- ]?value|pvalue|q[- ]?value|fdr)\s*$/i, "")
    .replace(/\s*(?:log2?\s*)?(?:ratio|fold\s*change|fc)\s*$/i, "")
    .replace(/\s+/g, " ")
    .trim()
}

function stage3Parts(stage3Condition: string): string[] {
  return stage3Condition
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean)
}

function normTokens(s: string): string[] {
  return s
    .toLowerCase()
    .replace(/ratio\b/g, " ")
    .replace(/\bvs\.?\b/g, " ")
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length >= 1)
}

function expandToken(t: string): Set<string> {
  const out = new Set<string>([t])
  const map: Record<string, string[]> = {
    ctr: ["control", "ctrl", "con", "ctl"],
    ctrl: ["control", "ctr", "con"],
    con: ["control", "ctr", "ctrl"],
    control: ["ctr", "ctrl", "con"],
    ex: ["exercise"],
    exercise: ["ex"],
    ir: ["ischemia", "reperfusion"],
    is: ["ischemia", "ischaemia"],
    ischemia: ["is", "ischaemia"],
    ischaemia: ["ischemia", "is"],
    rep: ["reperfusion"],
    reperfusion: ["rep"],
    mi: ["myocardial", "infarction"],
    sham: ["sh"],
  }
  for (const x of map[t] ?? []) out.add(x)
  return out
}

function tokenSet(s: string): Set<string> {
  const out = new Set<string>()
  for (const t of normTokens(s)) {
    for (const e of expandToken(t)) out.add(e)
  }
  return out
}

function scoreConditionMatch(mapped: string, stage3Part: string): number {
  const a = tokenSet(mapped)
  const b = tokenSet(stage3Part)
  // Keep digits (timepoints) and length>=2 tokens
  const aSig = [...a].filter((t) => t.length >= 2 || /^\d+$/.test(t))
  const bSig = [...b].filter((t) => t.length >= 2 || /^\d+$/.test(t))
  if (aSig.length === 0 || bSig.length === 0) return 0
  let hit = 0
  for (const t of aSig) if (b.has(t)) hit++
  for (const ta of aSig) {
    for (const tb of bSig) {
      if (ta.length >= 2 && tb.length >= 2 && (ta.startsWith(tb) || tb.startsWith(ta))) hit += 0.5
    }
  }
  // Bonus for shared timepoint numbers
  const aNums = new Set(aSig.filter((t) => /^\d+$/.test(t)))
  const bNums = new Set(bSig.filter((t) => /^\d+$/.test(t)))
  for (const n of aNums) if (bNums.has(n)) hit += 1.5
  return hit
}

/** Token overlap score between a table-derived label and a Stage3 comparison fragment. */
export function biologicalConditionOverlap(mapped: string, stage3Part: string): number {
  return scoreConditionMatch(mapped, stage3Part)
}

/**
 * True when spreadsheet label carries extra biological detail beyond Stage3
 * (timepoints, doses, sub-comparisons like MI_6h/MI_30).
 */
export function hasExtraSpecificity(mapped: string, stage3Part: string): boolean {
  const cleaned = cleanMappedCondition(mapped)
  if (!cleaned || isCrypticCondition(cleaned) || isPlaceholderGroupLabel(cleaned)) return false
  const a = normTokens(cleaned)
  const b = tokenSet(stage3Part)
  const extras = a.filter((t) => {
    // Single-letter arms (A/B) are not biological specificity.
    if (t.length <= 1 && !/^\d+$/.test(t)) return false
    if (b.has(t)) return false
    for (const e of expandToken(t)) if (b.has(e)) return false
    return true
  })
  if (extras.length === 0) return false
  if (extras.some((t) => /\d/.test(t))) return true
  if (extras.some((t) => /^(h|hr|hrs|min|mins|day|days|wk|week|weeks|mo|month)$/i.test(t))) return true
  if (extras.filter((t) => t.length >= 2).length >= 1 && /[\/_]/.test(cleaned)) {
    if (cleaned.toLowerCase().replace(/\s+/g, "") !== stage3Part.toLowerCase().replace(/\s+/g, "")) {
      return extras.some((t) => t.length >= 2 && !/^\d+$/.test(t))
    }
  }
  return false
}

function normalizeTreatmentPhrase(phrase: string): string {
  return phrase
    .replace(/^(?:of|the|a|an)\s+/i, "")
    .replace(/\s+of\s+/gi, " ")
    .replace(/\s+and\s+/gi, " + ")
    .replace(/\s+/g, " ")
    .trim()
}

/**
 * Mine compact Treatment/Baseline comparisons from Detail condition prose.
 * Example: "...mice after 6 h of cerebral ischemia, and mice after 1.5 h of
 * ischemia and 24 h of reperfusion..." + sham →
 * ["6 h cerebral ischemia/Sham", "1.5 h ischemia + 24 h reperfusion/Sham"]
 */
export function extractComparisonsFromDetail(detailCondition: string): string[] {
  const d = (detailCondition || "").replace(/\s+/g, " ").trim()
  if (!d) return []

  const hasSham = /\bsham\b/i.test(d)
  const hasCtrl = /\b(controls?|untreated|vehicle|normal|dmso)\b/i.test(d)
  const baseline = hasSham ? "Sham" : hasCtrl ? "Ctr" : ""
  if (!baseline) return []

  const out: string[] = []
  const seen = new Set<string>()
  const push = (treatment: string) => {
    const t = normalizeTreatmentPhrase(treatment)
    if (t.length < 4 || t.length > 120) return
    if (/\b(analyzed|samples?|mice|rats?|cells?|were|for)\b/i.test(t) && t.split(/\s+/).length > 10)
      return
    const label = `${t}/${baseline}`
    const key = label.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    out.push(label)
  }

  // Prefer "mice after <treatment>" splits (handles decimals like 1.5 h)
  for (const part of d.split(/\b(?:mice|rats|animals|samples)\s+after\s+/i).slice(1)) {
    let t = part
    t = t.replace(/,?\s*and\s+(?:mice|rats|animals)\b[\s\S]*$/i, "")
    t = t.replace(/\s+were\b[\s\S]*$/i, "")
    t = t.replace(/\s+was\b[\s\S]*$/i, "")
    t = t.replace(/[.;]\s*$/g, "").trim()
    // cut trailing clause junk
    t = t.replace(/,?\s*and\s*$/i, "").trim()
    if (t) push(t)
  }

  // "treated with 10 μM MG132 for 6 h … compared to DMSO"
  const treatedWith = d.match(
    /\btreated\s+with\s+(.+?)(?:\s+for\s+|\s+to\s+|,\s*compared|\s+compared|\.|;|$)/i,
  )
  if (treatedWith) push(treatedWith[1])

  // Fallback: "after <phrase>" when the split above finds nothing
  if (out.length === 0) {
    const afterRe =
      /(?:after|following|subjected to)\s+([\w][\w\s.+/-]*?)(?=(?:\s*,\s*(?:and\s+)?(?:mice|rats)|\s+were\b|\s*;|\.|$))/gi
    let m: RegExpExecArray | null
    while ((m = afterRe.exec(d))) {
      push(m[1])
    }
  }

  // "6 h cerebral ischemia vs sham" already compact in detail
  const vsRe =
    /([A-Za-z0-9][^/;,]{2,60}?)\s+(?:vs\.?|versus|compared(?:\s+with|\s+to)?)\s+(sham|control|ctr|vehicle|dmso)/gi
  let m: RegExpExecArray | null
  while ((m = vsRe.exec(d))) {
    push(m[1])
  }

  return out
}

/**
 * Mine timepoint contrasts from prose like "treated with 2 mM H2O2 for 0.5, 1, 2, and 4 hours".
 */
export function extractTimepointComparisonsFromDetail(detailCondition: string): string[] {
  const d = (detailCondition || "").replace(/\s+/g, " ").trim()
  if (!d) return []

  const forM = d.match(
    /\bfor\s+([\d.]+\s*(?:hours?|hrs?|min(?:utes)?|days?)(?:\s*,\s*[\d.]+\s*(?:hours?|hrs?|min(?:utes)?|days?))*(?:\s*,?\s*and\s+[\d.]+\s*(?:hours?|hrs?|min(?:utes)?|days?))?)/i,
  )
  if (!forM) return []

  const times = forM[1]
    .split(/\s*,\s*|\s+and\s+/i)
    .map((t) => t.trim())
    .filter((t) => /\d/.test(t))
  if (times.length === 0) return []

  let agent = ""
  const agentM = d.match(/(?:treated|exposed)\s+(?:with\s+)?((?:\d+\s*m?M\s+)?[A-Za-z0-9-]+)/i)
  if (agentM) agent = agentM[1].trim()

  const baseline = /\bsham\b/i.test(d) ? "Sham" : /\b(controls?|untreated|vehicle)\b/i.test(d) ? "Ctr" : "Ctr"

  const out: string[] = []
  const seen = new Set<string>()
  for (const t of times) {
    const label = agent ? `${t} ${agent}/${baseline}` : `${t}/${baseline}`
    const key = label.toLowerCase().replace(/\s+/g, "")
    if (seen.has(key)) continue
    seen.add(key)
    out.push(label)
  }
  return out
}

/** Stage3 Condition parts that look biologically informative (not sheet-name residue). */
export function informativeStage3Parts(stage3Condition: string): string[] {
  return stage3Parts(stage3Condition).filter((p) => !isCrypticCondition(p))
}

/** Candidates for alignment: informative Stage3 fragments + Detail-mined comparisons. */
export function conditionCandidates(
  stage3Condition: string,
  detailCondition = "",
): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const p of [
    ...informativeStage3Parts(stage3Condition),
    ...extractComparisonsFromDetail(detailCondition),
    ...extractTimepointComparisonsFromDetail(detailCondition),
  ]) {
    const key = p.toLowerCase().replace(/\s+/g, "")
    if (seen.has(key)) continue
    seen.add(key)
    out.push(p)
  }
  return out
}

/** Pick best candidate label for a mapped spreadsheet condition. */
export function matchStage3Condition(
  mapped: string,
  stage3Condition: string,
  detailCondition = "",
): string | null {
  const cleaned = cleanMappedCondition(mapped)
  const parts = conditionCandidates(stage3Condition, detailCondition)
  if (parts.length === 0) {
    const fallback = stage3Parts(stage3Condition)
    if (fallback.length === 1) return fallback[0]
    return null
  }
  if (parts.length === 1 && (isCrypticCondition(cleaned) || !cleaned)) return parts[0]

  const exact = parts.find((p) => p.toLowerCase() === cleaned.toLowerCase())
  if (exact) return exact

  let best: string | null = null
  let bestScore = 0
  for (const p of parts) {
    const s = scoreConditionMatch(cleaned, p)
    if (s > bestScore) {
      bestScore = s
      best = p
    }
  }
  // Cryptic labels need a weaker bar; informative mapped labels need clearer overlap
  const minScore = isCrypticCondition(cleaned) ? 1.5 : 2
  return bestScore >= minScore ? best : null
}

/**
 * One biological condition per row.
 * Prefer Detail/Stage3-expanded labels over cryptic sheet names; keep finer table ratios.
 */
export function resolveRowCondition(
  mappedCondition: string,
  stage3Condition: string,
  detailCondition = "",
): string {
  const mapped = cleanMappedCondition(mappedCondition || "")
  const candidates = conditionCandidates(stage3Condition, detailCondition)
  const parts = candidates.length > 0 ? candidates : stage3Parts(stage3Condition)

  if (parts.length === 0) return mapped || (mappedCondition || "").trim()

  const placeholderOrCryptic =
    isChannelLabel(mapped) ||
    isGenericRatioLabel(mapped) ||
    isPlaceholderGroupLabel(mapped) ||
    isTechnicalRatioLabel(mapped) ||
    !mapped ||
    isCrypticCondition(mapped)

  if (parts.length === 1) {
    if (placeholderOrCryptic) {
      return parts[0]
    }
    if (hasExtraSpecificity(mapped, parts[0])) return mapped
    if (scoreConditionMatch(mapped, parts[0]) >= 1) return parts[0]
    return mapped
  }

  if (placeholderOrCryptic) {
    return (
      matchStage3Condition(mapped, stage3Condition, detailCondition) ||
      parts[0] ||
      parts.join("; ")
    )
  }

  const matched = matchStage3Condition(mapped, stage3Condition, detailCondition)
  if (matched && hasExtraSpecificity(mapped, matched)) return mapped
  if (matched) return matched
  return mapped
}
