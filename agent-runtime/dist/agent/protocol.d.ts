/** Tokens that must never appear in user-visible assistant text. */
export declare const PROTOCOL_LEAK_RE: RegExp;
export declare function containsProtocolMarkup(text: string): boolean;
export declare function stripProtocolMarkup(text: string): {
    text: string;
    leaked: boolean;
};
export declare function failedGenerationMessage(lang?: "zh" | "en"): string;
/** If stripping leaves nothing readable, replace with a retry prompt. */
export declare function sanitizeUserVisibleText(text: string, lang?: "zh" | "en"): string;
