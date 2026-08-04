/**
 * Register user-uploaded supplementary ZIP as a Stage 4/5 job.
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { rebuildStage4Outputs, type SuppScoutRecord } from "../pipeline/stage4-supp.js"
import type { ZipFileHit } from "../stage4/supp-scout.js"
import { stage4SuppDir, stage4SuppScoutJsonlPath, toPortablePath } from "../utils/io.js"

function loadAllScoutRecords(): SuppScoutRecord[] {
  const path = stage4SuppScoutJsonlPath()
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

export function registerManualSuppJob(options: {
  pmid: string
  title?: string
  zipHits: ZipFileHit[]
  zipPath: string
  sourceFile?: string
}): SuppScoutRecord {
  const pmid = options.pmid.trim()
  const scoutedAt = new Date().toISOString()
  const topFiles = options.zipHits
    .slice(0, 8)
    .map((h) => `${h.path}[${h.kind};${h.score}]`)
    .join("; ")
  const clues = options.zipHits
    .slice(0, 8)
    .flatMap((h) => h.clues.map((c) => `zip:${c}`))
    .slice(0, 30)
    .join(";")

  const record: SuppScoutRecord = {
    pmid,
    title: options.title ?? "",
    identifier: "",
    doi: null,
    pmcid: null,
    verdict: "likely_qptm_table",
    zipStatus: "ok",
    zipPath: toPortablePath(options.zipPath),
    topFiles,
    clues,
    xmlHitCount: 0,
    zipHitCount: options.zipHits.length,
    notes: `source=user_upload${options.sourceFile ? `; file=${options.sourceFile}` : ""}`,
    scoutedAt,
  }

  const kept = loadAllScoutRecords().filter((r) => r.pmid !== pmid)
  kept.push(record)
  writeFileSync(
    stage4SuppScoutJsonlPath(),
    kept.map((r) => JSON.stringify(r)).join("\n") + (kept.length ? "\n" : ""),
    "utf8",
  )
  rebuildStage4Outputs()
  return record
}

export function hasUserUploadedSupplementary(pmid: string): boolean {
  return existsSync(join(stage4SuppDir(), pmid, "source_user_upload.txt"))
}
