import { detectLang } from "./gate.js";
import { InvestigationMemory } from "../context/memory.js";
import { getLlm } from "../llm/client.js";
import type { AgentEvent } from "../sse.js";

export interface ClarificationPayload {
  needs_clarification: boolean;
  intro?: string;
  fields?: Array<{
    id: string;
    label: string;
    options: string[];
    allow_custom?: boolean;
    placeholder?: string;
  }>;
  free_text?: { label: string; placeholder: string };
  submit_label?: string;
  skip_label?: string;
}

const DR_CLARIFICATION_DEFAULT: ClarificationPayload = {
  needs_clarification: true,
  intro: "",
  fields: [],
  free_text: { label: "", placeholder: "" },
  submit_label: "",
  skip_label: "",
};

export function buildDeepResearchClarification(message: string): ClarificationPayload {
  const lang = detectLang(message);
  if (lang === "zh") {
    return {
      needs_clarification: true,
      intro: "为进行更精准的 PTM 深度调研，请补充以下信息（可跳过）：",
      fields: [
        {
          id: "research_goal",
          label: "研究目的",
          options: ["上游激酶/调控因子", "定量动力学与条件", "亚细胞定位/结构域", "功能与疾病关联", "药物/抑制剂影响"],
          allow_custom: true,
          placeholder: "例如：DNA 损伤后 TP53 S15 的激酶网络",
        },
        {
          id: "focus_aspect",
          label: "优先关注",
          options: ["WHO 调控酶", "WHEN 定量条件", "WHERE 定位", "WHY 功能疾病", "全面综合"],
          allow_custom: true,
        },
      ],
      free_text: {
        label: "补充说明（体系、比较条件、疾病背景等）",
        placeholder: "例如：人源细胞、与对照相比、乳腺癌背景…",
      },
      submit_label: "开始深度调研",
      skip_label: "跳过，直接调研",
    };
  }
  return {
    needs_clarification: true,
    intro: "To tailor this PTM deep research, please clarify (optional — you can skip):",
    fields: [
      {
        id: "research_goal",
        label: "Research goal",
        options: [
          "Upstream kinases/regulators",
          "Quantitative dynamics & conditions",
          "Localization & domains",
          "Function & disease",
          "Drug / inhibitor effects",
        ],
        allow_custom: true,
        placeholder: "e.g. kinase network for TP53 S15 after DNA damage",
      },
      {
        id: "focus_aspect",
        label: "Priority focus",
        options: ["WHO regulators", "WHEN quantitation", "WHERE context", "WHY function/disease", "Comprehensive"],
        allow_custom: true,
      },
    ],
    free_text: {
      label: "Additional context (system, comparison, disease)",
      placeholder: "e.g. human cells, vs control, breast cancer…",
    },
    submit_label: "Start deep research",
    skip_label: "Skip and research",
  };
}

export function mergeClarification(
  original: string,
  selections: Record<string, string>,
  freeText: string,
): string {
  const parts = [original];
  for (const [k, v] of Object.entries(selections)) {
    if (v) parts.push(`${k}: ${v}`);
  }
  if (freeText.trim()) parts.push(freeText.trim());
  return parts.join("\n");
}

export async function assessClarificationLlm(
  message: string,
  memory: InvestigationMemory,
): Promise<ClarificationPayload | null> {
  // Deep research always uses buildDeepResearchClarification — LLM assess optional
  return null;
}

export function clarificationEvent(payload: ClarificationPayload): AgentEvent {
  return { type: "clarification_request", ...payload };
}
