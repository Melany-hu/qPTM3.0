/**
 * User-provided hints for which supplementary tables/sheets to parse.
 * Written when auto-detection finds no usable quantitative tables,
 * or when the user intervenes after Stage5 via Teach UI / free-text guidance.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { basename, dirname, join } from "node:path"
import { stage4SuppDir } from "../utils/io.js"

export interface UserTableSelection {
  /** Path inside the supplementary ZIP (or bare filename for single-file uploads). */
  entryPath: string
  /** Sheet name for Excel; omit / empty for csv/tsv. */
  sheetName?: string
}

export interface UserTableHints {
  selections: UserTableSelection[]
  note?: string
  /** Prefer joining / keeping protein-level Log2Ratio columns. */
  preferProteinLog2?: boolean
  /** User-requested contrasts from intensity channels, e.g. log2(P5/P1). */
  derivedRatios?: Array<{
    numerator: string
    denominator: string
    isLog2: boolean
    condition: string
  }>
  updatedAt: string
}

export function userHintsPath(pmid: string): string {
  return join(stage4SuppDir(), pmid.trim(), "user_hints.json")
}

export function loadUserTableHints(pmid: string): UserTableHints | null {
  const path = userHintsPath(pmid)
  if (!existsSync(path)) return null
  try {
    const raw = JSON.parse(readFileSync(path, "utf8")) as UserTableHints
    if (!raw || !Array.isArray(raw.selections)) return null
    return raw
  } catch {
    return null
  }
}

export function saveUserTableHints(
  pmid: string,
  selections: UserTableSelection[],
  note?: string,
  preferProteinLog2?: boolean,
  derivedRatios?: UserTableHints["derivedRatios"],
): UserTableHints {
  const hints: UserTableHints = {
    selections: selections
      .map((s) => ({
        entryPath: String(s.entryPath || "").trim(),
        sheetName: s.sheetName != null ? String(s.sheetName).trim() : undefined,
      }))
      .filter((s) => s.entryPath),
    note: note?.trim() || undefined,
    preferProteinLog2: preferProteinLog2 || undefined,
    derivedRatios: derivedRatios?.length ? derivedRatios : undefined,
    updatedAt: new Date().toISOString(),
  }
  const path = userHintsPath(pmid)
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, JSON.stringify(hints, null, 2) + "\n", "utf8")
  return hints
}

export function selectionKey(entryPath: string, sheetName?: string): string {
  const sheet = (sheetName || "").trim()
  return sheet ? `${entryPath}#${sheet}` : entryPath
}

/** Normalize for fuzzy path / filename matching. */
export function normalizeEntryKey(path: string): string {
  return (path || "").trim().replace(/\\/g, "/").toLowerCase()
}

/** True when hint path equals, ends with, or shares basename with actual ZIP entry. */
export function entryPathMatches(hintPath: string, actualPath: string): boolean {
  const h = normalizeEntryKey(hintPath)
  const a = normalizeEntryKey(actualPath)
  if (!h || !a) return false
  if (h === a) return true
  if (a.endsWith("/" + h) || h.endsWith("/" + a)) return true
  const hb = basename(h)
  const ab = basename(a)
  return Boolean(hb && ab && hb === ab)
}

/** True if this sheet is explicitly selected (or file selected without sheet filter). */
export function isHintedSheet(
  hints: UserTableHints | null | undefined,
  entryPath: string,
  sheetName: string,
): boolean {
  if (!hints?.selections?.length) return false
  for (const s of hints.selections) {
    if (!entryPathMatches(s.entryPath, entryPath)) continue
    if (!s.sheetName || !s.sheetName.trim()) return true
    if (s.sheetName.trim() === sheetName) return true
  }
  return false
}

const TABLE_NAME_RE =
  /([A-Za-z0-9][\w.\-]*(?:\([\w.\- ]+\))?[\w.\-]*\.(?:xlsx|xls|csv|tsv|txt))(?![A-Za-z0-9])/gi

