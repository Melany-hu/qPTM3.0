import { cfg } from "../config.js";
import { ArtifactStore } from "../context/artifacts.js";
import {
  addFinding,
  InvestigationMemory,
  mergeEntities,
  memoryPromptBlock,
  normalizeTargetIdentity,
  parseEntities,
} from "../context/memory.js";
import { SessionState } from "../context/session.js";
import {
  callQptmTool,
  biomcpGetArticle,
  readQptmResource,
  searchLiteratureArticles,
  webSearch,
} from "../mcp/hub.js";
import { loadSkills, skillsForMode } from "../skills/loader.js";
import { getLlm } from "../llm/client.js";
import type { AgentEvent } from "../sse.js";
import { mergeCitation, type Citation } from "./citations.js";
import { detectLang } from "./gate.js";
import { retrieveToolsDeep } from "./retriever.js";
import { generateFollowUps } from "./followups.js";
import {
  applyResolvedIdentity,
  invokeArgumentsJson,
  resolveSessionTarget,
} from "./resolve-target.js";

interface PlanStep {
  step: number;
  title: string;
  entity: string;
  tools: string[];
  rationale: string;
}

function phase(p: string, label: string): AgentEvent {
  return { type: "phase_update", phase: p, label };
}

export async function* runDeepResearch(
  userMessage: string,
  history: Array<{ role: string; content: string }>,
  session: SessionState,
): AsyncGenerator<AgentEvent> {
  const memory = session.memory;
  const artifacts = session.artifacts;
  const lang = detectLang(userMessage);
  mergeEntities(memory, parseEntities(userMessage));
  normalizeTargetIdentity(memory, userMessage);

  yield phase("planning", lang === "zh" ? "制定调研计划" : "Planning research");

  if (memory.gene || memory.uniprot_ac) {
    yield {
      type: "tool_call",
      tool_name: "qptm_resolve",
      arguments: { gene: memory.gene, position: memory.position, query: userMessage },
      kind: "database",
    };
    const resolved = await resolveSessionTarget(memory, userMessage);
    yield {
      type: "tool_result",
      payload: {
        tool_name: "qptm_resolve",
        success: resolved.success,
        summary: resolved.summary,
        error_kind: resolved.error_kind,
        data_count: 1,
      },
      kind: "database",
    };
  }

  const skills = loadSkills(skillsForMode("deep_research", userMessage));
  const sourcesCatalog = await readQptmResource("qptm://sources");
  const plan = await buildPlan(userMessage, memory, skills, sourcesCatalog, lang);

  yield {
    type: "plan_created",
    plan: {
      intent_summary: plan.summary,
      steps: plan.steps.map((s) => ({
        step: s.step,
        title: s.title,
        description: s.rationale,
        database: s.entity,
        status: "pending",
      })),
    },
  };

  const citations: Citation[] = [...session.citations];
  const toolsUsed: string[] = [];

  yield phase("database", lang === "zh" ? "执行数据库调研" : "Database investigation");

  for (const step of plan.steps) {
    for (const tool of step.tools) {
      yield {
        type: "tool_call",
        tool_name: tool,
        arguments: { entity: step.entity, query: userMessage },
        kind: "database",
      };
      const result = await callQptmTool("qptm_invoke", {
        tool_name: tool,
        arguments_json: invokeArgumentsJson(memory, userMessage),
      });
      applyResolvedIdentity(memory, result);
      const kindTag = result.error_kind ? ` [${result.error_kind}]` : "";
      addFinding(memory, tool, `${result.summary}${kindTag}`);
      artifacts.add("db_result", `${tool}`, result.summary, { tool });
      toolsUsed.push(tool);
      mergeCitation(citations, tool);
      yield {
        type: "tool_result",
        payload: {
          tool_name: tool,
          success: result.success,
          summary: result.summary,
          error_kind: result.error_kind,
          data_count: 1,
        },
        kind: "database",
      };
    }
  }

  yield phase("literature", lang === "zh" ? "文献检索与整合" : "Literature search");
  const geneOk = memory.gene && !/^[STYKR]\d{2,5}$/i.test(memory.gene);
  const siteLabel = memory.position ? `S${memory.position}` : "";
  const primaryQuestion = userMessage.split("\n").map((l) => l.trim()).filter(Boolean)[0] || userMessage;
  const litQueries = [
    geneOk && siteLabel
      ? `${memory.gene} ${siteLabel} phosphorylation ${/疾病|disease|cancer|肿瘤/i.test(userMessage) ? "disease cancer" : "function"}`.trim()
      : "",
    geneOk ? `${memory.gene} ${siteLabel} phosphorylation`.trim() : "",
    primaryQuestion,
  ].filter((q, i, arr) => Boolean(q) && arr.indexOf(q) === i);

  const pmids: string[] = [];
  for (let i = 0; i < litQueries.length; i++) {
    const q = litQueries[i];
    const start = Date.now();
    const lit = await searchLiteratureArticles(q);
    const found = (lit.match(/PMID[:\s]*(\d{7,8})/gi) || []).length;
    artifacts.add("literature_search", q, lit.slice(0, 2000), {
      pmids: [...lit.matchAll(/(\d{7,8})/g)].slice(0, 10).map((m) => m[1]),
    });
    for (const m of lit.matchAll(/(\d{7,8})/g)) {
      if (pmids.length < 5) pmids.push(m[1]);
    }
    yield {
      type: "literature_search",
      round: i + 1,
      query: q,
      papers_found: found,
      elapsed_s: (Date.now() - start) / 1000,
    };
    mergeCitation(citations, "pubtator_literature_search");
  }

  for (const pmid of pmids.slice(0, 3)) {
    let abstract = "";
    const viaPubmed = await callQptmTool("qptm_invoke", {
      tool_name: "pubmed_fetch_abstracts",
      arguments_json: JSON.stringify({ pmids: [pmid] }),
    });
    if (viaPubmed.success || viaPubmed.summary) {
      abstract = `${viaPubmed.summary || ""}\n${JSON.stringify(viaPubmed.data ?? {})}`;
    } else {
      abstract = await biomcpGetArticle(`pmid:${pmid}`);
    }
    artifacts.add("paper", `PMID:${pmid}`, abstract.slice(0, 2000), { pmids: [pmid] });
  }

  const web = await webSearch(`${userMessage} PTM site`);
  if (web && !web.startsWith("Web search failed")) {
    artifacts.add("web_search", userMessage, web.slice(0, 1500));
  }

  yield phase("synthesis", lang === "zh" ? "撰写深度调研报告" : "Writing research report");

  const report = await synthesizeDeepReport(
    userMessage,
    history,
    memory,
    artifacts,
    skills,
    sourcesCatalog,
    citations,
    lang,
  );

  for (const chunk of chunkText(report, 120)) {
    yield { type: "text", content: chunk };
  }

  yield { type: "sources", citations };
  session.citations = citations;

  const followUps = await generateFollowUps(userMessage, report, memory, artifacts, "deep_research", toolsUsed);
  yield { type: "follow_up_questions", questions: followUps };
  yield { type: "done" };
}

