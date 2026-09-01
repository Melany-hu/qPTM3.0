export type AgentEventType = "text" | "tool_call" | "tool_result" | "phase_update" | "sources" | "follow_up_questions" | "clarification_request" | "plan_created" | "done" | "error" | "literature_search";
export interface AgentEvent {
    type: AgentEventType | string;
    [key: string]: unknown;
}
export declare function sseFormat(event: string, data: Record<string, unknown>): string;
export declare function agentEventToSse(event: AgentEvent): string | null;
