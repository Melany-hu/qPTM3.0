/** Connect qPTM stdio MCP only — never blocks on BioMCP. */
export declare function initQptmMcp(): Promise<void>;
/** @deprecated Use initQptmMcp — kept for callers that only need qPTM tools. */
export declare function initMcpClients(): Promise<void>;
export declare function readQptmResource(uri: string): Promise<string>;
export declare function callQptmTool(toolName: string, args: Record<string, unknown>): Promise<{
    success: boolean;
    summary: string;
    data: unknown;
}>;
export declare function callBiomcp(command: string, args?: string[]): Promise<string>;
export declare function biomcpSearchArticle(query: string): Promise<string>;
export declare function biomcpGetArticle(id: string): Promise<string>;
export declare function webSearch(query: string): Promise<string>;
