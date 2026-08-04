/**
 * PhosphoSitePlus / supplementary tables: "GENE_S5731", "P04637_S15", "1433S_S74__1".
 */

const UNIPROT_ACC_RE =
  /^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-\d+)?$/i

export function isValidUniprotAccession(id: string): boolean {
  return UNIPROT_ACC_RE.test((id || "").trim())
}

export interface PhosphositeCombinedId {
  geneOrAcc: string
  aminoAcid: string
  position: string
  isUniprotAcc: boolean
}

/** Parse PSP-style combined IDs: GENE_A1234, ACC_S15, with optional __multiplicity suffix. */
export function parsePhosphositeCombinedId(raw: string): PhosphositeCombinedId | null {
  let t = (raw || "").trim()
  if (!t) return null
  t = t.replace(/__\d+$/, "")
  const m = t.match(/^([A-Z0-9]+)_([A-Z])(\d{1,5})$/i)
  if (!m) return null
  const geneOrAcc = m[1].toUpperCase()
  const aminoAcid = m[2].toUpperCase()
  const position = m[3]
  if (!/^[ACDEFGHIKLMNPQRSTVWY]$/.test(aminoAcid)) return null
  return {
    geneOrAcc,
    aminoAcid,
    position,
    isUniprotAcc: isValidUniprotAccession(geneOrAcc),
  }
}
