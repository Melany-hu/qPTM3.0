import type { LlmRuntime } from "../../runtime.js"
import { assistantText } from "../../runtime.js"
import type { ColumnMapping } from "../../stage5/heuristic.js"
import type { SheetInventory } from "../../stage5/tables.js"
import { parseQratioMapOutput, QratioMapParseError } from "./parse.js"
import { buildQratioMapUserPrompt, QRATIO_MAP_SYSTEM } from "./prompt.js"

export interface QratioMapInput {
  pmid: string
  title: string
  ptms: string
  sample: string
  condition: string
  detailCondition: string
  entryPath: string
  sheet: SheetInventory
}

export class QratioMapChain {
  constructor(
    private readonly runtime: LlmRuntime,
    private readonly options: { retryOnParseError?: boolean; temperature?: number } = {},
  ) {}

  async run(input: QratioMapInput): Promise<ColumnMapping & { skip: boolean }> {
    const retry = this.options.retryOnParseError !== false
    try {
      return await this.runOnce(input, false)
    } catch (err) {
      if (retry && err instanceof QratioMapParseError) {
        return await this.runOnce(input, true)
      }
      throw err
    }
  }

  private async runOnce(
    input: QratioMapInput,
    isRetry: boolean,
  ): Promise<ColumnMapping & { skip: boolean }> {
    const user = buildQratioMapUserPrompt({
      pmid: input.pmid,
      title: input.title,
      ptms: input.ptms,
      sample: input.sample,
      condition: input.condition,
      detailCondition: input.detailCondition,
      entryPath: input.entryPath,
      sheetName: input.sheet.name,
      headers: input.sheet.headers,
      preview: input.sheet.preview,
    })
    const retryHint = isRetry
      ? "\n\nYour previous answer was not valid JSON. Reply with ONLY one JSON object matching the schema."
      : ""

    const llmTimeoutMs = Number(process.env.STAGE5_LLM_TIMEOUT_MS ?? 120_000)
    const llmPromise = this.runtime.modelRuntime.completeSimple(
      this.runtime.model,
      {
        systemPrompt: QRATIO_MAP_SYSTEM,
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
    const message = await Promise.race([
      llmPromise,
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error(`qratio_llm_timeout_${llmTimeoutMs}ms`)), llmTimeoutMs),
      ),
    ])

    const text = assistantText(message)
    return parseQratioMapOutput(text, {
      entryPath: input.entryPath,
      sheetName: input.sheet.name,
      headerRowIndex: input.sheet.headerRowIndex,
    })
  }
}
