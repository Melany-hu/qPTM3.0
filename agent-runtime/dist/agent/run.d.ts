import type { AgentEvent } from "../sse.js";
export type AgentMode = "qa" | "deep_research";
export interface RunAgentOptions {
    message: string;
    sessionId: string;
    history: Array<{
        role: string;
        content: string;
    }>;
    mode: AgentMode;
    clarificationResponse?: {
        skip?: boolean;
        selections?: Record<string, string>;
        free_text?: string;
    } | null;
}
export declare function runAgent(opts: RunAgentOptions): AsyncGenerator<AgentEvent>;
export declare function newSessionId(): string;
