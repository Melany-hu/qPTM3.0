/**
 * Stage 5 — Parse supplementary tables → qratio rows.
 * Default scope: Stage4 verdict=likely_qptm_table.
 */
import {
  appendFileSync,
  createReadStream,
  createWriteStream,
  existsSync,
  readFileSync,
  writeFileSync,
} from "node:fs"
import { createInterface } from "node:readline"
import { join } from "node:path"
import { QratioMapChain } from "../chains/qratio/agent.js"
import type { SuppScoutRecord } from "./stage4-supp.js"
import { createLlmRuntime, type LlmRuntime } from "../runtime.js"
import {
  entryPathMatches,
  extractColumnRoleHints,
  extractSheetHintsFromText,
  isHintedSheet,
  loadUserTableHints,
  noteWantsProteinLog2,
  noteWantsSheetAsSample,
  noteWantsSiteLevelSheet,
  extractProteomeSheetNames,
  resolveForceIncludePaths,
  type UserTableHints,
} from "../stage5/user-hints.js"
import {
  HEURISTIC_HIGH,
  HEURISTIC_MIN_PARSE,
  alignConditionsToStage3,
  applyColumnRoleHints,
  applyProteomeColumnHints,
  heuristicMapSheet,
  mappingIsParsable,
  repairSiteColumnMapping,
  stripIntensityRatioColumns,
  type ColumnMapping,
} from "../stage5/heuristic.js"
import {
  applyDerivedRatiosToMapping,
  parseDerivedRatioSpecs,
  type DerivedRatioSpec,
} from "../stage5/derived-ratio.js"
import {
  dedupeQratioRows,
  parseMappedSheet,
  qratioCsvHeader,
  qratioToCsvLine,
  type QratioCsvOptions,
  type QratioRow,
} from "../stage5/parse-rows.js"
import { sheetsAlignWithStage3Samples } from "../stage5/sample-map.js"
import {
  alignProteomeConditions,
  classifySheetKind,
  enrichSiteRowsWithProteome,
  heuristicMapProteomeSheet,
  parseProteomeSheet,
  type ProteomeRow,
} from "../stage5/proteome.js"
import { collectConditionsFromQratioRows } from "../stage5/sync-stage3-condition.js"
import {
  buildPmidInventory,
  writeInventoryJson,
  type PmidTableInventory,
} from "../stage5/tables.js"
import { listZipEntries } from "../stage4/zip.js"
import type { LiteratureInfoRow, Stage5Result, Stage5Status } from "../types.js"
import {
  csvEscape,
  dedupeCsvFileByPmid,
  loadStage3Results,
  stage4SuppJobsPath,
  stage5Dir,
  stage5IntensityQueuePath,
  stage5InventoryDir,
  stage5ManualQueuePath,
  stage5ParseReportPath,
  stage5QcResultsPath,
  stage5QratioCsvPath,
  stage5QratioSuccessPath,
  stage5ResultsJsonlPath,
  stage5WorkDir,
  resolvePortablePath,
} from "../utils/io.js"

export interface Stage5Options {
  limit?: number
  all?: boolean
  concurrency?: number
  flushEvery?: number
  model?: string
  pmid?: string
  /** Default true: only likely_qptm_table */
  likelyOnly?: boolean
  /** Include has_tabular_supp as well */
  allJobs?: boolean
  resume?: boolean
  strictLlm?: boolean
  onResult?: (row: Stage5Result, index: number, total: number) => void
  onError?: (pmid: string, error: unknown, index: number) => void
  /** Live progress for interactive UI (file / sheet / column decisions). */
  onThinking?: (step: Stage5ThinkingStep) => void
}

export interface Stage5ThinkingStep {
  step:
    | "start"
    | "inventory"
    | "candidates"
    | "sample_from_sheet"
    | "try_sheet"
    | "mapping"
    | "role_hint"
    | "progress"
    | "parsed"
    | "skip"
    | "summary"
  message: string
  entryPath?: string
  sheet?: string
  kind?: string
  mappingSource?: string
  confidence?: number
  columns?: Record<string, unknown>
  rowsAdded?: number
  status?: string
  at?: string
}

export interface Stage5RunSummary {
  modelId: string
  eligible: number
  attempted: number
  saved: number
  skippedDone: number
  byStatus: Record<string, number>
  totalRows: number
  totalProteomeRows: number
}

function mappingColumnsBrief(mapping: ColumnMapping): Record<string, unknown> {
  return {
    uniprotCol: mapping.uniprotCol,
    geneCol: mapping.geneCol,
    positionCol: mapping.positionCol,
    aminoAcidCol: mapping.aminoAcidCol,
    siteCombinedCol: mapping.siteCombinedCol,
    conditionCol: mapping.conditionCol ?? null,
    modSeqCol: mapping.modSeqCol,
    ratioColumns: mapping.ratioColumns.map((r) => ({
      column: r.column,
      condition: r.condition,
      level: r.level,
      valueType: r.valueType,
    })),
    pValueColumns: mapping.pValueColumns.map((p) => ({
      column: p.column,
      condition: p.condition,
    })),
    intensityOnly: Boolean(mapping.intensityOnly),
    notes: mapping.notes,
  }
}

function loadSuppJobs(): SuppScoutRecord[] {
  const path = stage4SuppJobsPath()
  if (!existsSync(path)) return []
  const out: SuppScoutRecord[] = []
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim()
    if (!t) continue
    try {
      out.push(JSON.parse(t) as SuppScoutRecord)
    } catch {
      // skip
    }
  }
  return out
}

function dedupeStage5Results(results: Stage5Result[]): Stage5Result[] {
  const byPmid = new Map<string, Stage5Result>()
  for (const r of results) {
    if (!r.pmid) continue
    const prev = byPmid.get(r.pmid)
    if (!prev || (r.parsedAt ?? "") >= (prev.parsedAt ?? "")) byPmid.set(r.pmid, r)
  }
  return [...byPmid.values()].sort((a, b) => a.pmid.localeCompare(b.pmid))
}

function loadStage5Results(): Stage5Result[] {
  const path = stage5ResultsJsonlPath()
  if (!existsSync(path)) return []
  const out: Stage5Result[] = []
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const t = line.trim()
    if (!t) continue
    try {
      out.push(JSON.parse(t) as Stage5Result)
    } catch {
      // skip
    }
  }
  return dedupeStage5Results(out)
}

/** Rewrite stage5_results.jsonl keeping one row per PMID (latest parsedAt). */
export function compactStage5ResultsJsonl(): number {
  const path = stage5ResultsJsonlPath()
  const deduped = loadStage5Results()
  writeFileSync(
    path,
    deduped.map((r) => JSON.stringify(r)).join("\n") + (deduped.length ? "\n" : ""),
    "utf8",
  )
  return deduped.length
}

export interface Stage5PaperCsvDedupeSummary {
  results: number
  qratioSuccess: { before: number; after: number; removed: number }
  qcResults: { before: number; after: number; removed: number }
  intensityQueue: { before: number; after: number; removed: number }
}

