/**
 * Map Stage3 Condition labels → Sample for qratio rows.
 *
 * Map string format (from Stage3 / literature_info):
 *   "HCC/Normal=>HCC tissue; Lung metastasis/Normal=>lung metastasis tissue"
 */

function splitParts(raw: string): string[] {
  return (raw || "")
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean)
}

function normKey(s: string): string {
  return (s || "")
    .toLowerCase()
    .replace(/[_\-–—]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

/** Compact form so MCF-7 ≡ MCF7, MDA-MB-231 ≡ MDAMB231. */
function compactKey(s: string): string {
  return normKey(s).replace(/[^a-z0-9]+/gi, "").toLowerCase()
}

/** Parse "Cond=>Sample; Cond2=>Sample2" (also accepts "Cond=Sample").
 * If the same condition is mapped to multiple different samples (common when
 * Stage3 lists N cell lines that share one contrast), drop that key — Sample
 * must then come from the sheet / table context, not the condition map.
 */
export function parseConditionSampleMap(raw: string): Map<string, string> {
  const out = new Map<string, string>()
  const ambiguous = new Set<string>()
  for (const part of splitParts(raw)) {
    const m = part.match(/^(.+?)\s*(?:=>|=)\s*(.+)$/)
    if (!m) continue
    const cond = m[1].trim()
    const sample = m[2].trim()
    if (!cond || !sample) continue
    const key = normKey(cond)
    const prev = out.get(key)
    if (prev && normKey(prev) !== normKey(sample)) {
      ambiguous.add(key)
      continue
    }
    out.set(key, sample)
  }
  for (const k of ambiguous) out.delete(k)
  return out
}

export function lookupConditionSample(
  mapRaw: string | undefined,
  condition: string,
): string {
  if (!mapRaw?.trim() || !condition?.trim()) return ""
  const map = parseConditionSampleMap(mapRaw)
  if (map.size === 0) return ""
  const key = normKey(condition)
  if (map.has(key)) return map.get(key)!
  // Fuzzy: map key contained in condition or vice versa
  let best = ""
  let bestScore = 0
  for (const [k, sample] of map) {
    if (!k) continue
    let score = 0
    if (key === k) score = 100
    else if (key.includes(k) || k.includes(key)) score = Math.min(k.length, key.length)
    if (score > bestScore) {
      bestScore = score
      best = sample
    }
  }
  return bestScore >= 3 ? best : ""
}

function tokenize(s: string): string[] {
  return normKey(s)
    .split(/[^a-z0-9]+/i)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2)
}

/** Score how well a sample name matches a condition arm (e.g. "HCC" vs "HCC tissue"). */
function scoreSampleArm(sample: string, arm: string): number {
  const a = normKey(arm)
  const s = normKey(sample)
  if (!a || !s) return 0
  if (s === a) return 100
  const ca = compactKey(arm)
  const cs = compactKey(sample)
  if (ca && cs && ca === cs) return 100
  // Prefer exact compact equality over substring (MCF7 must not lose to MCF10A)
  if (ca && cs && (cs.includes(ca) || ca.includes(cs))) {
    // Penalize weak substring when lengths differ a lot (mcf ⊂ mcf10a)
    const ratio = Math.min(ca.length, cs.length) / Math.max(ca.length, cs.length)
    if (ratio >= 0.75) return 90
    if (ratio >= 0.5) return 40
  }
  if (s.includes(a) || a.includes(s)) return 80
  const at = new Set(tokenize(a))
  const st = tokenize(s)
  let hit = 0
  for (const t of st) {
    if (at.has(t)) hit += t.length >= 4 ? 3 : 1
  }
  return hit
}

/**
 * Infer focal sample for a comparison condition (Treatment/Control).
 * Uses the numerator (left of "/") as the primary sample when possible.
 */
export function inferSampleFromCondition(stage3Sample: string, condition: string): string {
  const samples = splitParts(stage3Sample)
  if (samples.length === 0) return ""
  if (samples.length === 1) return samples[0]
  const cond = (condition || "").trim()
  if (!cond) return ""

  const arms = cond
    .split("/")
    .map((a) => a.trim())
    .filter(Boolean)
  const focusArm = arms[0] || cond

  let best = ""
  let bestScore = 0
  for (const sample of samples) {
    // Only match the numerator arm — do NOT score against the full "A/B"
    // string, or the denominator sample (often the shared control) wins.
    const score = scoreSampleArm(sample, focusArm)
    if (score > bestScore) {
      bestScore = score
      best = sample
    }
  }
  // Require a minimal match so we don't invent
  return bestScore >= 2 ? best : ""
}

/**
 * Build Condition=>Sample map from Stage3 Sample + Condition lists.
 * Used when the LLM did not emit an explicit map.
 * Multi-sample + shared condition is left empty (ambiguous) — Stage5 should
 * resolve Sample from per-sample sheets or other table context.
 */
export function buildConditionSampleMap(
  stage3Sample: string,
  stage3Condition: string,
  explicitMap?: string,
): string {
  if (explicitMap && explicitMap.trim()) {
    // Re-serialize after dropping ambiguous Cond=>Sample collisions
    const map = parseConditionSampleMap(explicitMap)
    if (map.size === 0) return ""
    return [...map.entries()]
      .map(([k, sample]) => {
        // Recover a readable condition label from the explicit map if possible
        for (const part of splitParts(explicitMap)) {
          const m = part.match(/^(.+?)\s*(?:=>|=)\s*(.+)$/)
          if (!m) continue
          if (normKey(m[1]) === k && normKey(m[2]) === normKey(sample)) {
            return `${m[1].trim()}=>${m[2].trim()}`
          }
        }
        return `${k}=>${sample}`
      })
      .join("; ")
  }
  const samples = splitParts(stage3Sample)
  const conditions = splitParts(stage3Condition)
  if (samples.length === 0 || conditions.length === 0) return ""
  if (samples.length === 1) {
    return conditions.map((c) => `${c}=>${samples[0]}`).join("; ")
  }
  // One shared contrast across many samples cannot name a unique Sample
  if (conditions.length === 1 && samples.length > 1) return ""
  const pairs: string[] = []
  for (const c of conditions) {
    const s = inferSampleFromCondition(stage3Sample, c)
    if (s) pairs.push(`${c}=>${s}`)
  }
  return pairs.join("; ")
}

/**
 * True when Excel sheet names clearly correspond to Stage3 Samples
 * (e.g. sheets MCF7 / MDA-MB-231 / MDA-MB-436 with the same Stage3 list).
 */
export function sheetsAlignWithStage3Samples(
  sheetNames: string[],
  stage3Sample: string,
): { aligned: boolean; matchedSamples: string[]; matchedSheets: string[] } {
  const samples = splitParts(stage3Sample)
  const sheets = (sheetNames || []).map((s) => (s || "").trim()).filter(Boolean)
  const matchedSamples: string[] = []
  const matchedSheets: string[] = []
  if (samples.length < 2 || sheets.length === 0) {
    return { aligned: false, matchedSamples, matchedSheets }
  }

  for (const sample of samples) {
    let bestSheet = ""
    let bestScore = 0
    for (const sheet of sheets) {
      if (/^(sheet\s*\d*|quant(?:ified)?|data|table\d*|proteome|phospho|protein)$/i.test(sheet)) {
        continue
      }
      let score = 0
      if (normKey(sample) === normKey(sheet)) score = 100
      else score = scoreSampleArm(sample, sheet)
      if (score > bestScore) {
        bestScore = score
        bestSheet = sheet
      }
    }
    if (bestScore >= 50) {
      matchedSamples.push(sample)
      matchedSheets.push(bestSheet)
    }
  }

  // Need at least 2 Stage3 samples matched to distinct sheets
  const uniqueSheets = new Set(matchedSheets.map((s) => normKey(s)))
  const aligned =
    matchedSamples.length >= 2 &&
    uniqueSheets.size >= 2 &&
    matchedSamples.length >= Math.min(samples.length, 2)
  return { aligned, matchedSamples, matchedSheets }
}

/**
 * Resolve Sample for one qratio row.
 */
export function resolveRowSample(
  stage3Sample: string,
  opts?: {
    tableSample?: string
    condition?: string
    conditionSampleMap?: string
  },
): string {
  const fromTable = (opts?.tableSample || "").trim()
  if (fromTable && !fromTable.includes(";")) return fromTable

  const condition = (opts?.condition || "").trim()
  const mapRaw = (opts?.conditionSampleMap || "").trim()
  if (mapRaw) {
    const hit = lookupConditionSample(mapRaw, condition)
    if (hit) return hit
  }

  const parts = splitParts(stage3Sample)
  if (parts.length === 1) return parts[0]
  if (parts.length === 0) return ""

  if (condition) {
    // Auto-build map from all Stage3 conditions if we only have this one row condition —
    // inferSampleFromCondition works from sample list + this condition alone.
    const inferred = inferSampleFromCondition(stage3Sample, condition)
    if (inferred) return inferred
  }

  return ""
}

/**
 * True when a sheet tab is a descriptive table title, not a biological sample name.
 * e.g. "Detected Kme sites with trigger", "Phospho (STY)Sites", "Table S2".
 */
export function looksLikeDescriptiveSheetTitle(sheetName: string): boolean {
  const s = (sheetName || "").trim()
  if (!s) return true
  if (
    /^(sheet\s*\d*|quant(?:ified)?|data|table\s*s?\d*|proteome|phospho|protein|results?)$/i.test(
      s,
    )
  ) {
    return true
  }
  if (
    /\b(detected|sites?|peptides?|proteins?|with\s+trigger|results?|supplementary|enriched|identified|quantified)\b/i.test(
      s,
    )
  ) {
    return true
  }
  // Long multi-word titles are almost never sample names
  if (/\s/.test(s) && s.length >= 18) return true
  return false
}

/**
 * Map an Excel sheet name to a Stage3 Sample when sheets are per-sample
 * (e.g. sheets MCF7 / MDA-MB-231 / MDA-MB-436).
 */
export function resolveSheetAsSample(
  sheetName: string,
  stage3Sample: string,
  preferSheetAsSample = false,
): string {
  const sheet = (sheetName || "").trim()
  if (!sheet) return ""
  const samples = splitParts(stage3Sample)

  for (const s of samples) {
    if (normKey(s) === normKey(sheet)) return s
  }
  let best = ""
  let bestScore = 0
  for (const s of samples) {
    const score = scoreSampleArm(s, sheet)
    if (score > bestScore) {
      bestScore = score
      best = s
    }
  }
  if (bestScore >= 50) return best

  // Descriptive titles ("Detected Kme sites…") are never samples.
  if (looksLikeDescriptiveSheetTitle(sheet)) return ""

  // Only when Stage3 sheets are explicitly per-sample (preferSheetAsSample)
  // may we keep a short sheet label that did not fuzzy-match.
  if (preferSheetAsSample) return sheet

  return ""
}
