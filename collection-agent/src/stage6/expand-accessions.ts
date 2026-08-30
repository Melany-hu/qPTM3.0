/**
 * Expand ProteomeXchange PXD accessions to native repository mirrors (IPX / MSV / …).
 * iProX deposits often advertise only the PXD partner ID in the paper / user query.
 */
import { expandViaProteomeXchange } from "../stage2/clients/proteomexchange.js"
import type { AccessionHit } from "../stage2/accessions.js"
import type { MsRepoKind } from "../types.js"
import { repoFromAccession } from "./accessions.js"

/** Infer preferred MS repository from free-text (chat / resolve-urls message). */
export function inferMsDataSourceFromText(text: string | undefined | null): string {
  const t = (text || "").toLowerCase()
  if (!t.trim()) return ""
  if (/\biprox\b/.test(t)) return "iProX"
  if (/\bjpost\b/.test(t)) return "jPOST"
  if (/\bmassive\b|\bmsv\b/.test(t)) return "MassIVE"
  if (/\bcptac\b|\bpdc\b/.test(t)) return "PDC"
  if (/\bpride\b/.test(t)) return "PRIDE"
  return ""
}

/**
 * For each PXD, look up ProteomeXchange Central and collect native mirrors (IPX…).
 * Returns expanded accession list (IPX first) plus notes for logging.
 */
export async function expandAccessionsForResolve(
  accessions: string[],
  msDataSourceHint = "",
): Promise<{ accessions: string[]; msDataSource: string; notes: string[] }> {
  const input = [
    ...new Set(
      (accessions || []).map((a) => String(a || "").trim().toUpperCase()).filter(Boolean),
    ),
  ]
  const notes: string[] = []
  const hint = (msDataSourceHint || "").trim()
  const preferIprox = /\biprox\b/i.test(hint)

  const pxdIds = input.filter((id) => /^PXD\d+$/i.test(id))
  let mirrors: AccessionHit[] = []
  if (pxdIds.length > 0) {
    try {
      mirrors = await expandViaProteomeXchange(pxdIds)
    } catch (err) {
      notes.push(
        `PX expand failed: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  }

  const uniqueIpx = [
    ...new Set(
      mirrors
        .filter((h) => /^IPX\d+$/i.test(h.id) || h.source === "iProX")
        .map((h) => h.id.toUpperCase()),
    ),
  ]

  if (uniqueIpx.length > 0) {
    notes.push(
      `ProteomeXchange: ${pxdIds.join(", ")} → iProX ${uniqueIpx.join(", ")}`,
    )
    // Prefer native IPX; keep original PXD after (processPaper skips PXD when IPX present)
    const merged = [...uniqueIpx]
    for (const id of input) {
      if (!merged.includes(id)) merged.push(id)
    }
    return {
      accessions: merged,
      msDataSource: preferIprox || uniqueIpx.length > 0 ? "iProX" : hint || "PRIDE",
      notes,
    }
  }

  // No IPX mirror found — keep input; respect user hint when present.
  const sources = [
    ...new Set(input.map((id) => repoFromAccession(id)).filter((r) => r !== "unknown")),
  ] as MsRepoKind[]
  let msDataSource = hint
  if (!msDataSource) {
    msDataSource = sources.length === 1 ? sources[0] : sources.join("; ") || "PRIDE"
  }
  if (preferIprox && pxdIds.length > 0) {
    notes.push(
      `User requested iProX but no IPX mirror found for ${pxdIds.join(", ")} on ProteomeXchange`,
    )
  }
  return { accessions: input, msDataSource, notes }
}
