import { InvestigationMemory, emptyMemory } from "./memory.js";
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

const sessions = new Map<string, SessionState>();

export function getOrCreateSession(sessionId: string): SessionState {
  let s = sessions.get(sessionId);
  if (!s) {
    s = {
      sessionId,
      memory: emptyMemory(),
      artifacts: new ArtifactStore(),
      citations: [],
      pendingClarification: null,
      clarifyRound: 0,
      deepResearchBrief: null,
      lastMode: "qa",
      turnCount: 0,
    };
    sessions.set(sessionId, s);
  }
  return s;
}

export function resetSession(sessionId: string): void {
  sessions.delete(sessionId);
}
