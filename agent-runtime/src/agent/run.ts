import { randomUUID } from "node:crypto";
import type { AgentEvent } from "../sse.js";
import { getOrCreateSession } from "../context/session.js";
import { mergeClarification, buildDeepResearchClarification, clarificationEvent } from "./clarification.js";
import { runQA } from "./qa-react.js";
import { runDeepResearch } from "./deep-research.js";
import { mergeEntities, parseEntities } from "../context/memory.js";

export type AgentMode = "qa" | "deep_research";

export interface RunAgentOptions {
  message: string;
  sessionId: string;
  history: Array<{ role: string; content: string }>;
  mode: AgentMode;
  clarificationResponse?: {
    skip?: boolean;
    selections?: Record<string, string>;
    free_text?: string;
  } | null;
}

export async function* runAgent(opts: RunAgentOptions): AsyncGenerator<AgentEvent> {
  const session = getOrCreateSession(opts.sessionId);
  session.turnCount += 1;
  session.lastMode = opts.mode;

  let userMessage = (opts.message || "").trim();
  const parsed = parseEntities(userMessage);
  mergeEntities(session.memory, parsed);

  if (opts.mode === "deep_research") {
    if (opts.clarificationResponse) {
      if (opts.clarificationResponse.skip) {
        // keep original message
      } else {
        userMessage = mergeClarification(
          userMessage,
          opts.clarificationResponse.selections || {},
          opts.clarificationResponse.free_text || "",
        );
      }
      session.pendingClarification = null;
    } else {
      const payload = buildDeepResearchClarification(userMessage);
      session.pendingClarification = { message: userMessage, payload };
      yield clarificationEvent(payload);
      return;
    }

    yield* runDeepResearch(userMessage, opts.history, session);
    return;
  }

  yield* runQA(userMessage, opts.history, session);
}

export function newSessionId(): string {
  return randomUUID();
}
