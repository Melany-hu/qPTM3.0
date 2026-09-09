import { AsyncLocalStorage } from "node:async_hooks";
/** OpenCode Go requires a stable session id per conversation (x-opencode-session). */
const opencodeSession = new AsyncLocalStorage();
export function getOpenCodeSessionId() {
    return opencodeSession.getStore();
}
export function runWithOpenCodeSession(sessionId, fn) {
    return opencodeSession.run(sessionId, fn);
}
