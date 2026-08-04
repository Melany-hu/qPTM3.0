/**
 * Classify user uploads for collection jobs.
 */
import { extname } from "node:path"

export type UploadFileKind = "fulltext" | "supplementary" | "unknown"

const FULLTEXT_EXT = new Set([".pdf", ".xml"])
const SUPP_EXT = new Set([".zip", ".xlsx", ".xls", ".csv", ".tsv"])

export function classifyUploadPath(filePath: string): UploadFileKind {
  const ext = extname(filePath).toLowerCase()
  if (FULLTEXT_EXT.has(ext)) return "fulltext"
  if (SUPP_EXT.has(ext)) return "supplementary"
  return "unknown"
}

export function isTabularUpload(filePath: string): boolean {
  return classifyUploadPath(filePath) === "supplementary"
}

export function isFulltextUpload(filePath: string): boolean {
  return classifyUploadPath(filePath) === "fulltext"
}
