import { AsyncLocalStorage } from "node:async_hooks";

/** OpenCode Go requires a stable session id per conversation (x-opencode-session). */
const opencodeSession = new AsyncLocalStorage<string>();

export function getOpenCodeSessionId(): string | undefined {
  return opencodeSession.getStore();
}

export function runWithOpenCodeSession<T>(sessionId: string, fn: () => Promise<T>): Promise<T> {
  return opencodeSession.run(sessionId, fn);
}
