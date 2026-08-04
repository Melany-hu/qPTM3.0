import { extractAccessions, mergeAccessions, type AccessionHit } from "./accessions.js"
import { fetchEuropePmcFullTextXml, fetchEuropePmcMeta } from "./clients/europepmc.js"
import { searchPrideByDoi } from "./clients/pride.js"
import { expandViaProteomeXchange } from "./clients/proteomexchange.js"
import { lookupMassiveByAccession, searchMassiveByDoi } from "./clients/massive.js"
import { lookupIprox, lookupJpost } from "./clients/iprox-jpost.js"
import { fetchDoiLandingAccessions } from "./clients/doi-html.js"

export type DiscoverStatus = "found" | "partial" | "not_found" | "error"

export interface Stage2DiscoverInput {
  pmid: string
  title: string
  abstract: string
  stage1Reason?: string
  dataSourceHint?: string
}

export interface Stage2Manifest {
  pmid: string
  title: string
  status: DiscoverStatus
  doi: string | null
  pmcid: string | null
  isOpenAccess: boolean
  repositories: AccessionHit[]
  channelsHit: string[]
  needsPdf: boolean
  notes: string
  discoveredAt: string
  dataSourceHint?: string
  error?: string
}

function uniqueChannels(hits: AccessionHit[]): string[] {
  return [...new Set(hits.flatMap((h) => h.via.split(";")))].sort()
}

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function resolveStatus(hits: AccessionHit[], stepErrors: string[]): DiscoverStatus {
  if (hits.length > 0) return stepErrors.length > 0 ? "partial" : "found"
  if (stepErrors.length > 0) return "error"
  return "not_found"
}

async function safeMerge(
  hits: AccessionHit[],
  stepErrors: string[],
  label: string,
  fn: () => Promise<AccessionHit[]>,
): Promise<AccessionHit[]> {
  try {
    return mergeAccessions(hits, await fn())
  } catch (err) {
    stepErrors.push(`${label}: ${errMsg(err)}`)
    return hits
  }
}

/**
 * Cascaded Stage-2 discovery (no PDF by default):
 * 1) abstract / stage1 reason regex
 * 2) repo reverse lookup (PRIDE by DOI, MassIVE, PX expand, iProX/jPOST validate)
 * 3) Europe PMC full text XML / DOI HTML
 * 4) mark needsPdf if still empty
 *
 * Each network step is isolated — partial hits from earlier steps are never discarded.
 */
export async function discoverForPmid(input: Stage2DiscoverInput): Promise<Stage2Manifest> {
  const discoveredAt = new Date().toISOString()
  const base = {
    pmid: input.pmid,
    title: input.title,
    dataSourceHint: input.dataSourceHint,
    discoveredAt,
  }
  const stepErrors: string[] = []

  // --- 1) abstract / reason (local regex; no network) ---
  let hits = mergeAccessions(
    extractAccessions(input.abstract ?? "", "abstract"),
    extractAccessions(input.stage1Reason ?? "", "stage1_reason"),
    extractAccessions(input.title ?? "", "title"),
  )

  // --- Europe PMC meta (DOI / PMCID) ---
  let doi: string | null = null
  let pmcid: string | null = null
  let isOpenAccess = false
  try {
    const meta = await fetchEuropePmcMeta(input.pmid)
    doi = meta.doi
    pmcid = meta.pmcid
    isOpenAccess = meta.isOpenAccess
  } catch (err) {
    stepErrors.push(`europepmc_meta: ${errMsg(err)}`)
  }

  // --- 2) repository reverse lookup ---
  if (doi) {
    hits = await safeMerge(hits, stepErrors, "pride_doi", () => searchPrideByDoi(doi!))
    hits = await safeMerge(hits, stepErrors, "massive_doi", () => searchMassiveByDoi(doi!))
  }

  const expandable = hits.map((h) => h.id).filter((id) => /^(PXD|MSV|PDC)/i.test(id))
  if (expandable.length) {
    hits = await safeMerge(hits, stepErrors, "proteomexchange", () =>
      expandViaProteomeXchange(expandable),
    )
  }

  for (const h of [...hits]) {
    if (h.source === "iProX") {
      hits = await safeMerge(hits, stepErrors, `iprox:${h.id}`, () => lookupIprox(h.id))
    }
    if (h.source === "jPOST") {
      hits = await safeMerge(hits, stepErrors, `jpost:${h.id}`, () => lookupJpost(h.id))
    }
    if (h.source === "MassIVE") {
      hits = await safeMerge(hits, stepErrors, `massive:${h.id}`, () =>
        lookupMassiveByAccession(h.id),
      )
    }
  }

  // --- 3) Europe PMC full text / DOI HTML ---
  if (pmcid) {
    try {
      const xml = await fetchEuropePmcFullTextXml(pmcid)
      if (xml) {
        hits = mergeAccessions(hits, extractAccessions(xml, "europepmc:xml"))
        const more = hits.map((h) => h.id).filter((id) => /^(PXD|MSV|PDC)/i.test(id))
        if (more.length) {
          hits = await safeMerge(hits, stepErrors, "proteomexchange_xml", () =>
            expandViaProteomeXchange(more),
          )
        }
      }
    } catch (err) {
      stepErrors.push(`europepmc_xml: ${errMsg(err)}`)
    }
  }

  if (hits.length === 0 && doi) {
    hits = await safeMerge(hits, stepErrors, "doi_html", () => fetchDoiLandingAccessions(doi!))
    const more = hits.map((h) => h.id).filter((id) => /^(PXD|MSV|PDC)/i.test(id))
    if (more.length) {
      hits = await safeMerge(hits, stepErrors, "proteomexchange_doi", () =>
        expandViaProteomeXchange(more),
      )
    }
  }

  const channelsHit = uniqueChannels(hits)
  const needsPdf = hits.length === 0
  const status = resolveStatus(hits, stepErrors)
  const notes = hits.length
    ? `Found ${hits.length} accession(s) via ${channelsHit.join(", ")}${
        stepErrors.length ? ` (${stepErrors.length} step warning(s))` : ""
      }`
    : stepErrors.length
      ? "Discover failed on all network steps; consider PDF / manual queue"
      : "No repository accession found; consider PDF / manual queue"

  return {
    ...base,
    status,
    doi,
    pmcid,
    isOpenAccess,
    repositories: hits,
    channelsHit,
    needsPdf,
    notes,
    ...(stepErrors.length ? { error: stepErrors.join("; ") } : {}),
  }
}
