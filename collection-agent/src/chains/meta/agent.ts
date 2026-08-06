import type { LiteratureInfoRow, MetaTextSource } from "../../types.js"
import type { LlmRuntime } from "../../runtime.js"
import { assistantText, completeSimpleWithFallback } from "../../runtime.js"
import { META_SYSTEM, buildMetaUserPrompt } from "./prompt.js"
import { MetaParseError, parseMetaOutput } from "./parse.js"

export interface MetaChainInput {
  pmid: string
  title: string
  excerpt: string
  textSource: MetaTextSource
  knownIdentifiers: Array<{ id: string; source: string }>
}

export interface MetaChainOptions {
  retryOnParseError?: boolean
  temperature?: number
}

/**
 * Specialized Stage-3 metadata extraction chain.
 * Deterministic I/O: paper excerpt → LiteratureInfoRow
 */
export class MetaChain {
  constructor(
    private readonly runtime: LlmRuntime,
    private readonly options: MetaChainOptions = {},
  ) {}

  async run(input: MetaChainInput): Promise<LiteratureInfoRow> {
    const retry = this.options.retryOnParseError !== false
    try {
      return await this.runOnce(input, false)
    } catch (err) {
      if (retry && err instanceof MetaParseError) {
        return await this.runOnce(input, true)
      }
      throw err
    }
  }

  private async runOnce(input: MetaChainInput, isRetry: boolean): Promise<LiteratureInfoRow> {
    const known = input.knownIdentifiers
      .map((h) => `${h.id} (${h.source})`)
      .join("; ")
    const fallbackIdentifier = input.knownIdentifiers.map((h) => h.id).join("; ")
    const sources = [...new Set(input.knownIdentifiers.map((h) => h.source).filter(Boolean))]
    const fallbackMsDataSource = sources.length === 1 ? sources[0] : sources.join("; ")

    const user = buildMetaUserPrompt({
      pmid: input.pmid,
      title: input.title,
      excerpt: input.excerpt,
      knownIdentifiers: known,
    })
    const retryHint = isRetry
      ? "\n\nYour previous answer was not valid JSON. Reply with ONLY one JSON object matching the schema."
      : ""

    const message = await completeSimpleWithFallback(
      this.runtime,
      {
        systemPrompt: META_SYSTEM,
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
    const row = parseMetaOutput(text, {
      pmid: input.pmid,
      title: input.title,
      textSource: input.textSource,
      fallbackIdentifier,
      fallbackMsDataSource,
    })

    // Prefer Stage-2 known IDs when LLM left identifier empty or partial
    if (fallbackIdentifier) {
      if (!row.identifier) row.identifier = fallbackIdentifier
      else {
        const have = new Set(row.identifier.split(/[;,\s]+/).filter(Boolean).map((x) => x.toUpperCase()))
        for (const id of fallbackIdentifier.split(";").map((x) => x.trim()).filter(Boolean)) {
          if (!have.has(id.toUpperCase())) {
            row.identifier = `${row.identifier}; ${id}`
            have.add(id.toUpperCase())
          }
        }
      }
      if (!row.msDataSource && fallbackMsDataSource) row.msDataSource = fallbackMsDataSource
    }

    return row
  }
}
