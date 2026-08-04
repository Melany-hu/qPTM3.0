import type { LiteratureInfoRow, MetaStatus, MetaTextSource } from "../../types.js"

export class MetaParseError extends Error {
  constructor(
    message: string,
    public readonly raw: string,
  ) {
    super(message)
    this.name = "MetaParseError"
  }
}

function extractJsonObject(text: string): unknown {
  const cleaned = text
    .replace(/```json/gi, "")
    .replace(/```/g, "")
    .trim()

  try {
    return JSON.parse(cleaned)
  } catch {
    // fall through
  }

  const start = cleaned.indexOf("{")
  const end = cleaned.lastIndexOf("}")
  if (start >= 0 && end > start) {
    try {
      return JSON.parse(cleaned.slice(start, end + 1))
    } catch {
      // fall through
    }
  }
  throw new MetaParseError("Failed to parse JSON object from LLM output", text)
}

function asStr(v: unknown): string {
  if (v == null) return ""
  return String(v).trim()
}

const CORE_FIELDS = [
  "sample",
  "sampleType",
  "organism",
  "ptms",
  "labelMethod",
  "condition",
  "detailCondition",
  "enrichmentMethod",
  "massSpectrometer",
] as const

function inferStatus(row: {
  sample: string
  organism: string
  ptms: string
  labelMethod: string
  condition: string
  identifier: string
  confidence: number
}): MetaStatus {
  const filled = [
    row.sample,
    row.organism,
    row.ptms,
    row.labelMethod,
    row.condition,
  ].filter(Boolean).length
  if (filled >= 4 && row.confidence >= 0.55) return "ok"
  if (filled >= 2) return "partial"
  return "partial"
}

export function parseMetaOutput(
  raw: string,
  meta: {
    pmid: string
    title: string
    textSource: MetaTextSource
    fallbackIdentifier?: string
    fallbackMsDataSource?: string
  },
): LiteratureInfoRow {
  const obj = extractJsonObject(raw) as Record<string, unknown>

  let confidence = Number(obj.confidence)
  if (!Number.isFinite(confidence)) confidence = 0.5
  confidence = Math.min(1, Math.max(0, confidence))

  const sample = asStr(obj.sample)
  const sampleType = asStr(obj.sampleType)
  const organism = asStr(obj.organism)
  const ptms = asStr(obj.ptms)
  const labelMethod = asStr(obj.labelMethod)
  const condition = asStr(obj.condition)
  const detailCondition = asStr(obj.detailCondition)
  const enrichmentMethod = asStr(obj.enrichmentMethod)
  const massSpectrometer = asStr(obj.massSpectrometer)
  let msDataSource = asStr(obj.msDataSource) || meta.fallbackMsDataSource || ""
  let identifier = asStr(obj.identifier) || meta.fallbackIdentifier || ""
  const notes = asStr(obj.notes)

  // Soft check: empty core fields with high confidence → clamp
  const coreFilled = CORE_FIELDS.filter((k) => {
    const map: Record<string, string> = {
      sample,
      sampleType,
      organism,
      ptms,
      labelMethod,
      condition,
      detailCondition,
      enrichmentMethod,
      massSpectrometer,
    }
    return Boolean(map[k])
  }).length
  if (coreFilled < 3 && confidence > 0.7) confidence = 0.55

  const status = inferStatus({
    sample,
    organism,
    ptms,
    labelMethod,
    condition,
    identifier,
    confidence,
  })

  return {
    pmid: meta.pmid,
    title: meta.title,
    sample,
    sampleType,
    organism,
    ptms,
    labelMethod,
    condition,
    detailCondition,
    enrichmentMethod,
    massSpectrometer,
    msDataSource,
    identifier,
    status,
    confidence,
    textSource: meta.textSource,
    notes,
    extractedAt: new Date().toISOString(),
  }
}
