/**
 * User-facing messages for the interactive collection job (default: English).
 *
 * UI segment markers (<<<…>>>) are stripped before display; the frontend uses
 * them to interleave prose with previews / forms / action buttons.
 */

export const UI_SEG = {
  AFTER_PAPER: "<<<AFTER_PAPER>>>",
  AFTER_META: "<<<AFTER_META>>>",
  AFTER_QRATIO: "<<<AFTER_QRATIO>>>",
  AFTER_ADJUST: "<<<AFTER_ADJUST>>>",
  AFTER_CONTRIBUTE: "<<<AFTER_CONTRIBUTE>>>",
} as const

export function messageRejected(opts: {
  title?: string
  reason?: string
  ptmTypes?: string[]
}): string {
  const title = (opts.title || "").trim()
  const reason = (opts.reason || "").trim()
  const lines = [
    "After screening, this paper does not appear to contain quantitative post-translational modification (PTM) proteomics data, so it cannot enter the qPTM collection pipeline.",
  ]
  if (title) lines.push(`Paper: ${title}`)
  if (reason) lines.push(`Reason: ${reason}`)
  lines.push(
    "",
    "qPTM mainly curates site-level quantitative PTM mass-spectrometry results (Condition, Log2Ratio, etc.).",
    "If you believe this paper does include quantitative PTM tables, try another PMID, or upload a PDF / supplementary file that contains the quant tables.",
    "You can also keep chatting below — I can help you judge whether a paper is suitable for collection.",
  )
  return lines.join("\n")
}

export function messageUncertain(opts: {
  title?: string
  abstract?: string
  reason?: string
  confidence?: number
}): string {
  const conf =
    opts.confidence != null && Number.isFinite(opts.confidence)
      ? ` (confidence ${Math.round(opts.confidence * 100)}%)`
      : ""
  const lines = [
    `Screening is uncertain${conf}: we cannot fully confirm site-level quantitative PTM data.`,
  ]
  if (opts.reason) lines.push(`Note: ${opts.reason}`)
  lines.push(
    "",
    "If you know the paper contains quantitative PTM tables, click Continue to proceed; otherwise try another PMID or upload a clearer supplementary table.",
  )
  return lines.join("\n")
}

export function messageInclude(opts: {
  title?: string
  abstract?: string
  ptmTypes?: string[]
  /** True when PDF/XML is already present (e.g. user upload). */
  hasFulltext?: boolean
}): string {
  const lines = [
    "This paper appears to contain quantitative PTM proteomics data and is suitable for the qPTM collection pipeline.",
  ]
  if (opts.ptmTypes && opts.ptmTypes.length) {
    lines.push(`Detected PTM types: ${opts.ptmTypes.join(", ")}.`)
  }
  lines.push("")
  lines.push(UI_SEG.AFTER_PAPER)
  if (opts.hasFulltext) {
    lines.push(
      "Click Continue to extract experimental information.",
    )
  } else {
    lines.push(
      "Click Continue to fetch the full text (PDF/XML). Next we will extract experimental information.",
    )
  }
  return lines.join("\n")
}

export function messageFulltextMissing(): string {
  return [
    "Open-access full text could not be retrieved automatically.",
    "Common causes: the journal is not OA, publisher blocking, or no usable Unpaywall/PMC link.",
    "",
    "Please upload a PDF or JATS XML for this paper, then click Continue.",
    "After upload we will extract Sample / Condition / PTMs and related metadata.",
  ].join("\n")
}

export function messageFulltextOk(source: "upload" | "oa"): string {
  return source === "upload"
    ? "Full text is ready, then click Continue to extract literature metadata."
    : "Full text retrieved successfully, then click Continue to extract literature metadata."
}

export function messageSuppMissing(): string {
  return [
    "Supplementary quantitative tables could not be downloaded automatically.",
    "Common causes: login-walled supplements, broken links, or tables only in the main text / attached files.",
    "",
    "Please upload a ZIP / Excel / CSV / TSV with site-level quant data, then click Continue.",
    "Ideal columns: UniProt (or gene), PTM site, and ratio / Log2Ratio.",
  ].join("\n")
}

export function messageSuppOk(verdict: string): string {
  return (
    `Supplementary quantitative tables located (${verdict}). ` +
    `You can download the supplementary package below, review the scout details, then click Continue to parse them into the qratio schema.`
  )
}

export function messageParseEmpty(): string {
  return [
    "The supplementary tables were read, but no site-level quantitative PTM ratios were parsed (0 qratio rows).",
    "Review the parse log below, then either:",
    "• Select which file/sheet contains the site-level quant table and click “Use selected tables”, or",
    "• Upload a clearer ZIP / Excel / CSV and try again.",
    "Ideal columns: UniProt (or gene), PTM site, and ratio / Log2Ratio.",
  ].join("\n")
}

export function messageUserSuppReady(): string {
  return "User-uploaded supplementary tables detected, then click Continue to parse quantitative data."
}

export function messageParseOk(rowCount: number, opts?: { proteinFilled?: number }): string {
  const lines = [
    `Quantitative tables parsed: ${rowCount} site-level record(s) written to Quantitative_data.csv.`,
  ]
  if (opts?.proteinFilled && opts.proteinFilled > 0) {
    lines.push(
      `Protein-level Log2Ratio was joined onto ${opts.proteinFilled} site row(s) where UniProt IDs matched.`,
    )
  }
  lines.push(
    "",
    UI_SEG.AFTER_QRATIO,
    "If something looks wrong (missing file, Condition mismatch, empty Log2Ratio (protein)), tell me in chat — e.g. which Excel file/sheet to use — or use “Adjust tables” below to re-parse.",
    "",
    UI_SEG.AFTER_ADJUST,
    "If you are willing, you can contribute these curated results to the qPTM database.",
    "",
    UI_SEG.AFTER_CONTRIBUTE,
    "You can also click Continue to resolve MS repository download URLs (PRIDE / iProX / jPOST).",
  )
  return lines.join("\n")
}

export function messageMsUrlsComplete(opts: {
  rowCount: number
  totalUrls?: number
  statusNote?: string
  offerContribute?: boolean
}): string {
  const lines = ["MS repository download links have been resolved."]
  if (opts.totalUrls != null && Number.isFinite(opts.totalUrls)) {
    lines.push(`Found ${opts.totalUrls} download URL(s) from PRIDE / iProX / jPOST.`)
  }
  if (opts.statusNote) lines.push(opts.statusNote)
  lines.push("")
  lines.push(
    `Collection complete: curated ${opts.rowCount} site-level quantitative record(s).`,
  )
  lines.push("You can download Experimental_info.csv and Quantitative_data.csv below.")
  if (opts.offerContribute !== false && opts.rowCount > 0) {
    lines.push("")
    lines.push(
      "If you are willing, you can contribute these curated results to the qPTM database to help other researchers (see the prompt below).",
    )
  }
  return lines.join("\n")
}

export function messageComplete(rowCount: number): string {
  return [
    `Collection complete: parsed ${rowCount} site-level quantitative record(s).`,
    "You can download Experimental_info.csv and Quantitative_data.csv below.",
    "",
    "If you are willing, you can contribute these curated results to the qPTM database to help other researchers (see the prompt below).",
  ].join("\n")
}

export function messageCompleteNoContribute(rowCount: number): string {
  return `Collection complete: parsed ${rowCount} site-level quantitative record(s). You can download the CSV files below.`
}
