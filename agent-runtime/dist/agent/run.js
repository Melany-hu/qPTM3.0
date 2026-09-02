import { randomUUID } from "node:crypto";
import { getOrCreateSession } from "../context/session.js";
import { mergeClarification, applyClarificationToMemory, buildDeepResearchClarification, clarificationEvent, } from "./clarification.js";
import { runQA } from "./qa-react.js";
import { runDeepResearch } from "./deep-research.js";
import { detectLang } from "./gate.js";
import { mergeEntities, normalizeTargetIdentity, parseEntities } from "../context/memory.js";
/** Soft cap so the agent can ask multiple times, but not loop forever. */
const MAX_CLARIFY_ROUNDS = 4;
export async function* runAgent(opts) {
    const session = getOrCreateSession(opts.sessionId);
    session.turnCount += 1;
    session.lastMode = opts.mode;
    let userMessage = (opts.message || "").trim();
    const parsed = parseEntities(userMessage);
    mergeEntities(session.memory, parsed);
    const lang = detectLang(userMessage);
    if (opts.mode === "deep_research") {
        let skippedClarify = false;
        if (opts.clarificationResponse) {
            const base = (session.deepResearchBrief || userMessage).trim();
            if (!opts.clarificationResponse.skip) {
                applyClarificationToMemory(session.memory, opts.clarificationResponse.selections || {}, opts.clarificationResponse.free_text || "");
                userMessage = mergeClarification(base, opts.clarificationResponse.selections || {}, opts.clarificationResponse.free_text || "");
            }
            else {
                skippedClarify = true;
                userMessage = base;
            }
            session.deepResearchBrief = userMessage;
            session.clarifyRound += 1;
            mergeEntities(session.memory, parseEntities(userMessage));
            normalizeTargetIdentity(session.memory, userMessage);
            session.pendingClarification = null;
        }
        else {
            // New deep-research question — reset multi-round clarify state.
            session.clarifyRound = 0;
            session.deepResearchBrief = userMessage;
        }
        // Agent may ask again (or for the first time) when something critical is still unclear.
        if (!skippedClarify && session.clarifyRound < MAX_CLARIFY_ROUNDS) {
            yield {
                type: "phase_update",
                phase: "clarifying",
                label: lang === "zh"
                    ? session.clarifyRound > 0
                        ? "根据已有信息，判断是否还需要补充…"
                        : "思考需要澄清的问题…"
                    : session.clarifyRound > 0
                        ? "Checking whether more clarification is needed…"
                        : "Thinking about what to clarify…",
            };
            const payload = await buildDeepResearchClarification(userMessage, session.memory, {
                round: session.clarifyRound,
                maxRounds: MAX_CLARIFY_ROUNDS,
            });
            if (payload.needs_clarification && (payload.fields || []).length) {
                session.pendingClarification = { message: userMessage, payload };
                yield clarificationEvent(payload);
                return;
            }
        }
        normalizeTargetIdentity(session.memory, userMessage);
        yield* runDeepResearch(userMessage, opts.history, session);
        return;
    }
    yield* runQA(userMessage, opts.history, session);
}
export function newSessionId() {
    return randomUUID();
}