/** Detect protein-level Log2Ratio intent from free text. */
export function noteWantsProteinLog2(note: string | undefined | null): boolean {
  const t = (note || "").toLowerCase()
  if (!t) return false
  if (/log2?\s*ratio\s*\(\s*protein\s*\)/i.test(t)) return true
  if (/protein[-\s_]*(?:level\s+)?(?:log2?\s*)?(?:ratio|fc|fold)/i.test(t)) return true
  if (/蛋白质/.test(note || "") && /(定量|log|ratio|比值)/i.test(t)) return true
  if (/蛋白/.test(note || "") && /(log2?ratio|定量值|定量表)/i.test(t)) return true
  return false
}

/** Pull table filenames mentioned in a note / chat message. */
export function extractTableFilenamesFromText(text: string): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  const t = text || ""
  let m: RegExpExecArray | null
  const re = new RegExp(TABLE_NAME_RE.source, "gi")
  while ((m = re.exec(t))) {
    const name = m[1].trim()
    const key = name.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(name)
  }
  return out
}

/**
 * Extract "file → SheetName" / "sheet Quantified" pairs from free-text guidance.
 * Returns Map<entryOrFile, sheetName>.
 */
export function extractSheetHintsFromText(text: string): Map<string, string> {
  const out = new Map<string, string>()
  const t = text || ""
  // filename → Sheet / filename -> Sheet / filename => Sheet
  const arrowRe =
    /([A-Za-z0-9][\w.\-]*(?:\([\w.\- ]+\))?[\w.\-]*\.(?:xlsx|xls|csv|tsv|txt))\s*(?:→|->|=>|—)\s*["']?([A-Za-z][\w .\-]{0,80}?)["']?(?=\s|$|[,;:]|to\s)/gi
  let m: RegExpExecArray | null
  while ((m = arrowRe.exec(t))) {
    const file = m[1].trim()
    const sheet = m[2].trim().replace(/[.,;:]+$/, "")
    if (file && sheet) out.set(file, sheet)
  }
  // file#SheetName
  const hashRe =
    /([A-Za-z0-9][\w.\-]*(?:\([\w.\- ]+\))?[\w.\-]*\.(?:xlsx|xls|csv|tsv|txt))\s*#\s*([A-Za-z][\w .\-]{0,80})/gi
  while ((m = hashRe.exec(t))) {
    const file = m[1].trim()
    const sheet = m[2].trim().replace(/[.,;:]+$/, "")
    if (file && sheet && !out.has(file)) out.set(file, sheet)
  }
  // sheet "Quantified" / sheet=Quantified (applies to first/only file if one file named)
  const sheetRe = /\bsheets?\s*[=:]\s*["']?([A-Za-z][\w .\-]{0,80}?)["']?(?=\s|$|[,;])/gi
  const genericSheets: string[] = []
  while ((m = sheetRe.exec(t))) {
    genericSheets.push(m[1].trim().replace(/[.,;:]+$/, ""))
  }
  if (genericSheets.length === 1 && out.size === 0) {
    const files = extractTableFilenamesFromText(t)
    if (files.length === 1) out.set(files[0], genericSheets[0])
  }
  return out
}

/**
 * Resolve force-include ZIP entry paths from hint selections + filenames in note,
 * matched against available ZIP entry paths.
 */
export function resolveForceIncludePaths(
  hints: UserTableHints | null | undefined,
  availableEntryPaths: string[],
): string[] {
  if (!availableEntryPaths.length) return []
  const wanted: string[] = []
  const seenWant = new Set<string>()
  const pushWant = (w: string) => {
    const k = normalizeEntryKey(w)
    if (!k || seenWant.has(k)) return
    seenWant.add(k)
    wanted.push(w)
  }
  for (const s of hints?.selections || []) {
    if (s.entryPath) pushWant(s.entryPath)
  }
  for (const name of extractTableFilenamesFromText(hints?.note || "")) {
    pushWant(name)
  }
  if (!wanted.length) return []

  const out: string[] = []
  const seen = new Set<string>()
  for (const w of wanted) {
    for (const actual of availableEntryPaths) {
      if (!entryPathMatches(w, actual)) continue
      const key = normalizeEntryKey(actual)
      if (seen.has(key)) continue
      seen.add(key)
      out.push(actual)
    }
  }
  return out
}
