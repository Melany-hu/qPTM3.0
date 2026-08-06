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

/** Parse "Cond=>Sample; Cond2=>Sample2" (also accepts "Cond=Sample"). */
export function parseConditionSampleMap(raw: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const part of splitParts(raw)) {
    const m = part.match(/^(.+?)\s*(?:=>|=)\s*(.+)$/)
    if (!m) continue
    const cond = m[1].trim()
    const sample = m[2].trim()
    if (!cond || !sample) continue
    out.set(normKey(cond), sample)
  }
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
  if (s.includes(a) || a.includes(s)) return 80
  const at = new Set(tokenize(a))
  const st = tokenize(s)
  let hit = 0
  for (const t of st) {
    if (at.has(t)) hit += t.length >= 4 ? 3 : 1
  }
  // Prefer distinctive tokens (HCC, metastasis) over stop-ish words
  if (/\b(tissue|cell|cells|sample|samples|normal|control|ctr|wt)\b/i.test(a)) {
    // still ok
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
    const score = scoreSampleArm(sample, focusArm)
    // Slight boost if sample tokens appear anywhere in the full condition
    const anywhere = scoreSampleArm(sample, cond) * 0.25
    const total = score + anywhere
    if (total > bestScore) {
      bestScore = total
      best = sample
    }
  }
  // Require a minimal match so we don't invent
  return bestScore >= 2 ? best : ""
}

/**
 * Build Condition=>Sample map from Stage3 Sample + Condition lists.
 * Used when the LLM did not emit an explicit map.
 */
export function buildConditionSampleMap(
  stage3Sample: string,
  stage3Condition: string,
  explicitMap?: string,
): string {
  if (explicitMap && explicitMap.trim()) return explicitMap.trim()
  const samples = splitParts(stage3Sample)
  const conditions = splitParts(stage3Condition)
  if (samples.length === 0 || conditions.length === 0) return ""
  if (samples.length === 1) {
    return conditions.map((c) => `${c}=>${samples[0]}`).join("; ")
  }
  const pairs: string[] = []
  for (const c of conditions) {
    const s = inferSampleFromCondition(stage3Sample, c)
    if (s) pairs.push(`${c}=>${s}`)
  }
  return pairs.join("; ")
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