/** Compact jsonl, rebuild derived CSVs, dedupe paper-level exports. */
export function finalizeStage5PaperCsvs(): Stage5PaperCsvDedupeSummary {
  const results = compactStage5ResultsJsonl()
  rebuildStage5Outputs()
  return {
    results,
    qratioSuccess: dedupeCsvFileByPmid(stage5QratioSuccessPath(), {
      preferLatestColumn: "parsedAt",
    }),
    qcResults: dedupeCsvFileByPmid(stage5QcResultsPath()),
    intensityQueue: dedupeCsvFileByPmid(stage5IntensityQueuePath()),
  }
}

function loadDonePmids(): Set<string> {
  return new Set(loadStage5Results().map((r) => r.pmid).filter(Boolean))
}

function appendQratioRows(rows: QratioRow[]): void {
  if (rows.length === 0) return
  const rowsPath = join(stage5Dir(), "qratio_rows.jsonl")
  // Always persist full row objects; CSV columns are chosen when rebuilding.
  const chunk = 2000
  for (let i = 0; i < rows.length; i += chunk) {
    const part = rows.slice(i, i + chunk)
    appendFileSync(rowsPath, part.map((r) => JSON.stringify(r)).join("\n") + "\n", "utf8")
  }
  // Rebuild CSV so Localization probability / PEP appear only when non-empty.
  rebuildQratioCsvFromJsonlSync()
}

/** Sync rebuild of qratio.csv from jsonl with optional Localization/PEP columns. */
function rebuildQratioCsvFromJsonlSync(): number {
  const rowsPath = join(stage5Dir(), "qratio_rows.jsonl")
  const csvPath = stage5QratioCsvPath()
  let includeLocalization = false
  let includePep = false
  let n = 0
  const lines = existsSync(rowsPath)
    ? readFileSync(rowsPath, "utf8").split(/\r?\n/)
    : []
  for (const line of lines) {
    const t = line.trim()
    if (!t) continue
    try {
      const row = JSON.parse(t) as QratioRow
      n++
      if (!includeLocalization && String(row.localization || "").trim()) {
        includeLocalization = true
      }
      if (!includePep && String(row.pep || "").trim()) {
        includePep = true
      }
    } catch {
      // skip
    }
  }
  const opts: QratioCsvOptions = { includeLocalization, includePep }
  const out: string[] = [qratioCsvHeader(opts).join(",")]
  for (const line of lines) {
    const t = line.trim()
    if (!t) continue
    try {
      out.push(qratioToCsvLine(JSON.parse(t) as QratioRow, opts))
    } catch {
      // skip
    }
  }
  writeFileSync(csvPath, out.join("\n") + "\n", "utf8")
  return n
}

/**
 * Drop prior qratio rows + Stage5 result for one PMID before a re-parse
 * (hints / free-text guidance), so append does not duplicate.
 */
export function clearPmidStage5Data(pmid: string): { removedRows: number } {
  const id = (pmid || "").trim()
  if (!id) return { removedRows: 0 }
  const rowsPath = join(stage5Dir(), "qratio_rows.jsonl")
  let removedRows = 0
  if (existsSync(rowsPath)) {
    const kept: string[] = []
    for (const line of readFileSync(rowsPath, "utf8").split("\n")) {
      const t = line.trim()
      if (!t) continue
      try {
        const row = JSON.parse(t) as QratioRow
        if ((row.pmid || "").trim() === id) {
          removedRows++
          continue
        }
        kept.push(t)
      } catch {
        kept.push(t)
      }
    }
    writeFileSync(rowsPath, kept.length ? kept.join("\n") + "\n" : "", "utf8")
  }

  const resultsPath = stage5ResultsJsonlPath()
  if (existsSync(resultsPath)) {
    const kept: string[] = []
    for (const line of readFileSync(resultsPath, "utf8").split("\n")) {
      const t = line.trim()
      if (!t) continue
      try {
        const row = JSON.parse(t) as Stage5Result
        if ((row.pmid || "").trim() === id) continue
        kept.push(t)
      } catch {
        kept.push(t)
      }
    }
    writeFileSync(resultsPath, kept.length ? kept.join("\n") + "\n" : "", "utf8")
  }

  // Rebuild CSV from remaining jsonl (optional Localization/PEP columns as needed).
  if (existsSync(rowsPath) || existsSync(stage5QratioCsvPath())) {
    rebuildQratioCsvFromJsonlSync()
  }
  return { removedRows }
}

/** Stream-rebuild qratio.csv from jsonl (avoids V8 max string length). */
export async function rebuildQratioCsvFromJsonl(): Promise<number> {
  const rowsPath = join(stage5Dir(), "qratio_rows.jsonl")
  const csvPath = stage5QratioCsvPath()

  // Pass 1: decide which optional columns have data (and count rows).
  let includeLocalization = false
  let includePep = false
  let n = 0
  if (existsSync(rowsPath)) {
    const rl = createInterface({ input: createReadStream(rowsPath, { encoding: "utf8" }) })
    for await (const line of rl) {
      const t = line.trim()
      if (!t) continue
      try {
        const row = JSON.parse(t) as QratioRow
        n++
        if (!includeLocalization && String(row.localization || "").trim()) {
          includeLocalization = true
        }
        if (!includePep && String(row.pep || "").trim()) {
          includePep = true
        }
      } catch {
        // skip
      }
    }
  }

  const opts: QratioCsvOptions = { includeLocalization, includePep }
  const out = createWriteStream(csvPath, { encoding: "utf8" })
  out.write(qratioCsvHeader(opts).join(",") + "\n")
  if (existsSync(rowsPath)) {
    const rl = createInterface({ input: createReadStream(rowsPath, { encoding: "utf8" }) })
    for await (const line of rl) {
      const t = line.trim()
      if (!t) continue
      try {
        const row = JSON.parse(t) as QratioRow
        out.write(qratioToCsvLine(row, opts) + "\n")
      } catch {
        // skip
      }
    }
  }
  await new Promise<void>((resolve, reject) => {
    out.end(() => resolve())
    out.on("error", reject)
  })
  return n
}

