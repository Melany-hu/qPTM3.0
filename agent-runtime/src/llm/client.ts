import OpenAI from "openai";
import { cfg } from "../config.js";

const ZEN_PREFIXES = ["gpt-", "gemini-", "claude-", "kimi-", "qwen"];

function baseUrlForModel(model: string): string {
  const m = model.toLowerCase();
  if (ZEN_PREFIXES.some((p) => m.startsWith(p))) return cfg.deepseekZenBaseUrl;
  return cfg.deepseekBaseUrl;
}

export type LlmStreamEvent =
  | { type: "text"; content: string }
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown> }
  | { type: "done" };

export class LlmClient {
  private clients: Map<string, OpenAI> = new Map();

  private clientFor(model: string): OpenAI {
    const base = baseUrlForModel(model);
    let c = this.clients.get(base);
    if (!c) {
      c = new OpenAI({
        apiKey: cfg.deepseekApiKey,
        baseURL: base,
        maxRetries: 0,
        timeout: 120000,
      });
      this.clients.set(base, c);
    }
    return c;
  }

  modelChain(): string[] {
    const chain = [cfg.deepseekModel, ...cfg.deepseekFallbackModels];
    return [...new Set(chain.filter(Boolean))];
  }

  async chatCompletion(
    messages: OpenAI.Chat.ChatCompletionMessageParam[],
    options: {
      tools?: OpenAI.Chat.ChatCompletionTool[];
      temperature?: number;
      maxTokens?: number;
    } = {},
  ): Promise<{ content: string; toolCalls: Array<{ id: string; name: string; arguments: Record<string, unknown> }> }> {
    const models = this.modelChain();
    let lastErr: Error | null = null;

    for (const model of models) {
      try {
        const res = await this.clientFor(model).chat.completions.create({
          model,
          messages,
          tools: options.tools,
          temperature: options.temperature ?? 0.3,
          max_tokens: options.maxTokens ?? 4096,
        });
        const msg = res.choices[0]?.message;
        const content = msg?.content || "";
        const toolCalls = (msg?.tool_calls || []).map((tc) => ({
          id: tc.id,
          name: tc.function.name,
          arguments: JSON.parse(tc.function.arguments || "{}") as Record<string, unknown>,
        }));
        if (!content && toolCalls.length === 0) throw new Error("empty response");
        return { content, toolCalls };
      } catch (e) {
        lastErr = e instanceof Error ? e : new Error(String(e));
      }
    }
    throw lastErr || new Error("LLM failed");
  }

  async *chatCompletionStream(
    messages: OpenAI.Chat.ChatCompletionMessageParam[],
    options: {
      tools?: OpenAI.Chat.ChatCompletionTool[];
      temperature?: number;
      maxTokens?: number;
    } = {},
  ): AsyncGenerator<LlmStreamEvent> {
    const models = this.modelChain();
    let lastErr: Error | null = null;

    for (const model of models) {
      try {
        const stream = await this.clientFor(model).chat.completions.create({
          model,
          messages,
          tools: options.tools,
          temperature: options.temperature ?? 0.3,
          max_tokens: options.maxTokens ?? 8192,
          stream: true,
        });

        const toolAcc: Map<number, { id: string; name: string; args: string }> = new Map();

        for await (const chunk of stream) {
          const delta = chunk.choices[0]?.delta;
          if (!delta) continue;
          if (delta.content) yield { type: "text", content: delta.content };
          if (delta.tool_calls) {
            for (const tc of delta.tool_calls) {
              const idx = tc.index ?? 0;
              let acc = toolAcc.get(idx);
              if (!acc) {
                acc = { id: tc.id || `call_${idx}`, name: tc.function?.name || "", args: "" };
                toolAcc.set(idx, acc);
              }
              if (tc.id) acc.id = tc.id;
              if (tc.function?.name) acc.name = tc.function.name;
              if (tc.function?.arguments) acc.args += tc.function.arguments;
            }
          }
        }

        for (const acc of toolAcc.values()) {
          if (acc.name) {
            yield {
              type: "tool_call",
              id: acc.id,
              name: acc.name,
              arguments: JSON.parse(acc.args || "{}") as Record<string, unknown>,
            };
          }
        }
        yield { type: "done" };
        return;
      } catch (e) {
        lastErr = e instanceof Error ? e : new Error(String(e));
      }
    }
    throw lastErr || new Error("LLM stream failed");
  }
}

let singleton: LlmClient | null = null;
export function getLlm(): LlmClient {
  if (!singleton) singleton = new LlmClient();
  return singleton;
}
