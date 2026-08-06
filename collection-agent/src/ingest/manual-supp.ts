/**
 * Ingest user-uploaded supplementary files into Stage 4 layout.
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { basename, extname, join } from "node:path"
import { packSupplementaryZip } from "../stage4/clients/doi-supp.js"
import { listAndScoreZip } from "../stage4/supp-scout.js"
import { writeBuffer } from "../stage4/zip.js"
import { stage4SuppDir } from "../utils/io.js"
import { registerManualSuppJob } from "./register-supp-job.js"

export interface IngestSuppOptions {
  pmid: string
  filePath: string
}

export interface IngestSuppResult {
  pmid: string
  zipPath: string
  listingPath: string
  fileCount: number
}

export function ingestManualSupplementary(options: IngestSuppOptions): IngestSuppResult {
  const pmid = options.pmid.trim()
  if (!pmid) throw new Error("PMID is required")
  if (!existsSync(options.filePath)) {
    throw new Error(`File not found: ${options.filePath}`)
  }

  const pmidDir = join(stage4SuppDir(), pmid)
  mkdirSync(pmidDir, { recursive: true })
  const localZip = join(pmidDir, "supplementary.zip")
  const listingPath = join(pmidDir, "listing.json")
  const ext = extname(options.filePath).toLowerCase()

  if (ext === ".zip") {
    copyFileSync(options.filePath, localZip)
  } else if (ext === ".xlsx" || ext === ".xls" || ext === ".csv" || ext === ".tsv") {
    const buf = readFileSync(options.filePath)
    packSupplementaryZip(localZip, [
      { filename: basename(options.filePath), buffer: buf },
    ])
    writeFileSync(join(pmidDir, "source_user_upload.txt"), "user_upload", "utf8")
  } else {
    throw new Error(`Unsupported supplementary type: ${ext} (use .zip, .xlsx, .csv, .tsv)`)
  }

  const zipHits = listAndScoreZip(localZip)
  writeFileSync(listingPath, JSON.stringify(zipHits, null, 2), "utf8")

  registerManualSuppJob({
    pmid,
    zipHits,
    zipPath: localZip,
    sourceFile: basename(options.filePath),
  })

  return {
    pmid,
    zipPath: localZip,
    listingPath,
    fileCount: zipHits.length,
  }
}
