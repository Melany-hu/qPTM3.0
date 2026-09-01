export function emptyMemory() {
    return {
        gene: null,
        uniprot_ac: null,
        position: null,
        ptm_type: "phosphorylation",
        organism: "human",
        pmid: null,
        mutation_label: null,
        query_mode: null,
        findings_summary: "",
        entities: {},
    };
}
const GENE_RE = /\b([A-Z][A-Z0-9]{1,9})\b/g;
const SITE_RE = /\b([STYKR])(\d{2,5})\b/gi;
const UNIPROT_RE = /\b([OPQ][0-9][A-Z0-9]{3}[0-9](?:-\d+)?|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:-\d+)?)\b/i;
const PMID_RE = /\b(?:PMID[:\s#]*)?(\d{7,8})\b/i;
export function parseEntities(message) {
    const out = {};
    const pmidM = PMID_RE.exec(message);
    if (pmidM)
        out.pmid = pmidM[1];
    const uniM = UNIPROT_RE.exec(message);
    if (uniM)
        out.uniprot_ac = uniM[1].toUpperCase();
    const siteM = SITE_RE.exec(message);
    if (siteM) {
        out.position = Number(siteM[2]);
        if (/phosph/i.test(message) || siteM[1].toUpperCase() === "Y" || siteM[1].toUpperCase() === "S" || siteM[1].toUpperCase() === "T") {
            out.ptm_type = "phosphorylation";
        }
    }
    const genes = [...message.matchAll(GENE_RE)].map((m) => m[1]);
    const common = new Set(["DNA", "RNA", "PTM", "WHO", "WHEN", "WHERE", "WHY", "PMID", "HTTP", "HTTPS"]);
    for (const g of genes) {
        if (!common.has(g) && g.length >= 2) {
            out.gene = g;
            break;
        }
    }
    if (/human|人/i.test(message))
        out.organism = "human";
    return out;
}
export function mergeEntities(memory, parsed) {
    memory.entities = { ...memory.entities, ...parsed };
    if (parsed.gene)
        memory.gene = parsed.gene;
    if (parsed.uniprot_ac)
        memory.uniprot_ac = parsed.uniprot_ac;
    if (parsed.position)
        memory.position = parsed.position;
    if (parsed.ptm_type)
        memory.ptm_type = parsed.ptm_type;
    if (parsed.organism)
        memory.organism = parsed.organism;
    if (parsed.pmid)
        memory.pmid = parsed.pmid;
    if (parsed.mutation_label)
        memory.mutation_label = parsed.mutation_label;
}
export function memoryPromptBlock(memory) {
    const parts = [];
    if (memory.gene)
        parts.push(`gene=${memory.gene}`);
    if (memory.uniprot_ac)
        parts.push(`UniProt=${memory.uniprot_ac}`);
    if (memory.position)
        parts.push(`site=${memory.position}`);
    if (memory.ptm_type)
        parts.push(`ptm_type=${memory.ptm_type}`);
    if (memory.pmid)
        parts.push(`PMID=${memory.pmid}`);
    if (memory.findings_summary)
        parts.push(`\nPrior findings:\n${memory.findings_summary}`);
    return parts.length ? parts.join(" · ") : "(no target yet)";
}
export function addFinding(memory, tool, summary) {
    const line = `- [${tool}] ${summary.slice(0, 300)}`;
    if (!memory.findings_summary.includes(line)) {
        memory.findings_summary += memory.findings_summary ? `\n${line}` : line;
    }
}