export function rebuildStage5Outputs(): void {
  stage5Dir()
  const results = loadStage5Results()
  // Do NOT rebuild full qratio.csv here (can exceed V8 string limits).
  // Rows are appended incrementally; use rebuildQratioCsvFromJsonl() for a full rewrite.

  const reportHeader = [
    "PMID",
    "Title",
    "status",
    "confidence",
    "rowCount",
    "proteomeRowCount",
    "sheetsUsed",
    "proteomeSheetsUsed",
    "mappingSource",
    "conditionRefined",
    "notes",
    "parsedAt",
    "error",
  ]
  const reportLines = [reportHeader.join(",")]
  for (const r of results) {
    reportLines.push(
      [
        csvEscape(r.pmid),
        csvEscape(r.title),
        csvEscape(r.status),
        String(r.confidence),
        String(r.rowCount),
        String(r.proteomeRowCount ?? 0),
        csvEscape(r.sheetsUsed),
        csvEscape(r.proteomeSheetsUsed ?? ""),
        csvEscape(r.mappingSource),
        csvEscape(r.conditionRefined ?? ""),
        csvEscape(r.notes),
        csvEscape(r.parsedAt),
        csvEscape(r.error ?? ""),
      ].join(","),
    )
  }
  writeFileSync(stage5ParseReportPath(), reportLines.join("\n") + "\n", "utf8")

  const manual = results.filter(
    (r) =>
      r.status === "manual" ||
      r.status === "error" ||
      r.status === "unavailable" ||
      r.status === "intensity",
  )
  const mHeader = [
    "PMID",
    "Title",
    "status",
    "confidence",
    "rowCount",
    "mappingSource",
    "notes",
    "error",
  ]
  const mLines = [mHeader.join(",")]
  for (const r of manual) {
    mLines.push(
      [
        csvEscape(r.pmid),
        csvEscape(r.title),
        csvEscape(r.status),
        String(r.confidence),
        String(r.rowCount),
        csvEscape(r.mappingSource),
        csvEscape(r.notes),
        csvEscape(r.error ?? ""),
      ].join(","),
    )
  }
  writeFileSync(stage5ManualQueuePath(), mLines.join("\n") + "\n", "utf8")

  // Successfully ingested papers (site-level qratio rows present)
  const success = results
    .filter((r) => r.status === "ok" && (r.rowCount ?? 0) > 0)
    .slice()
    .sort((a, b) => a.pmid.localeCompare(b.pmid))
  const sHeader = [
    "PMID",
    "Title",
    "status",
    "rowCount",
    "proteomeRowCount",
    "sheetsUsed",
    "proteomeSheetsUsed",
    "mappingSource",
    "conditionRefined",
    "parsedAt",
  ]
  const sLines = [sHeader.join(",")]
  for (const r of success) {
    sLines.push(
      [
        csvEscape(r.pmid),
        csvEscape(r.title),
        csvEscape(r.status),
        String(r.rowCount),
        String(r.proteomeRowCount ?? 0),
        csvEscape(r.sheetsUsed),
        csvEscape(r.proteomeSheetsUsed ?? ""),
        csvEscape(r.mappingSource),
        csvEscape(r.conditionRefined ?? ""),
        csvEscape(r.parsedAt),
      ].join(","),
    )
  }
  writeFileSync(stage5QratioSuccessPath(), sLines.join("\n") + "\n", "utf8")
}

function appendStage5Results(rows: Stage5Result[]): void {
  if (rows.length === 0) return
  appendFileSync(
    stage5ResultsJsonlPath(),
    rows.map((r) => JSON.stringify(r)).join("\n") + "\n",
    "utf8",
  )
}

/** Avoid `arr.push(...huge)` which exceeds call-stack limits. */
function pushAll<T>(target: T[], items: T[]): void {
  const chunk = 10_000
  for (let i = 0; i < items.length; i += chunk) {
    const end = Math.min(i + chunk, items.length)
    for (let j = i; j < end; j++) target.push(items[j])
  }
}

function scoreSheetForTry(headers: string[]): number {
  const blob = headers.join(" ").toLowerCase()
  let s = 0
  if (/uniprot|accession|\bipi\b|^protein$/.test(blob) || /\bprotein\b/.test(blob)) s += 3
  if (/phospho_?location|position|phosphosite|residue/.test(blob)) s += 5
  if (/ratio|log2|2log|fold|fc|average/.test(blob)) s += 3
  if (/p-value|pvalue|significance|q-value/.test(blob)) s += 1
  if (/amino|residue/.test(blob)) s += 2
  return s
}

function scoreParseResult(mapping: ColumnMapping, rows: QratioRow[]): number {
  if (rows.length === 0) return -1
  const siteN = rows.filter((r) => r.position).length
  const siteFrac = siteN / rows.length
  return (
    mapping.confidence * 10 +
    siteFrac * 25 +
    (mapping.positionCol || mapping.siteCombinedCol || mapping.aminoAcidCol || mapping.modSeqCol
      ? 5
      : 0) +
    Math.min(Math.log10(rows.length + 1), 4)
  )
}

async function resolveMapping(opts: {
  chain: QratioMapChain | null
  lit: LiteratureInfoRow
  entryPath: string
  sheet: { name: string; headers: string[]; preview: string[][]; headerRowIndex: number }
  /** User curation feedback (Adjust tables free text) to honor when mapping columns. */
  userGuidance?: string
}): Promise<ColumnMapping & { skip?: boolean }> {
  const finish = (m: ColumnMapping & { skip?: boolean }) => {
    const cleaned = stripIntensityRatioColumns(m)
    if (m.skip || cleaned.intensityOnly) {
      return { ...cleaned, skip: true }
    }
    // User column-role note first, then STY+AA layout repair (data-driven) last.
    const roles = extractColumnRoleHints(opts.userGuidance || "")
    const withRoles = applyColumnRoleHints(cleaned, opts.sheet.headers, roles)
    return repairSiteColumnMapping(withRoles, opts.sheet.headers)
  }

  let heuristic = stripIntensityRatioColumns(
    heuristicMapSheet(opts.entryPath, {
      name: opts.sheet.name,
      headers: opts.sheet.headers,
      preview: opts.sheet.preview,
      headerRowIndex: opts.sheet.headerRowIndex,
      dataRowCount: opts.sheet.preview.length,
    }),
  )
  // When the user supplied curation feedback, keep table-native condition labels
  // untouched so the LLM re-map below can honor the feedback (e.g. correcting
  // wrong Stage3 conditions) instead of being forced back onto Stage3 labels.
  if (!opts.userGuidance) {
    heuristic = alignConditionsToStage3(
      heuristic,
      opts.lit.condition,
      opts.lit.detailCondition || "",
    )
  }

  // Intensity-only sheets: do not parse into fake qratio
  if (heuristic.intensityOnly) {
    return { ...heuristic, skip: true }
  }

  // Require site signal for high-confidence short-circuit. Skip the shortcut when
  // the user has provided feedback: their corrections must reach the LLM so the
  // resulting column/condition mapping reflects them.
  if (
    heuristic.confidence >= HEURISTIC_HIGH &&
    mappingIsParsable(heuristic) &&
    !opts.userGuidance
  ) {
    return finish(heuristic)
  }

  if (!opts.chain) {
    return finish(heuristic)
  }

  try {
    const llm = await opts.chain.run({
      pmid: opts.lit.pmid,
      title: opts.lit.title,
      ptms: opts.lit.ptms,
      sample: opts.lit.sample,
      condition: opts.lit.condition,
      detailCondition: opts.lit.detailCondition,
      entryPath: opts.entryPath,
      sheet: {
        name: opts.sheet.name,
        headers: opts.sheet.headers,
        preview: opts.sheet.preview,
        headerRowIndex: opts.sheet.headerRowIndex,
        dataRowCount: opts.sheet.preview.length,
      },
      userGuidance: opts.userGuidance,
    })
    const llmAligned = opts.userGuidance
      ? { ...llm, headerRowIndex: opts.sheet.headerRowIndex }
      : alignConditionsToStage3(
          { ...llm, headerRowIndex: opts.sheet.headerRowIndex },
          opts.lit.condition,
          opts.lit.detailCondition || "",
        )
    const llmMapped: ColumnMapping & { skip: boolean } = {
      ...llmAligned,
      skip: Boolean(llm.skip),
      intensityOnly: Boolean(llm.intensityOnly || llmAligned.intensityOnly),
    }

    if (llmMapped.intensityOnly || (llm.skip && /intensity/i.test(llm.notes))) {
      return {
        ...llmMapped,
        intensityOnly: true,
        skip: true,
        notes: llmMapped.notes || "intensity_only",
      }
    }

    if (llm.skip) {
      if (mappingIsParsable(heuristic) && heuristic.confidence >= HEURISTIC_MIN_PARSE) {
        return finish({
          ...heuristic,
          notes: `${heuristic.notes}; llm-skip-kept-heuristic: ${llm.notes}`.replace(/^; /, ""),
        })
      }
      return {
        ...heuristic,
        notes: `llm-skip: ${llm.notes || heuristic.notes}`,
        confidence: Math.min(heuristic.confidence, 0.3),
        skip: true,
      }
    }

    const mergeLongFormat = (m: ColumnMapping & { skip?: boolean }) => ({
      ...m,
      conditionCol: m.conditionCol || heuristic.conditionCol || null,
      siteCombinedCol: m.siteCombinedCol || heuristic.siteCombinedCol,
    })

    if (mappingIsParsable(llmMapped) && llmMapped.confidence >= heuristic.confidence - 0.05) {
      return finish(mergeLongFormat(llmMapped))
    }
    if (mappingIsParsable(heuristic) && heuristic.confidence >= HEURISTIC_MIN_PARSE) {
      return finish(heuristic)
    }
    if (mappingIsParsable(llmMapped)) return finish(mergeLongFormat(llmMapped))
    return finish(heuristic)
  } catch (err) {
    return finish({
      ...heuristic,
      notes: `${heuristic.notes}; llm-error: ${err instanceof Error ? err.message : String(err)}`,
    })
  }
}

