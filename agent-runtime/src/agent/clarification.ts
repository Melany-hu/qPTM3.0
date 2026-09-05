import { detectLang } from "./gate.js";
import {
  InvestigationMemory,
  extractPositionFromText,
  memoryPromptBlock,
  mergeEntities,
  parseEntities,
} from "../context/memory.js";
import { getLlm } from "../llm/client.js";
import type { AgentEvent } from "../sse.js";

export interface ClarificationOption {
  label: string;
  description?: string;
}

export interface ClarificationField {
  id: string;
  label: string;
  /** Short question under the field title. */
  prompt?: string;
  options: ClarificationOption[];
  allow_custom?: boolean;
  placeholder?: string;
}

export interface ClarificationPayload {
  needs_clarification: boolean;
  intro?: string;
  fields?: ClarificationField[];
  free_text?: { label: string; placeholder: string };
  submit_label?: string;
  skip_label?: string;
}

function opt(label: string, description = ""): ClarificationOption {
  return { label, description };
}

/** Minimal fallback only when LLM fails — still question-shaped, not a fixed WHO/WHEN template. */
function fallbackClarification(message: string, memory: InvestigationMemory): ClarificationPayload {
  const lang = detectLang(message);
  const target = [memory.gene, memory.position ? `S${memory.position}` : "", memory.ptm_type]
    .filter(Boolean)
    .join(" ")
    .trim();
  const subject = target || (lang === "zh" ? "该 PTM 问题" : "this PTM question");

  if (lang === "zh") {
    return {
      needs_clarification: true,
      intro: `在深入调研「${subject}」前，请先确认最关键的一点（可跳过）：`,
      fields: [
        {
          id: "priority",
          label: "本次优先弄清什么？",
          prompt: "选一项最贴近你当前目标的方向，或在下方手输。",
          options: [
            opt("上游如何调控", "激酶、酶或刺激如何修饰该位点"),
            opt("何时 / 何种条件变化", "定量动力学、处理条件与比较"),
            opt("功能与疾病意义", "功能后果、稳定性或疾病关联"),
            opt("文献机制", "已有机制链条与争议"),
          ],
          allow_custom: true,
          placeholder: "也可直接写你的目标…",
        },
      ],
      free_text: {
        label: "补充说明（可选）",
        placeholder: "物种/细胞系、比较条件、疾病背景等",
      },
      submit_label: "开始深度调研",
      skip_label: "跳过，直接调研",
    };
  }

  return {
    needs_clarification: true,
    intro: `Before deep research on “${subject}”, confirm the main priority (optional — you can skip):`,
    fields: [
      {
        id: "priority",
        label: "What should we prioritize?",
        prompt: "Pick the closest goal, or type your own below.",
        options: [
          opt("Upstream regulation", "Kinases/enzymes/stimuli acting on the site"),
          opt("Conditions & dynamics", "Quantitative changes and experimental conditions"),
          opt("Function & disease", "Functional consequences, stability, disease links"),
          opt("Literature mechanisms", "Known mechanistic chains and debates"),
        ],
        allow_custom: true,
        placeholder: "Or type your goal…",
      },
    ],
    free_text: {
      label: "Additional context (optional)",
      placeholder: "Organism/cell line, comparison, disease background…",
    },
    submit_label: "Start deep research",
    skip_label: "Skip and research",
  };
}

function normalizeOption(raw: unknown): ClarificationOption | null {
  if (typeof raw === "string" && raw.trim()) return { label: raw.trim() };
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const label = String(o.label || o.value || "").trim();
  if (!label) return null;
  return {
    label,
    description: String(o.description || o.desc || "").trim() || undefined,
  };
}

