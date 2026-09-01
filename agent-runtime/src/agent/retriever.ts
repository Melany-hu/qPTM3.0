import { InvestigationMemory } from "../context/memory.js";

const TOOL_HINTS: Record<string, string[]> = {
  kinase: ["qptm_kinases", "iptmnet_enzymes", "psp_kinase_substrate", "gps6_kinases", "ekpi_kinases"],
  condition: ["qptm_site_conditions", "qptm_search", "ekpi_quantitative"],
  localization: ["compartments_localization", "inuloc_nls_nes", "uniprot_annotation", "interpro_domains"],
  function: ["psp_regulatory", "ptm_stability", "ptmd_disease", "funcscore_phosphosite", "reactome_pathways"],
  disease: ["ptmd_disease", "psp_disease_sites", "activedriver_mutations", "cancerproteome_disease"],
  drug: ["pmads_drug_ptm", "drugbank_targets", "decryptm_drug_ptm"],
  ppi: ["string_ppi", "iptmnet_ptm_ppi", "ptmint_ppi"],
  llps: ["ptmphase_llps", "dscope_predictions"],
  pathway: ["reactome_pathways", "kegg_pathways", "pathbank_pathways"],
  literature: ["pubtator_literature_search"],
};

const KEYWORDS: Record<string, RegExp> = {
  kinase: /\b(kinase|激酶|磷酸化|phosphorylat|upstream|enzyme)\b/i,
  condition: /\b(condition|fold|log2|定量|条件|倍数|treatment|dynamics)\b/i,
  localization: /\b(locali|定位|compartment|domain|结构域|nls|nes)\b/i,
  function: /\b(function|功能|mechanism|机制|role|stability|意义)\b/i,
  disease: /\b(disease|cancer|疾病|肿瘤|mutation|突变)\b/i,
  drug: /\b(drug|药物| inhibitor|therapy)\b/i,
  ppi: /\b(ppi|interact|互作|binding partner)\b/i,
  llps: /\b(llps|phase separation|相分离)\b/i,
  pathway: /\b(pathway|通路|signaling|信号)\b/i,
  literature: /\b(literature|paper|pubmed|文献|论文)\b/i,
};

export function retrieveTools(question: string, memory: InvestigationMemory, topK = 6): string[] {
  const scores: Record<string, number> = {};
  for (const [dim, re] of Object.entries(KEYWORDS)) {
    if (re.test(question)) scores[dim] = (scores[dim] || 0) + 2;
  }
  if (memory.position) scores.kinase = (scores.kinase || 0) + 1;
  if (memory.gene && !memory.position) scores.condition = (scores.condition || 0) + 1;

  const picked: string[] = ["qptm_search", "uniprot_annotation"];
  const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1]);

  for (const [dim] of ranked) {
    for (const t of TOOL_HINTS[dim] || []) {
      if (!picked.includes(t)) picked.push(t);
    }
  }

  if (!ranked.length) {
    picked.push("qptm_kinases", "qptm_site_conditions", "psp_regulatory");
  }

  return picked.slice(0, topK);
}

export function retrieveToolsDeep(question: string, memory: InvestigationMemory): string[] {
  const all = new Set<string>();
  for (const tools of Object.values(TOOL_HINTS)) {
    for (const t of tools) all.add(t);
  }
  const base = retrieveTools(question, memory, 10);
  for (const t of base) all.add(t);
  return [...all].slice(0, 16);
}
