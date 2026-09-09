export declare function getOpenCodeSessionId(): string | undefined;
export declare function runWithOpenCodeSession<T>(sessionId: string, fn: () => Promise<T>): Promise<T>;
