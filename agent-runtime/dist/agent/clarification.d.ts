import { InvestigationMemory } from "../context/memory.js";
import type { AgentEvent } from "../sse.js";
export interface ClarificationPayload {
    needs_clarification: boolean;
    intro?: string;
    fields?: Array<{
        id: string;
        label: string;
        options: string[];
        allow_custom?: boolean;
        placeholder?: string;
    }>;
    free_text?: {
        label: string;
        placeholder: string;
    };
    submit_label?: string;
    skip_label?: string;
}
export declare function buildDeepResearchClarification(message: string): ClarificationPayload;
export declare function mergeClarification(original: string, selections: Record<string, string>, freeText: string): string;
export declare function assessClarificationLlm(message: string, memory: InvestigationMemory): Promise<ClarificationPayload | null>;
export declare function clarificationEvent(payload: ClarificationPayload): AgentEvent;