async function processOnePmid(opts: {
  job: SuppScoutRecord
  lit: LiteratureInfoRow | undefined
  chain: QratioMapChain | null
  onThinking?: (step: Stage5ThinkingStep) => void
}): Promise<{
  result: Stage5Result
  rows: QratioRow[]
  proteomeRows: ProteomeRow[]
  inventory: PmidTableInventory | null
}> {
  const { job } = opts
  const think = (step: Omit<Stage5ThinkingStep, "at">) => {
    opts.onThinking?.({ ...step, at: new Date().toISOString() })
  }
  const lit: LiteratureInfoRow =
    opts.lit ??
    ({
      pmid: job.pmid,
      title: job.title,
      sample: "",
      sampleType: "",
      organism: "",
      ptms: "",
      labelMethod: "",
      condition: "",
      detailCondition: "",
      conditionSampleMap: "",
      enrichmentMethod: "",
      massSpectrometer: "",
      msDataSource: "",
      identifier: job.identifier ?? "",
      status: "partial",
      confidence: 0,
      textSource: "none",
      notes: "missing stage3",
      extractedAt: "",
    } satisfies LiteratureInfoRow)

  const parsedAt = new Date().toISOString()
  const emptyResult = (status: Stage5Status, notes: string, error?: string): Stage5Result => ({
    pmid: job.pmid,
    title: lit.title || job.title,
    status,
    confidence: 0,
    rowCount: 0,
    proteomeRowCount: 0,
    sheetsUsed: "",
    proteomeSheetsUsed: "",
    mappingSource: "none",
    notes,
    parsedAt,
    ...(error ? { error } : {}),
  })

  think({
    step: "start",
    message: `Starting quantitative table parse for PMID ${job.pmid} (verdict=${job.verdict}).`,
  })

  const zipPath = job.zipPath ? resolvePortablePath(job.zipPath) : job.zipPath
  if (!zipPath || !existsSync(zipPath) || job.zipStatus !== "ok") {
    think({
      step: "summary",
      message: `No local supplementary ZIP available (zipStatus=${job.zipStatus}).`,
      status: "unavailable",
    })
    return {
      result: emptyResult("unavailable", `no local zip (zipStatus=${job.zipStatus})`),
      rows: [],
      proteomeRows: [],
      inventory: null,
    }
  }

  const workDir = join(stage5WorkDir(), job.pmid)
  const hints: UserTableHints | null = (() => {
    const h = loadUserTableHints(job.pmid)
    if (h && noteWantsProteinLog2(h.note)) h.preferProteinLog2 = true
    return h
  })()

  const derivedSpecs: DerivedRatioSpec[] = (() => {
    if (hints?.derivedRatios?.length) {
      return hints.derivedRatios.map((d) => ({
        numerator: d.numerator,
        denominator: d.denominator,
        isLog2: d.isLog2 !== false,
        condition: d.condition || `${d.numerator}/${d.denominator}`,
      }))
    }
    return parseDerivedRatioSpecs(hints?.note || "")
  })()

  // Attach sheet names from free-text "file → Sheet" when selections lack sheetName
  if (hints?.note && hints.selections?.length) {
    const sheetHints = extractSheetHintsFromText(hints.note)
    if (sheetHints.size) {
      for (const sel of hints.selections) {
        if (sel.sheetName) continue
        for (const [file, sheet] of sheetHints) {
          if (entryPathMatches(file, sel.entryPath)) {
            sel.sheetName = sheet
            break
          }
        }
        if (!sel.sheetName && sheetHints.size === 1) {
          sel.sheetName = [...sheetHints.values()][0]
        }
      }
    }
  }

  let inventory: PmidTableInventory
  try {
    const allTablePaths = listZipEntries(zipPath)
      .filter((e) => /\.(xlsx|xls|csv|tsv|txt)$/i.test(e.path))
      .map((e) => e.path)
    const forcePaths = resolveForceIncludePaths(hints, allTablePaths)
    if (forcePaths.length) {
      think({
        step: "inventory",
        message: `Force-including user-hinted table file(s): ${forcePaths.join("; ")}.`,
      })
    }
    inventory = buildPmidInventory(job.pmid, zipPath, workDir, forcePaths)
  } catch (err) {
    think({
      step: "summary",
      message: `Inventory failed: ${err instanceof Error ? err.message : String(err)}`,
      status: "error",
    })
    return {
      result: emptyResult(
        "error",
        "inventory failed",
        err instanceof Error ? err.message : String(err),
      ),
      rows: [],
      proteomeRows: [],
      inventory: null,
    }
  }

  writeInventoryJson(join(stage5InventoryDir(), `${job.pmid}.json`), inventory)

  const fileNames = inventory.files.map((f) => f.entryPath)
  think({
    step: "inventory",
    message:
      inventory.files.length === 0
        ? "Scanned the ZIP: no tabular files (.xlsx/.xls/.csv/.tsv) were found."
        : `Identified ${inventory.files.length} candidate tabular file(s): ${fileNames.slice(0, 8).join("; ")}${fileNames.length > 8 ? "…" : ""}.`,
  })

  if (inventory.files.length === 0) {
    return {
      result: emptyResult("manual", "no tabular files in zip"),
      rows: [],
      proteomeRows: [],
      inventory,
    }
  }

  if (hints?.selections?.length || hints?.note) {
    think({
      step: "candidates",
      message: `Using user table guidance${hints.selections?.length ? ` (${hints.selections.length} selection(s))` : ""}${hints.note ? `: ${hints.note}` : ""}${hints.preferProteinLog2 ? " [prefer protein Log2Ratio]" : ""}${derivedSpecs.length ? ` [derived ${derivedSpecs.map((d) => (d.isLog2 ? `log2(${d.condition})` : d.condition)).join(", ")}]` : ""}.`,
    })
  }

  type Candidate = {
    entryPath: string
    localPath: string
    sheet: { name: string; headers: string[]; preview: string[][]; headerRowIndex: number }
    score: number
    hinted: boolean
  }
  const candidates: Candidate[] = []
  for (const f of inventory.files) {
    if (!f.localPath || f.error) continue
    for (const sh of f.sheets) {
      if (!sh.headers.length) continue
      candidates.push({
        entryPath: f.entryPath,
        localPath: f.localPath,
        sheet: {
          name: sh.name,
          headers: sh.headers,
          preview: sh.preview,
          headerRowIndex: sh.headerRowIndex ?? 0,
        },
        score: scoreSheetForTry(sh.headers),
        hinted: isHintedSheet(hints, f.entryPath, sh.name),
      })
    }
  }

  // Prefer user-hinted sheets; otherwise prefer site_ptm sheets over proteome/legends.
  // When guidance is protein-Log2Ratio oriented, keep site sheets in the try list too
  // so proteome ratios can still be joined onto site rows.
  if (hints?.selections?.length) {
    const hinted = candidates.filter((c) => c.hinted)
    const rest = candidates.filter((c) => !c.hinted).sort((a, b) => b.score - a.score)
    if (hinted.length > 0) {
      candidates.length = 0
      candidates.push(...hinted.sort((a, b) => b.score - a.score), ...rest)
    } else {
      candidates.sort((a, b) => b.score - a.score)
      think({
        step: "candidates",
        message:
          "User hints did not match any inventoried sheet names; falling back to automatic ranking.",
      })
    }
  } else {
    candidates.sort((a, b) => {
      const ak = classifySheetKind(a.sheet.name, a.sheet.headers)
      const bk = classifySheetKind(b.sheet.name, b.sheet.headers)
      const rank = (k: string) => (k === "site_ptm" ? 0 : k === "proteome" ? 2 : 1)
      const d = rank(ak) - rank(bk)
      if (d !== 0) return d
      return b.score - a.score
    })
  }

  const MAX_SHEETS_TO_TRY = Number.parseInt(process.env.STAGE5_MAX_SHEETS_TRY ?? "40", 10) || 40
  const hintedOnly = candidates.filter((c) => c.hinted)
  const preferProtein = Boolean(hints?.preferProteinLog2 || noteWantsProteinLog2(hints?.note))
  let tryList: typeof candidates
  if (hints?.selections?.length && hintedOnly.length > 0) {
    if (preferProtein) {
      const siteExtras = candidates.filter(
        (c) =>
          !c.hinted &&
          classifySheetKind(c.sheet.name, c.sheet.headers) === "site_ptm",
      )
      const merged: typeof candidates = []
      const seen = new Set<string>()
      for (const c of [...hintedOnly, ...siteExtras, ...candidates]) {
        const key = `${c.entryPath}#${c.sheet.name}`
        if (seen.has(key)) continue
        seen.add(key)
        merged.push(c)
        if (merged.length >= MAX_SHEETS_TO_TRY) break
      }
      tryList = merged
    } else {
      tryList = hintedOnly.slice(0, MAX_SHEETS_TO_TRY)
    }
  } else {
    tryList = candidates.slice(0, MAX_SHEETS_TO_TRY)
  }

  think({
    step: "candidates",
    message: `Will inspect ${tryList.length} sheet(s) (of ${candidates.length} available). Top: ${tryList
      .slice(0, 8)
      .map((c) => `${c.entryPath}#${c.sheet.name}${c.hinted ? "★" : ""}`)
      .join("; ")}${tryList.length > 8 ? "…" : ""}.`,
  })

  const allRows: QratioRow[] = []
  const usedSheets: string[] = []
  const mappingNotes: string[] = []
  let bestConf = 0
  let mappingSource: Stage5Result["mappingSource"] = "none"
  let anyParsable = false
  let sawIntensity = false
  let sawNoSite = false
  let sawPtmNoSite = false
  let tried = 0
  let bestScore = -1

  // Stage3 multi-sample + sheets named like those samples → treat each sheet as Sample
  const sheetSampleAlign = sheetsAlignWithStage3Samples(
    candidates.map((c) => c.sheet.name),
    lit.sample || "",
  )
  const preferSheetAsSample =
    noteWantsSheetAsSample(hints?.note) || sheetSampleAlign.aligned
  if (sheetSampleAlign.aligned) {
    think({
      step: "sample_from_sheet",
      message: `Stage3 lists ${sheetSampleAlign.matchedSamples.length} Sample(s) that match sheet names (${sheetSampleAlign.matchedSheets.join(", ")}); assigning Sample from each sheet.`,
    })
    mappingNotes.push(
      `sheet_as_sample:${sheetSampleAlign.matchedSheets.join("|")}`,
    )
  }

  for (const c of tryList) {
    tried++
    const kind = classifySheetKind(c.sheet.name, c.sheet.headers)
    think({
      step: "try_sheet",
      message: `Examining ${c.entryPath} → sheet “${c.sheet.name}” (kind=${kind}, headerScore=${c.score}${c.hinted ? ", user-hinted" : ""}). Headers: ${c.sheet.headers.slice(0, 12).join(" | ")}${c.sheet.headers.length > 12 ? " …" : ""}.`,
      entryPath: c.entryPath,
      sheet: c.sheet.name,
      kind,
    })

    if (kind === "ptm_no_site") {
      // Explicitly selected sheets may still be site-level via ModifiedSequence /
      // ProteinAccessions_PTM even when classifySheetKind missed Position.
      if (!c.hinted) {
        sawPtmNoSite = true
        mappingNotes.push(`${c.entryPath}#${c.sheet.name}:ptm_no_site(skip-not-proteome)`)
        think({
          step: "skip",
          message: `Skipped “${c.sheet.name}”: looks like PTM peptide data without site-level Position columns.`,
          entryPath: c.entryPath,
          sheet: c.sheet.name,
          kind,
          status: "ptm_no_site",
        })
        continue
      }
      think({
        step: "try_sheet",
        message: `User-selected “${c.sheet.name}” classified as ptm_no_site; parsing anyway (site may come from ModifiedSequence / accession+site columns).`,
        entryPath: c.entryPath,
        sheet: c.sheet.name,
        kind,
        status: "force_parse_hinted_ptm_no_site",
      })
    }
    if (kind === "proteome") {
      // User Teach note can override proteome misclassification (e.g. combined
      // Protein+Phosphosite columns that look like proteome without Position).
      // Only force when this sheet actually has the named split/site column —
      // don't treat TotalProteins as site-level just because another sheet has mod_sites.
      const roleHints = extractColumnRoleHints(hints?.note || "")
      const hintedSiteCol = roleHints.siteCombinedCol
      const sheetHasHintedSite =
        Boolean(hintedSiteCol) &&
        c.sheet.headers.some(
          (h) => (h || "").toLowerCase() === String(hintedSiteCol).toLowerCase(),
        )
      const forceSite =
        sheetHasHintedSite ||
        (noteWantsSiteLevelSheet(hints?.note) &&
          (c.hinted ||
            c.sheet.headers.some((h) =>
              /mod[_\s.-]?sites?|phosphosite|feature[_\s-]?names?|protein\s*\+\s*phospho|glcnac\s*site|o\s*[- ]?glcnac\s*site|\w+\s+site$/i.test(
                h || "",
              ),
            )))
      if (!forceSite) {
        mappingNotes.push(`${c.entryPath}#${c.sheet.name}:proteome(defer)`)
        think({
          step: "skip",
          message: `Deferred “${c.sheet.name}” as whole-proteome (will try later for protein-level ratios only).`,
          entryPath: c.entryPath,
          sheet: c.sheet.name,
          kind,
          status: "proteome_defer",
        })
        continue
      }
      think({
        step: "try_sheet",
        message: `User guidance marks “${c.sheet.name}” as site-level; parsing as site PTM instead of proteome.`,
        entryPath: c.entryPath,
        sheet: c.sheet.name,
        kind: "site_ptm",
        status: "force_site_from_hint",
      })
    }

    const mapping = await resolveMapping({
      chain: opts.chain,
      lit,
      entryPath: c.entryPath,
      sheet: c.sheet,
      userGuidance: hints?.note || undefined,
    })

    if (hints?.note) {
      const roles = extractColumnRoleHints(hints.note)
      if (roles.siteCombinedCol || roles.uniprotCol || roles.positionCol || roles.aminoAcidCol) {
        const bits = [
          roles.siteCombinedCol ? `split column “${roles.siteCombinedCol}”` : "",
          roles.uniprotCol ? `UniProt=${roles.uniprotCol}` : "",
          roles.geneCol ? `Gene=${roles.geneCol}` : "",
          roles.positionCol ? `Position=${roles.positionCol}` : "",
          roles.aminoAcidCol ? `AA=${roles.aminoAcidCol}` : "",
        ].filter(Boolean)
        if (bits.length) {
          think({
            step: "role_hint",
            message: `Understood your column guidance: ${bits.join("; ")}.`,
            entryPath: c.entryPath,
            sheet: c.sheet.name,
          })
        }
      }
    }
    let effectiveMapping = mapping
    if (derivedSpecs.length > 0) {
      effectiveMapping = applyDerivedRatiosToMapping(mapping, c.sheet.headers, derivedSpecs)
      if (effectiveMapping.derivedContrasts?.length) {
        think({
          step: "mapping",
          message: `Applied user-derived contrasts on “${c.sheet.name}”: ${effectiveMapping.derivedContrasts
            .map(
              (d) =>
                `${d.isLog2 ? "log2" : "fc"}(${d.numeratorCol} / ${d.denominatorCol}) → ${d.condition}`,
            )
            .join("; ")}.`,
          entryPath: c.entryPath,
          sheet: c.sheet.name,
        })
      }
    }
    // Honor user-named protein-level columns even if the LLM dropped them.
    effectiveMapping = applyProteomeColumnHints(effectiveMapping, c.sheet.headers, hints)
    bestConf = Math.max(bestConf, effectiveMapping.confidence)
    mappingNotes.push(
      `${c.entryPath}#${c.sheet.name}:${effectiveMapping.source}@${effectiveMapping.confidence.toFixed(2)}${effectiveMapping.notes ? `(${effectiveMapping.notes})` : ""}`,
    )

    const colBrief = mappingColumnsBrief(effectiveMapping)
    think({
      step: "mapping",
      message: `Mapped columns for “${c.sheet.name}” via ${effectiveMapping.source} (confidence ${effectiveMapping.confidence.toFixed(2)}): ID=${effectiveMapping.uniprotCol || effectiveMapping.geneCol || (effectiveMapping.siteCombinedCol ? `${effectiveMapping.siteCombinedCol} (split)` : "—")}, Position=${effectiveMapping.positionCol || (effectiveMapping.siteCombinedCol ? `${effectiveMapping.siteCombinedCol} (split)` : "—")}, AA=${effectiveMapping.aminoAcidCol || effectiveMapping.modSeqCol || (effectiveMapping.siteCombinedCol ? "from split" : "—")}, ratios=[${effectiveMapping.ratioColumns.map((r) => r.column).slice(0, 6).join(", ") || "—"}]${effectiveMapping.derivedContrasts?.length ? `, derived=[${effectiveMapping.derivedContrasts.map((d) => d.condition).join(", ")}]` : ""}${effectiveMapping.notes ? `. Notes: ${effectiveMapping.notes}` : ""}.`,
      entryPath: c.entryPath,
      sheet: c.sheet.name,
      kind,
      mappingSource: effectiveMapping.source,
      confidence: effectiveMapping.confidence,
      columns: colBrief,
    })

    if (
      (effectiveMapping.intensityOnly || /intensity_only/i.test(effectiveMapping.notes)) &&
      !(effectiveMapping.derivedContrasts && effectiveMapping.derivedContrasts.length > 0)
    ) {
      sawIntensity = true
      think({
        step: "skip",
        message: `Skipped “${c.sheet.name}”: intensity/abundance only (no ratio / Log2FC).`,
        entryPath: c.entryPath,
        sheet: c.sheet.name,
        status: "intensity_only",
      })
      continue
    }
    if (/no_site_level/i.test(effectiveMapping.notes) && !mappingIsParsable(effectiveMapping)) {
      sawNoSite = true
    }

    if (!mappingIsParsable(effectiveMapping)) {
      think({
        step: "skip",
        message: `Skipped “${c.sheet.name}”: mapping not parsable as site-level quantitative PTM (need ID + site + ratio; a split UniProt_AA### column counts as both ID and site).`,
        entryPath: c.entryPath,
        sheet: c.sheet.name,
        status: "not_parsable",
      })
      continue
    }
    anyParsable = true

    const rows = await parseMappedSheet({
      localPath: c.localPath,
      mapping: effectiveMapping,
      lit,
      fallbackCondition: lit.condition,
      preferSheetAsSample,
      onProgress: (message) => {
        think({
          step: "progress",
          message,
          entryPath: c.entryPath,
          sheet: c.sheet.name,
        })
      },
    })
    if (rows.length === 0) {
      think({
        step: "skip",
        message: `Mapped “${c.sheet.name}” but extracted 0 data rows.`,
        entryPath: c.entryPath,
        sheet: c.sheet.name,
        status: "empty_rows",
        rowsAdded: 0,
      })
      continue
    }

    const score = scoreParseResult(effectiveMapping, rows)
    pushAll(allRows, rows)
    usedSheets.push(`${c.entryPath}#${c.sheet.name}`)
    if (score > bestScore) {
      bestScore = score
      mappingSource = effectiveMapping.source
    }
    think({
      step: "parsed",
      message: `Extracted ${rows.length} site-level row(s) from “${c.sheet.name}” (running total ${allRows.length}).`,
      entryPath: c.entryPath,
      sheet: c.sheet.name,
      mappingSource: mapping.source,
      confidence: mapping.confidence,
      rowsAdded: rows.length,
      columns: colBrief,
    })

    // Soft cap only — keep parsing remaining PTM sheets when possible.
    if (allRows.length >= 500_000) break
  }

  // Whole-proteome pass — never accepts ptm_no_site / site_ptm sheets
  const proteomeRows: ProteomeRow[] = []
  const proteomeSheets: string[] = []
  const forceProteomeSheets = new Set(
    extractProteomeSheetNames(hints?.note).map((s) => s.toLowerCase()),
  )
  // When user asks for protein Log2Ratio, also try common short proteome sheet titles
  if (preferProtein || forceProteomeSheets.size > 0) {
    for (const name of ["pro", "prot", "protein", "proteome"]) {
      forceProteomeSheets.add(name)
    }
  }
  const roleHints = extractColumnRoleHints(hints?.note || "")
  for (const f of inventory.files) {
    if (!f.localPath || f.error) continue
    for (const sh of f.sheets) {
      if (!sh.headers.length) continue
      const kind = classifySheetKind(sh.name, sh.headers)
      if (kind === "ptm_no_site") {
        sawPtmNoSite = true
        continue
      }
      if (kind === "site_ptm") continue
      const forceThis = forceProteomeSheets.has(sh.name.toLowerCase())
      if (kind !== "proteome" && !forceThis) continue
      if (f.size > 8_000_000) {
        mappingNotes.push(`${f.entryPath}#${sh.name}:skip_proteome_large_file`)
        continue
      }
      let mapping = heuristicMapProteomeSheet(
        f.entryPath,
        {
          name: sh.name,
          headers: sh.headers,
          headerRowIndex: sh.headerRowIndex ?? 0,
        },
        { force: kind !== "proteome" },
      )
      if (!mapping) continue
      // Apply UniProt column role hint (e.g. PG.ProteinGroups is UniProtID)
      if (roleHints.uniprotCol) {
        const want = roleHints.uniprotCol.toLowerCase().replace(/[\s_]+/g, " ").trim()
        const hit =
          sh.headers.find((h) => h.toLowerCase().replace(/[\s_]+/g, " ").trim() === want) ||
          sh.headers.find((h) => {
            const n = h.toLowerCase().replace(/[\s_]+/g, " ").trim()
            return want.length >= 5 && (n.includes(want) || want.includes(n))
          })
        if (hit) {
          mapping = {
            ...mapping,
            uniprotCol: hit,
            notes: `${mapping.notes}; role_hint:uniprot=${hit}`,
          }
        }
      }
      mapping = alignProteomeConditions(mapping, lit.condition, lit.detailCondition || "")
      const rows = await parseProteomeSheet({
        localPath: f.localPath,
        mapping,
        lit,
        fallbackCondition: lit.condition,
        preferSheetAsSample,
        forceProteome: kind !== "proteome",
      })
      if (rows.length === 0) continue
      pushAll(proteomeRows, rows)
      proteomeSheets.push(`${f.entryPath}#${sh.name}`)
      mappingNotes.push(
        `${f.entryPath}#${sh.name}:proteome@${mapping.confidence.toFixed(2)}(${mapping.notes};rows=${rows.length})`,
      )
      think({
        step: "parsed",
        message: `Extracted ${rows.length} protein-level row(s) from “${sh.name}” for Log2Ratio (protein).`,
        entryPath: f.entryPath,
        sheet: sh.name,
        rowsAdded: rows.length,
        status: "proteome",
      })
      bestConf = Math.max(bestConf, mapping.confidence)
      if (proteomeRows.length >= 50_000) break
    }
    if (proteomeRows.length >= 50_000) break
  }

  const MAX_ROWS_PER_PMID = Number.parseInt(process.env.STAGE5_MAX_ROWS_PER_PMID ?? "600000", 10) || 600_000
  const minSiteRatioRows = Math.max(
    1,
    Number.parseInt(process.env.STAGE5_MIN_SITE_RATIO_ROWS ?? "1", 10) || 1,
  )
  const siteRatioFrac = Number.parseFloat(process.env.STAGE5_SITE_RATIO_MIN_FRAC ?? "0")
  // One quantitative record per site per sample per condition — collapse
  // duplicate rows emitted when several ratio columns were mapped onto the
  // same condition (protein-level fields are merged, not dropped).
  if (allRows.length > 0) {
    const before = allRows.length
    const deduped = dedupeQratioRows(allRows)
    allRows.length = 0
    pushAll(allRows, deduped)
    if (deduped.length < before) {
      mappingNotes.push(`dedupe_site_rows:${before}->${deduped.length}`)
    }
  }
  if (allRows.length > MAX_ROWS_PER_PMID) {
    mappingNotes.push(`truncated_rows:${allRows.length}->${MAX_ROWS_PER_PMID}`)
    allRows.length = MAX_ROWS_PER_PMID
  }
  if (proteomeRows.length > MAX_ROWS_PER_PMID) {
    mappingNotes.push(`truncated_proteome:${proteomeRows.length}->${MAX_ROWS_PER_PMID}`)
    proteomeRows.length = MAX_ROWS_PER_PMID
  }

  let status: Stage5Status
  if (allRows.length > 0) {
    const siteRatioRows = allRows.filter(
      (r) =>
        r.position &&
        (r.log2RatioPeptide || r.log2RatioProtein),
    )
    status =
      siteRatioRows.length >= minSiteRatioRows &&
      (siteRatioFrac <= 0 ||
        siteRatioRows.length >= Math.max(minSiteRatioRows, Math.floor(allRows.length * siteRatioFrac)))
        ? "ok"
        : "manual"
    if (status === "manual") {
      mappingNotes.push("failed_qc_gate:need_site+ratio")
    }
  } else if (proteomeRows.length > 0) {
    // Whole-proteome alone is not enough — never emit protein-only rows into qratio
    status = sawIntensity ? "intensity" : "manual"
    mappingNotes.push(`proteome_without_sites:${proteomeRows.length}(ignored)`)
  } else if (sawIntensity && !anyParsable) {
    status = "intensity"
    mappingNotes.push("intensity_queue_candidate")
  } else if (sawPtmNoSite && !anyParsable) {
    status = "manual"
    mappingNotes.push("ptm_no_site(not_proteome)")
  } else if (sawNoSite && !anyParsable) {
    status = "manual"
    mappingNotes.push("no_site_level")
  } else if (!anyParsable || bestConf < HEURISTIC_MIN_PARSE) {
    status = "manual"
  } else {
    status = "manual"
  }

  if (proteomeRows.length > 0) {
    mappingNotes.push(`protein_qratio_rows=${proteomeRows.length}`)
  }

  // Join proteome Log2Ratio/P into site qratio rows (UniProt match); drop proteome-only proteins
  let proteomeFilled = 0
  if (allRows.length > 0 && proteomeRows.length > 0) {
    const join = enrichSiteRowsWithProteome(allRows, proteomeRows)
    proteomeFilled = join.filled
    mappingNotes.push(
      `protein_cols_filled=${join.filled};matched_proteins=${join.matchedProteins}`,
    )
    think({
      step: "summary",
      message: `Joined protein-level Log2Ratio onto site rows: filled ${join.filled} row(s) across ${join.matchedProteins} UniProt ID(s) from ${proteomeRows.length} proteome row(s).`,
      rowsAdded: join.filled,
    })
  } else if (proteomeRows.length > 0 && allRows.length === 0) {
    think({
      step: "summary",
      message: `Parsed ${proteomeRows.length} protein-level ratio row(s), but qPTM stores site-level records — protein-only tables cannot become Quantitative_data rows without a matching site table.`,
      status: "manual",
    })
  }

  writeInventoryJson(join(stage5InventoryDir(), `${job.pmid}.json`), {
    ...inventory,
    ...( {
      mappingAttempt: mappingNotes,
      sheetsUsed: usedSheets,
      proteomeSheetsUsed: proteomeSheets,
      status,
      rowCount: allRows.length,
      proteomeRowCount: proteomeFilled,
    } as object),
  } as PmidTableInventory)

  think({
    step: "summary",
    message:
      allRows.length > 0
        ? `Finished: status=${status}, extracted ${allRows.length} site-level row(s) from ${usedSheets.length} sheet(s): ${usedSheets.join("; ") || "—"}. Tried ${tried} candidate sheet(s).`
        : `Finished: status=${status}, 0 site-level quantitative rows. Tried ${tried} sheet(s). ${usedSheets.length ? `Used: ${usedSheets.join("; ")}.` : "No sheet produced parsable site+ratio rows."}`,
    status,
    rowsAdded: allRows.length,
  })

  return {
    result: {
      pmid: job.pmid,
      title: lit.title || job.title,
      status,
      confidence: bestConf,
      rowCount: allRows.length,
      proteomeRowCount: proteomeFilled,
      sheetsUsed: usedSheets.join("; "),
      proteomeSheetsUsed: proteomeSheets.join("; "),
      mappingSource,
      conditionRefined:
        allRows.length > 0 ? collectConditionsFromQratioRows(allRows).join("; ") : "",
      notes: mappingNotes.slice(0, 6).join(" | ") || `tried=${tried}`,
      parsedAt,
    },
    rows: allRows,
    proteomeRows: [],
    inventory,
  }
}