function normalizePayload(raw: unknown, message: string, memory: InvestigationMemory): ClarificationPayload {
  if (!raw || typeof raw !== "object") return fallbackClarification(message, memory);
  const data = raw as Record<string, unknown>;

  if (data.needs_clarification === false) {
    return { needs_clarification: false };
  }

  const lang = detectLang(message);
  const fieldsIn = Array.isArray(data.fields) ? data.fields : [];
  const fields: ClarificationField[] = [];

  for (let i = 0; i < fieldsIn.length && fields.length < 3; i += 1) {
    const f = fieldsIn[i];
    if (!f || typeof f !== "object") continue;
    const fr = f as Record<string, unknown>;
    const options = (Array.isArray(fr.options) ? fr.options : [])
      .map(normalizeOption)
      .filter((x): x is ClarificationOption => Boolean(x))
      .slice(0, 6);
    if (options.length < 2) continue;
    const id = String(fr.id || `q${fields.length + 1}`).replace(/[^\w-]/g, "_").slice(0, 40) || `q${fields.length + 1}`;
    fields.push({
      id,
      label: String(fr.label || (lang === "zh" ? `问题 ${fields.length + 1}` : `Question ${fields.length + 1}`)).slice(0, 80),
      prompt: String(fr.prompt || fr.question || "").slice(0, 200) || undefined,
      options,
      allow_custom: fr.allow_custom !== false,
      placeholder: String(fr.placeholder || (lang === "zh" ? "其他：直接输入…" : "Other: type here…")).slice(0, 160),
    });
  }

  if (!fields.length) return fallbackClarification(message, memory);

  const free = (data.free_text && typeof data.free_text === "object"
    ? (data.free_text as Record<string, unknown>)
    : null);

  return {
    needs_clarification: true,
    intro: String(
      data.intro ||
        (lang === "zh"
          ? "开始深度调研前，我想先确认以下几点（均可跳过）："
          : "Before deep research, I’d like to confirm a few points (all optional):"),
    ).slice(0, 300),
    fields,
    free_text: {
      label: String(free?.label || (lang === "zh" ? "补充说明（可选）" : "Additional context (optional)")).slice(0, 80),
      placeholder: String(
        free?.placeholder ||
          (lang === "zh"
            ? "物种/细胞系、比较条件、疾病背景等"
            : "Organism/cell line, comparison, disease background…"),
      ).slice(0, 160),
    },
    submit_label: String(data.submit_label || (lang === "zh" ? "开始深度调研" : "Start deep research")).slice(0, 40),
    skip_label: String(data.skip_label || (lang === "zh" ? "跳过，直接调研" : "Skip and research")).slice(0, 40),
  };
}

export interface ClarifyRoundOpts {
  /** Completed clarification rounds so far (0 = first ask). */
  round?: number;
  maxRounds?: number;
}

/**
 * Agent-generated clarification: judge what is still ambiguous,
 * then propose 1–3 targeted questions — may run across multiple rounds.
 */
