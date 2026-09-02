import { InvestigationMemory } from "./memory.js";
import { ArtifactStore } from "./artifacts.js";
import type { Citation } from "../agent/citations.js";
export interface SessionState {
    sessionId: string;
    memory: InvestigationMemory;
    artifacts: ArtifactStore;
    citations: Citation[];
    pendingClarification: Record<string, unknown> | null;
    /** How many clarification rounds already completed in this deep-research thread. */
    clarifyRound: number;
    /** Accumulated question + clarification answers for multi-round clarify. */
    deepResearchBrief: string | null;
    lastMode: "qa" | "deep_research";
    turnCount: number;
}
export declare function getOrCreateSession(sessionId: string): SessionState;
export declare function resetSession(sessionId: string): void;