async function buildPlan(
  question: string,
  memory: InvestigationMemory,
  skills: string,
  catalog: string,
  lang: "zh" | "en",
): Promise<{ summary: string; steps: PlanStep[] }> {
  const tools = retrieveToolsDeep(question, memory);
  const prompt =
    lang === "zh"
      ? `为 PTM 深度调研生成 JSON 计划。按用户问题与澄清信息定制步骤，不要套用固定 WHO/WHEN/WHERE/WHY 模板；无关维度可跳过。
问题：${question}
上下文：${memoryPromptBlock(memory)}
可用工具：${tools.join(", ")}

输出: {"summary":"...","steps":[{"step":1,"title":"生物学主题标题","entity":"kinase|condition|function|disease|localization|drug|literature|site","tools":["tool_name"],"rationale":"为何此步对回答该问题必要"}]}
最多 6 步。title/rationale 用中文生物学表述，禁止写 WHO/WHEN/WHERE/WHY。`
      : `Create a JSON plan for PTM deep research tailored to the user's question and clarification. Do NOT force a fixed WHO/WHEN/WHERE/WHY template; skip irrelevant dimensions.
Question: ${question}
Context: ${memoryPromptBlock(memory)}
Tools: ${tools.join(", ")}

Output: {"summary":"...","steps":[{"step":1,"title":"biological theme","entity":"kinase|condition|function|disease|localization|drug|literature|site","tools":["tool_name"],"rationale":"why this step is needed"}]}
Max 6 steps. Never use WHO/WHEN/WHERE/WHY labels in title/rationale.`;

  try {
    const llm = getLlm();
    const { content } = await llm.chatCompletion(
      [
        { role: "system", content: `${skills}\n${catalog.slice(0, 3000)}` },
        { role: "user", content: prompt },
      ],
      { maxTokens: 1200, temperature: 0.2 },
    );
    const parsed = JSON.parse(content.replace(/```json?\s*|\s*```/g, "").trim()) as {
      summary?: string;
      steps?: PlanStep[];
    };
    if (parsed.steps?.length) {
      return {
        summary: parsed.summary || question,
        steps: parsed.steps.slice(0, cfg.drMaxPlanSteps),
      };
    }
  } catch {
    /* fallback */
  }

  // Goal-flexible fallback — pick tool buckets by question keywords, not fixed WHO→WHEN→WHY.
  const q = question.toLowerCase();
  const steps: PlanStep[] = [];
  const push = (title: string, entity: string, rationale: string, slice: string[]) => {
    if (!slice.length) return;
    steps.push({
      step: steps.length + 1,
      title,
      entity,
      tools: slice,
      rationale,
    });
  };
  push(
    lang === "zh" ? "位点与蛋白背景" : "Site & protein context",
    "site",
    lang === "zh" ? "确认靶点与基础注释" : "Confirm target and baseline annotation",
    tools.filter((t) => /qptm_search|uniprot/i.test(t)).slice(0, 2),
  );
  if (/kinase|上游|调控|who|enzyme|e3|writer/i.test(q) || !/only|仅/.test(q)) {
    push(
      lang === "zh" ? "上游调控" : "Upstream regulation",
      "kinase",
      lang === "zh" ? "检索激酶/酶/调控证据" : "Retrieve kinase/enzyme/regulator evidence",
      tools.filter((t) => /kinase|enzyme|psp_kinase|gps|ekpi_kinase/i.test(t)).slice(0, 3),
    );
  }
  if (/condition|定量|动力学|fold|when|刺激|处理/i.test(q)) {
    push(
      lang === "zh" ? "定量与条件" : "Quantitation & conditions",
      "condition",
      lang === "zh" ? "检索条件定量数据" : "Retrieve quantitative condition data",
      tools.filter((t) => /condition|quantitative|ekpi_quant/i.test(t)).slice(0, 3),
    );
  }
  if (/local|定位|domain|where|结构域/i.test(q)) {
    push(
      lang === "zh" ? "定位与结构域" : "Localization & domains",
      "localization",
      lang === "zh" ? "检索定位/结构域背景" : "Retrieve localization/domain context",
      tools.filter((t) => /local|compartment|domain|interpro|inuloc/i.test(t)).slice(0, 3),
    );
  }
  if (/function|disease|疾病|功能|稳定|why|突变|mutat|drug|药/i.test(q) || steps.length < 2) {
    push(
      lang === "zh" ? "功能与疾病关联" : "Function & disease",
      "function",
      lang === "zh" ? "检索功能、疾病与稳定性证据" : "Retrieve function/disease/stability evidence",
      tools.filter((t) => /regulatory|disease|stability|funcscore|ptmd|drug|decryptm/i.test(t)).slice(0, 4),
    );
  }
  if (!steps.length) {
    push(
      lang === "zh" ? "综合检索" : "Broad retrieval",
      "site",
      lang === "zh" ? "按可用工具综合检索" : "Broad tool sweep",
      tools.slice(0, 5),
    );
  }
  return { summary: question, steps };
}