export async function buildDeepResearchClarification(
  message: string,
  memory?: InvestigationMemory,
  roundOpts: ClarifyRoundOpts = {},
): Promise<ClarificationPayload> {
  const mem = memory || ({ ...parseEntities(message) } as InvestigationMemory);
  const lang = detectLang(message);
  const round = roundOpts.round ?? 0;
  const maxRounds = roundOpts.maxRounds ?? 4;

  const system =
    lang === "zh"
      ? `你是 qPTM 深度调研助手。请判断：以当前信息，是否还需要向用户澄清后才能做更精准的调研。
规则：
1. 允许多轮澄清。已完成 ${round}/${maxRounds} 轮。只问**仍然不明确且对本次调研关键**的点；不要重复用户已回答过的内容。
2. 不要套固定 WHO/WHEN/WHERE/WHY 模板；每次 1–3 个字段，每字段 2–5 个贴合选项（含简短 description）。
3. 若蛋白/基因已知但无具体残基编号，且目标是位点级（调控网络、上游激酶、功能等），应问 id=site，选项写清残基（如「S18（小鼠）/ S15（人）」）。若用户只选了「单个位点」却没给编号，下一轮应追问具体位点。
4. 信息已足够，或用户已明确可先按假设推进时，返回 needs_clarification=false（调研阶段仍可在报告里标注假设或再提问）。
5. 不要为了凑问题而提问；不关键就跳过。
6. 字段 id 用英文 snake_case；文案用中文。只输出 JSON，不要 markdown。

JSON 格式：
{
  "needs_clarification": true|false,
  "intro": "简短说明",
  "fields": [
    {
      "id": "priority",
      "label": "标题",
      "prompt": "一句问句",
      "options": [{"label":"...","description":"..."}],
      "allow_custom": true,
      "placeholder": "其他…"
    }
  ],
  "free_text": {"label":"补充说明（可选）","placeholder":"..."},
  "submit_label": "开始深度调研",
  "skip_label": "跳过，直接调研"
}`
      : `You are the qPTM deep-research assistant. Decide whether more clarification is still needed.
Rules:
1. Multi-round clarification is allowed. Completed ${round}/${maxRounds} rounds. Ask ONLY what is still ambiguous and material; do not re-ask answered points.
2. No fixed WHO/WHEN/WHERE/WHY template; 1–3 fields, 2–5 tailored options each.
3. If gene/protein is known but residue is missing for a site-level goal, ask id=site with concrete residues. If the user chose “single site” without a number, follow up on the residue.
4. If information is sufficient (or the user can proceed under a stated assumption), return needs_clarification=false.
5. Do not invent questions. Output JSON only.

JSON schema:
{
  "needs_clarification": true|false,
  "intro": "...",
  "fields": [{"id":"...","label":"...","prompt":"...","options":[{"label":"...","description":"..."}],"allow_custom":true,"placeholder":"..."}],
  "free_text": {"label":"...","placeholder":"..."},
  "submit_label": "Start deep research",
  "skip_label": "Skip and research"
}`;

  const user = [
    `User question / accumulated context:\n${message}`,
    memoryPromptBlock(mem),
    `Parsed entities: gene=${mem.gene || ""} position=${mem.position || ""} ptm=${mem.ptm_type || ""} organism=${mem.organism || ""}`,
    `Clarification round: ${round} (0=first ask). Max rounds: ${maxRounds}.`,
  ].join("\n");

  try {
    const llm = getLlm();
    const { content } = await llm.chatCompletion(
      [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      { maxTokens: 1200, temperature: 0.3 },
    );
    const text = content.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();
    const parsed = JSON.parse(text) as unknown;
    return normalizePayload(parsed, message, mem);
  } catch {
    // On follow-up rounds, fail open (start research) rather than forcing a generic card again.
    if (round > 0) return { needs_clarification: false };
    return fallbackClarification(message, mem);
  }
}

export function mergeClarification(
  original: string,
  selections: Record<string, string>,
  freeText: string,
): string {
  const parts = [original];
  for (const [k, v] of Object.entries(selections)) {
    if (!v) continue;
    parts.push(`${k}: ${v}`);
  }
  if (freeText.trim()) parts.push(freeText.trim());
  return parts.join("\n");
}

/** Fold clarification choices into memory (site labels, organism, etc.). */
export function applyClarificationToMemory(
  memory: InvestigationMemory,
  selections: Record<string, string>,
  freeText: string,
): void {
  const texts = [...Object.values(selections), freeText].filter(Boolean);
  for (const t of texts) {
    mergeEntities(memory, parseEntities(t), t);
    const pos = extractPositionFromText(t);
    if (pos && !memory.position) memory.position = pos;
    if (/小鼠|mouse/i.test(t)) memory.organism = "mouse";
    if (/人源|人类|human/i.test(t) && memory.organism !== "mouse") memory.organism = "human";
  }
}

export function clarificationEvent(payload: ClarificationPayload): AgentEvent {
  return { type: "clarification_request", ...payload };
}
