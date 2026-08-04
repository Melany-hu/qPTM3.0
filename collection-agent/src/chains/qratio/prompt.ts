/**
 * Stage 5 — LLM column mapping prompt.
 */

export const QRATIO_MAP_SYSTEM = `You are a qPTM Stage-5 curator.
Map spreadsheet columns to quantitative PTM site-ratio fields.
Return ONLY a single JSON object (no markdown fences, no commentary).`

export const QRATIO_MAP_RULES = `Target qratio fields:
- UniProtID
- Position (residue number)
- AminoAcid (S/T/Y/K/… single letter when possible)
- Log2Ratio (peptide) — site/peptide-level log2 fold-change (NOT raw intensity)
- P value (peptide)
- Log2Ratio (protein) / P value (protein) — optional

Hard rules (from QC):
1) Prefer site/peptide-level ratio columns over protein-level when both exist.
2) If multiple condition ratios exist, list EACH as a separate ratioColumns entry.
3) valueType must be one of: "log2_ratio" | "fold_change" | "intensity" | "other".
   - intensity / abundance / peak area / bare timepoint channels (e.g. "0/5","5/5") → valueType="intensity" and do NOT put them in ratioColumns.
4) If the sheet ONLY has intensities (no ratio/log2FC/fold-change), set skip=true, intensityOnly=true, and list intensityColumns.
5) If there is NO site-level Position/siteCombined column AND no mod-sequence/probability column from which AA can be inferred (e.g. "Lactylation Probabilities", "Modified sequence"), set skip=true (reason: no_site_level). AminoAcid column is optional — Position alone is enough; AA may be filled from sequence later. When AA is only in a probability column, set modSeqCol and leave aminoAcidCol null.
6) If site is encoded as S123 / T45 / K31 in one column, set siteCombinedCol.
7) If UniProt/accession is missing but Gene name/symbol exists with site+ratio, set geneCol (Stage5 will map gene→UniProt). Prefer uniprotCol when both exist. MaxQuant "Proteins" holding accessions → uniprotCol.
8) Prefer normalized / "nomolized" ratio (H/L) over raw Ratio H/L or 1/ratio inverse when both exist; treat as fold_change (not intensity).
9) SILAC MaxQuant columns named "Ratio H/L …" or "Ratio M/L …" are linear heavy/light ratios (fold_change, isLog2=false), NOT log2FC. When paired genotype columns exist at the same time (e.g. WT_10min vs ARH3ko_10min), the biological contrast is Treatment/Control (e.g. "ARH3ko/WT (10 min)") — not the per-sample H/L channel ratio stored as log2FC.
9) condition labels: map each ratio column to a Stage3 Condition fragment when possible
   (e.g. "EGF 5 min/Ctr"), using Stage3 sample/condition/detailCondition. Do NOT leave meaningless labels like ".1" or bare "M/L" if Stage3 has clearer comparisons.
10) Do NOT invent column names — only use names from the provided headers.
11) confidence: 0–1.

JSON schema:
{
  "skip": boolean,
  "intensityOnly": boolean,
  "confidence": number,
  "reason": string,
  "uniprotCol": string | null,
  "geneCol": string | null,
  "positionCol": string | null,
  "aminoAcidCol": string | null,
  "siteCombinedCol": string | null,
  "modSeqCol": string | null,
  "intensityColumns": string[],
  "ratioColumns": [
    { "column": string, "condition": string, "isLog2": boolean, "level": "peptide" | "protein", "valueType": "log2_ratio" | "fold_change" | "other" }
  ],
  "pValueColumns": [
    { "column": string, "condition": string, "level": "peptide" | "protein" }
  ]
}`

export function buildQratioMapUserPrompt(input: {
  pmid: string
  title: string
  ptms: string
  sample: string
  condition: string
  detailCondition: string
  entryPath: string
  sheetName: string
  headers: string[]
  preview: string[][]
}): string {
  const previewLines = input.preview
    .slice(0, 5)
    .map((r, i) => `row${i + 1}: ${JSON.stringify(r.slice(0, 40))}`)
    .join("\n")

  return `${QRATIO_MAP_RULES}

PMID: ${input.pmid}
Title: ${input.title}
PTMs (Stage3): ${input.ptms || "(unknown)"}
Sample (Stage3): ${input.sample || "(unknown)"}
Conditions (Stage3): ${input.condition || "(unknown)"}
Detail condition (Stage3): ${input.detailCondition || "(unknown)"}
File: ${input.entryPath}
Sheet: ${input.sheetName}

Headers (${input.headers.length}):
${JSON.stringify(input.headers)}

Preview (up to 5 rows, truncated columns):
${previewLines || "(empty)"}
`
}