async function synthesizeDeepReport(
  question: string,
  history: Array<{ role: string; content: string }>,
  memory: InvestigationMemory,
  artifacts: ArtifactStore,
  skills: string,
  catalog: string,
  citations: Citation[],
  lang: "zh" | "en",
): Promise<string> {
  const citeList = citations.map((c) => `${c.id}: ${c.database}`).join(", ");
  const system =
    lang === "zh"
      ? `你是 PTM 深度调研专家。优先基于已收集证据撰写分节、引用充分的调研报告。
规则：
1. 若证据足以回答用户问题：直接写报告；不要把整篇答案写成澄清问卷。
2. 若关键信息仍不清楚、且会实质改变结论：可以再提问（简短、具体、可操作）；也可在报告末尾列出待确认点。能部分回答时先写已有发现，再问缺口。
3. 若你采用了假设（例如默认某位点），必须明确标注假设，并说明换位点后结论可能变化。
4. 不要套用固定 WHO/WHEN/WHERE/WHY 标题。区分数据库事实 vs 机制推理；标注证据级别。引用：${citeList}
5. 工具标注：[empty_result]=库中无记录；[missing_params]=缺参；[call_bug]=调用失败。
已解析靶点：${memoryPromptBlock(memory)}。`
      : `You are a PTM deep-research expert. Prefer a sectioned, well-cited report grounded in collected evidence.
Rules:
1. If evidence is enough, write the report — do not replace the whole answer with a questionnaire.
2. If a critical ambiguity remains that would change conclusions, you MAY ask again (brief, concrete); or list open questions at the end. When partially answerable, report findings first, then ask.
3. State any assumptions explicitly.
4. No forced WHO/WHEN/WHERE/WHY headings. Separate facts vs hypotheses; label evidence levels. Citations: ${citeList}
5. Tool tags: [empty_result]=no DB records; [missing_params]=need args; [call_bug]=call failed.
Resolved target: ${memoryPromptBlock(memory)}.`;

  const evidence = [
    memory.findings_summary,
    artifacts.catalogForPrompt(15),
    artifacts.getLiteratureContext(),
  ].join("\n\n");

  const messages: Array<{ role: "system" | "user" | "assistant"; content: string }> = [
    { role: "system", content: `${system}\n\n${skills}\n${catalog.slice(0, 3500)}` },
    ...history.slice(-6).map((h) => ({
      role: h.role as "user" | "assistant",
      content: h.content,
    })),
    {
      role: "user",
      content: `Research question: ${question}\n\nEvidence collected:\n${evidence.slice(0, 14000)}`,
    },
  ];

  const llm = getLlm();
  try {
    const { content } = await llm.chatCompletion(messages, { maxTokens: 8192, temperature: 0.35 });
    return content;
  } catch {
    const { content } = await getLlm().chatCompletion(messages, { maxTokens: 8192 });
    return content;
  }
}

function chunkText(text: string, size = 80): string[] {
  const chunks: string[] = [];
  for (let i = 0; i < text.length; i += size) chunks.push(text.slice(i, i + size));
  return chunks;
}
