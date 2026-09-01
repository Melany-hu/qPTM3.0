import { emptyMemory } from "./memory.js";
import { ArtifactStore } from "./artifacts.js";
const sessions = new Map();
export function getOrCreateSession(sessionId) {
    let s = sessions.get(sessionId);
    if (!s) {
        s = {
            sessionId,
            memory: emptyMemory(),
            artifacts: new ArtifactStore(),
            citations: [],
            pendingClarification: null,
            lastMode: "qa",
            turnCount: 0,
        };
        sessions.set(sessionId, s);
    }
    return s;
}
export function resetSession(sessionId) {
    sessions.delete(sessionId);
}
