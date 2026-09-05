/** Tokens that must never appear in user-visible assistant text. */
export const PROTOCOL_LEAK_RE =
  /<\|?DSML\|?|<\/?tool_call\b|tool_calls|function_call|<tool\b|<\/tool>/i;

const DSML_BLOCK_RE = /<\|DSML\|[\s\S]*?(?:\|DSML\|>|$)/gi;
const TOOL_CALL_BLOCK_RE = /<\/?tool_call\b[^>]*>[\s\S]*?(<\/tool_call>|$)/gi;
const TOOL_CALLS_JSON_RE = /```(?:json|xml|text)?\s*\{[\s\S]*?"tool_calls"[\s\S]*?```/gi;
const TOOL_CALLS_INLINE_RE = /"?tool_calls"?\s*[:=]\s*\[[\s\S]*?\]/gi;
const FUNCTION_CALL_RE = /"?function_call"?\s*[:=]\s*\{[\s\S]*?\}/gi;
const ANGLE_PROTOCOL_RE = /<\|[^|]{0,80}\|>/g;

export function containsProtocolMarkup(text: string): boolean {
  return Boolean(text && PROTOCOL_LEAK_RE.test(text));
}

export function stripProtocolMarkup(text: string): { text: string; leaked: boolean } {
  if (!text) return { text: "", leaked: false };
  const leaked = containsProtocolMarkup(text);
  let s = text;
  s = s.replace(DSML_BLOCK_RE, "");
  s = s.replace(TOOL_CALL_BLOCK_RE, "");
  s = s.replace(TOOL_CALLS_JSON_RE, "");
  s = s.replace(TOOL_CALLS_INLINE_RE, "");
  s = s.replace(FUNCTION_CALL_RE, "");
  s = s.replace(ANGLE_PROTOCOL_RE, "");
  s = s.replace(/\n{3,}/g, "\n\n").trim();
  return { text: s, leaked };
}

export function failedGenerationMessage(lang: "zh" | "en" = "en"): string {
  return lang === "zh" ? "生成失败，请重试。" : "Generation failed. Please retry.";
}

/** If stripping leaves nothing readable, replace with a retry prompt. */
export function sanitizeUserVisibleText(text: string, lang: "zh" | "en" = "en"): string {
  const { text: cleaned, leaked } = stripProtocolMarkup(text);
  if (leaked && cleaned.replace(/\s/g, "").length < 12) {
    return failedGenerationMessage(lang);
  }
  return cleaned;
}
