export interface ParsedEntities {
    gene?: string;
    uniprot_ac?: string;
    position?: number;
    ptm_type?: string;
    organism?: string;
    pmid?: string;
    mutation_label?: string;
}
export interface InvestigationMemory {
    gene: string | null;
    uniprot_ac: string | null;
    position: number | null;
    ptm_type: string;
    organism: string;
    pmid: string | null;
    mutation_label: string | null;
    query_mode: string | null;
    findings_summary: string;
    entities: ParsedEntities;
}
export declare function emptyMemory(): InvestigationMemory;
export declare function parseEntities(message: string): ParsedEntities;
/** Pull a residue number out of clarification option labels like "S18（小鼠）/ S15（人）". */
export declare function extractPositionFromText(text: string): number | null;
/** Normalize organism / p53-family gene symbols. Does NOT invent a site. */
export declare function normalizeTargetIdentity(memory: InvestigationMemory, contextText?: string): void;
export declare function mergeEntities(memory: InvestigationMemory, parsed: ParsedEntities): void;
export declare function memoryPromptBlock(memory: InvestigationMemory): string;
export declare function addFinding(memory: InvestigationMemory, tool: string, summary: string): void;