async function mapPool<T, R>(
  items: T[],
  concurrency: number,
  fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const out: R[] = new Array(items.length)
  let next = 0
  async function worker() {
    while (true) {
      const i = next++
      if (i >= items.length) return
      out[i] = await fn(items[i], i)
    }
  }
  const n = Math.max(1, Math.min(concurrency, items.length || 1))
  await Promise.all(Array.from({ length: n }, () => worker()))
  return out
}

export async function runStage5Parse(options: Stage5Options = {}): Promise<Stage5RunSummary> {
  const likelyOnly = options.allJobs ? false : options.likelyOnly !== false
  const resume = options.resume !== false
  const concurrency = options.concurrency ?? 2
  const flushEvery = options.flushEvery ?? 5

  stage5Dir()
  const jobsAll = loadSuppJobs()
  let jobs = jobsAll.filter((j) => {
    if (options.pmid) return j.pmid === options.pmid
    if (likelyOnly) return j.verdict === "likely_qptm_table"
    return j.verdict === "likely_qptm_table" || j.verdict === "has_tabular_supp"
  })

  const done = resume && !options.pmid ? loadDonePmids() : new Set<string>()
  const skippedDone = jobs.filter((j) => done.has(j.pmid)).length
  jobs = jobs.filter((j) => !done.has(j.pmid))

  if (!options.all && !options.pmid) {
    const limit = options.limit ?? 20
    jobs = jobs.slice(0, limit)
  }

  const litByPmid = new Map(loadStage3Results().map((r) => [r.pmid, r]))

  let runtime: LlmRuntime | null = null
  let chain: QratioMapChain | null = null
  let modelId = "none"
  try {
    runtime = await createLlmRuntime({ model: options.model })
    chain = new QratioMapChain(runtime)
    modelId = runtime.modelId
  } catch (err) {
    if (options.strictLlm) {
      throw err
    }
    modelId = `heuristic-only:${err instanceof Error ? err.message : String(err)}`
    console.error(`  stage5 warning: LLM unavailable, using heuristic-only (${modelId})`)
  }

  const byStatus: Record<string, number> = {}
  let saved = 0
  let totalRows = 0
  const pending: Stage5Result[] = []
  const pendingRows: QratioRow[] = []
  let totalProteomeRows = 0

  const flush = () => {
    if (pending.length === 0) return
    const flushedResults = pending.splice(0, pending.length)
    const flushedRows = pendingRows.splice(0, pendingRows.length)
    appendStage5Results(flushedResults)
    appendQratioRows(flushedRows)
    try {
      rebuildStage5Outputs()
    } catch (err) {
      console.error(
        `  stage5 rebuild warning: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  }

  await mapPool(jobs, concurrency, async (job, index) => {
    try {
      // Single-PMID / hint-driven re-parse must replace prior rows, not append duplicates.
      if (options.pmid || loadUserTableHints(job.pmid)) {
        clearPmidStage5Data(job.pmid)
      }
      const { result, rows } = await processOnePmid({
        job,
        lit: litByPmid.get(job.pmid),
        chain,
        onThinking: options.onThinking,
      })
      pending.push(result)
      pushAll(pendingRows, rows)
      saved++
      totalRows += rows.length
      totalProteomeRows += result.proteomeRowCount ?? 0
      byStatus[result.status] = (byStatus[result.status] ?? 0) + 1
      options.onResult?.(result, index, jobs.length)
      if (pending.length >= flushEvery) flush()
    } catch (err) {
      const result: Stage5Result = {
        pmid: job.pmid,
        title: job.title,
        status: "error",
        confidence: 0,
        rowCount: 0,
        proteomeRowCount: 0,
        sheetsUsed: "",
        proteomeSheetsUsed: "",
        mappingSource: "none",
        notes: "uncaught",
        parsedAt: new Date().toISOString(),
        error: err instanceof Error ? err.message : String(err),
      }
      pending.push(result)
      saved++
      byStatus.error = (byStatus.error ?? 0) + 1
      options.onError?.(job.pmid, err, index)
      options.onResult?.(result, index, jobs.length)
      if (pending.length >= flushEvery) flush()
    }
  })

  flush()
  const dedupe = finalizeStage5PaperCsvs()
  if (
    dedupe.qratioSuccess.removed > 0 ||
    dedupe.qcResults.removed > 0 ||
    dedupe.intensityQueue.removed > 0
  ) {
    console.error(
      `  stage5 dedupe: qratio_success -${dedupe.qratioSuccess.removed}, qc_results -${dedupe.qcResults.removed}, intensity_queue -${dedupe.intensityQueue.removed}`,
    )
  }

  return {
    modelId,
    eligible: jobsAll.filter((j) =>
      likelyOnly
        ? j.verdict === "likely_qptm_table"
        : j.verdict === "likely_qptm_table" || j.verdict === "has_tabular_supp",
    ).length,
    attempted: jobs.length,
    saved,
    skippedDone,
    byStatus,
    totalRows,
    totalProteomeRows,
  }
}

export function stage5OutputPaths() {
  return {
    dir: stage5Dir(),
    results: stage5ResultsJsonlPath(),
    qratio: stage5QratioCsvPath(),
    success: stage5QratioSuccessPath(),
    qcResults: stage5QcResultsPath(),
    intensityQueue: stage5IntensityQueuePath(),
    report: stage5ParseReportPath(),
    manual: stage5ManualQueuePath(),
    inventory: stage5InventoryDir(),
  }
}
