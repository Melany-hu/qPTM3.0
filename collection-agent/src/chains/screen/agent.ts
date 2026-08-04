import type { AbstractRecord, ScreenResult } from "../../types.js"
import type { LlmRuntime } from "../../runtime.js"
import { assistantText } from "../../runtime.js"
import { SCREEN_SYSTEM, buildScreenUserPrompt } from "./prompt.js"
import { parseScreenOutput, ScreenParseError } from "./parse.js"

export interface ScreenChainOptions {
  /** Retry once on parse failure (default true) */
  retryOnParseError?: boolean
  temperature?: number
}

/**
 * Specialized Stage-1 classification chain.
 * Deterministic I/O: AbstractRecord → ScreenResult
 * (Pi Coding Agent is NOT used here — only ModelRuntime.completeSimple)
 */
export class ScreenChain {
  constructor(
    private readonly runtime: LlmRuntime,
    private readonly options: ScreenChainOptions = {},
  ) {}

  async run(abstract: AbstractRecord): Promise<ScreenResult> {
    const retry = this.options.retryOnParseError !== false
    try {
      return await this.runOnce(abstract, false)
    } catch (err) {
      if (retry && err instanceof ScreenParseError) {
        return await this.runOnce(abstract, true)
      }
      throw err
    }
  }

  private async runOnce(abstract: AbstractRecord, isRetry: boolean): Promise<ScreenResult> {
    const user = buildScreenUserPrompt(abstract.title, abstract.abstract)
    const retryHint = isRetry
      ? "\n\nYour previous answer was not valid JSON. Reply with ONLY one JSON object matching the schema."
      : ""

    const message = await this.runtime.modelRuntime.completeSimple(
      this.runtime.model,
      {
        systemPrompt: SCREEN_SYSTEM,
        messages: [
          {
            role: "user",
            content: user + retryHint,
            timestamp: Date.now(),
          },
        ],
      },
      {
        temperature: this.options.temperature ?? 0,
      },
    )

    const text = assistantText(message)
    return parseScreenOutput(text, {
      pmid: abstract.pmid,
      title: abstract.title,
      sourceFile: abstract.sourceFile,
    })
  }
}
