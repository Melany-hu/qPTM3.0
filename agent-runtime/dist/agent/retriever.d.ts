import { InvestigationMemory } from "../context/memory.js";
export declare function retrieveTools(question: string, memory: InvestigationMemory, topK?: number): string[];
export declare function retrieveToolsDeep(question: string, memory: InvestigationMemory): string[];
