import { ArtifactStore } from "../context/artifacts.js";
import { addFinding, InvestigationMemory, mergeEntities, parseEntities } from "../context/memory.js";
import { SessionState } from "../context/session.js";
import {
  callQptmTool,
  searchLiteratureArticles,
  readQptmResource,
  webSearch,
} from "../mcp/hub.js";
import { loadSkills, skillsForMode } from "../skills/loader.js";
import { getLlm } from "../llm/client.js";
import type { AgentEvent } from "../sse.js";
import { mergeCitation, type Citation } from "./citations.js";
import {
  classifyQueryMode,
  detectLang,
  gateReply,
  needsLiterature,
  needsWebSearch,
} from "./gate.js";
import { retrieveTools } from "./retriever.js";
import { generateFollowUps } from "./followups.js";
import {
  applyResolvedIdentity,
  invokeArgumentsJson,
  resolveSessionTarget,
  resolvedBanner,
} from "./resolve-target.js";
import { sanitizeUserVisibleText } from "./protocol.js";

function phase(phase: string, label: string): AgentEvent {
  return { type: "phase_update", phase, label };
}

async function executeQptmTool(
  toolHint: string,
  question: string,
  memory: InvestigationMemory,
  artifacts: ArtifactStore,
  citations: Citation[],
): Promise<{ summary: string; tool: string; success: boolean; error_kind?: string | null }> {
  const entityMap: Record<string, string> = {
    qptm_kinases: "kinase",
    qptm_site_conditions: "condition",
    qptm_search: "site",
    pubtator_literature_search: "literature",
  };
  let entity = "site";
  for (const [t, e] of Object.entries(entityMap)) {
    if (toolHint.includes(t) || toolHint === t) entity = e;
  }

  const args: Record<string, unknown> = {
    entity,
    query: question,
    gene: memory.gene || "",
    position: memory.position || 0,
    uniprot_ac: memory.uniprot_ac || "",
  };

  let result;
  if (toolHint === "qptm_search" || toolHint === "qptm_get") {
    result = await callQptmTool(toolHint, args);
  } else {
    result = await callQptmTool("qptm_invoke", {
      tool_name: toolHint,
      arguments_json: invokeArgumentsJson(memory, question),
    });
  }
  applyResolvedIdentity(memory, result);

  const summary = result.summary || "done";
  const kindTag = result.error_kind ? ` [${result.error_kind}]` : "";
  addFinding(memory, toolHint, `${summary}${kindTag}`);
  artifacts.add("db_result", `${toolHint}: ${question}`, summary, { tool: toolHint, arguments: args });
  mergeCitation(citations, toolHint);
  return {
    summary,
    tool: toolHint,
    success: result.success,
    error_kind: result.error_kind,
  };
}

export async function* runQA(
  userMessage: string,
  history: Array<{ role: string; content: string }>,
  session: SessionState,
): AsyncGenerator<AgentEvent> {
  const memory = session.memory;
  const artifacts = session.artifacts;
  const lang = detectLang(userMessage);
  const parsed = parseEntities(userMessage);
  mergeEntities(memory, parsed, userMessage);
  memory.query_mode = classifyQueryMode(userMessage, parsed);

  yield phase("planning", lang === "zh" ? "理解问题" : "Understanding question");

  const gate = gateReply(memory.query_mode as Parameters<typeof gateReply>[0], lang);
  if (gate) {
    yield phase("synthesis", lang === "zh" ? "回复" : "Reply");
    yield { type: "text", content: gate };
    yield { type: "done" };
    return;
  }

  const skills = loadSkills(skillsForMode("qa", userMessage));

  if (memory.query_mode === "concept") {
    yield phase("synthesis", lang === "zh" ? "撰写回答" : "Writing answer");
    const answer = sanitizeUserVisibleText(
      await synthesizeConcept(userMessage, history, skills, lang),
      lang,
    );
    for (const chunk of chunkText(answer)) yield { type: "text", content: chunk };
    const followUps = await generateFollowUps(userMessage, answer, memory, artifacts, "qa", []);
    yield { type: "follow_up_questions", questions: followUps };
    yield { type: "done" };
    return;
  }

  yield phase("retrieving_tools", lang === "zh" ? "准备工具" : "Preparing tools");
  const sourcesCatalog = await readQptmResource("qptm://sources");

  const toolsUsed: string[] = [];
  const citations: Citation[] = [...session.citations];

  if (artifacts.shouldSkipLiteratureSearch(userMessage)) {
    yield phase("synthesis", lang === "zh" ? "基于已有文献回答" : "Answering from cached literature");
    const litCtx = artifacts.getLiteratureContext();
    const synth = resolvedBanner(memory, lang) + sanitizeUserVisibleText(
      await synthesizeQA(userMessage, history, memory, skills, sourcesCatalog, litCtx, citations, lang),
      lang,
    );
    for (const chunk of chunkText(synth)) yield { type: "text", content: chunk };
    yield { type: "sources", citations };
    const followUps = await generateFollowUps(userMessage, synth, memory, artifacts, "qa", toolsUsed);
    yield { type: "follow_up_questions", questions: followUps };
    session.citations = citations;
    yield { type: "done" };
    return;
  }

  yield phase("database", lang === "zh" ? "查询数据库" : "Querying databases");

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

  const toolList = retrieveTools(userMessage, memory, 6);

  const parallel = toolList.slice(0, 3);
  for (const tool of parallel) {
    yield {
      type: "tool_call",
      tool_name: tool,
      arguments: {
        query: userMessage,
        gene: memory.gene,
        uniprot_ac: memory.uniprot_ac,
        position: memory.position,
      },
      kind: "database",
    };
    const { summary, success, error_kind } = await executeQptmTool(
      tool,
      userMessage,
      memory,
      artifacts,
      citations,
    );
    toolsUsed.push(tool);
    yield {
      type: "tool_result",
      payload: { tool_name: tool, success, summary, error_kind, data_count: 1 },
      kind: "database",
    };
  }

  let litSummary = "";
  if (needsLiterature(userMessage)) {
    yield phase("literature", lang === "zh" ? "检索文献" : "Searching literature");
    const start = Date.now();
    litSummary = await searchLiteratureArticles(userMessage);
    const elapsed = (Date.now() - start) / 1000;
    artifacts.add("literature_search", userMessage, litSummary.slice(0, 1500));
    yield {
      type: "literature_search",
      round: 1,
      query: userMessage,
      papers_found: (litSummary.match(/PMID/gi) || []).length,
      elapsed_s: elapsed,
    };
    mergeCitation(citations, "pubtator_literature_search");
  }

  let webSummary = "";
  if (needsWebSearch(userMessage)) {
    webSummary = await webSearch(userMessage);
    artifacts.add("web_search", userMessage, webSummary.slice(0, 1500));
  }

  yield phase("synthesis", lang === "zh" ? "撰写回答" : "Writing answer");
  const extraCtx = [litSummary, webSummary].filter(Boolean).join("\n---\n");
  let answer = await synthesizeQA(
    userMessage,
    history,
    memory,
    skills,
    sourcesCatalog,
    extraCtx,
    citations,
    lang,
  );
  answer = resolvedBanner(memory, lang) + sanitizeUserVisibleText(answer, lang);
  for (const chunk of chunkText(answer)) yield { type: "text", content: chunk };

  yield { type: "sources", citations };
  session.citations = citations;

  const followUps = await generateFollowUps(userMessage, answer, memory, artifacts, "qa", toolsUsed);
  yield { type: "follow_up_questions", questions: followUps };
  yield { type: "done" };
}

async function synthesizeQA(
  question: string,
  history: Array<{ role: string; content: string }>,
  memory: InvestigationMemory,
  skills: string,
  sourcesCatalog: string,
  extraEvidence: string,
  citations: Citation[],
  lang: "zh" | "en",
): Promise<string> {
  const citeList = citations.map((c) => `${c.id}: ${c.database}`).join(", ");
  const system =
    lang === "zh"
      ? `你是 qPTM 生物学专家助手，只回答生物学问题。回答简洁准确，区分实验数据与预测结果。引用数据库名（${citeList}）。不要冗长综述。
工具结果标注含义：[empty_result]=库中无记录，不是缺参数；[missing_params]=缺少参数；[call_bug]=调用失败。已解析的靶点（gene/UniProt/site）不得再说“缺少 UniProt AC”。`
      : `You are qPTM biology expert. Answer concisely; distinguish experimental vs predicted evidence. Cite databases (${citeList}). No lengthy reviews.
Tool tags: [empty_result]=no records in DB (not a missing ID); [missing_params]=need more arguments; [call_bug]=call failed. If gene/UniProt/site is already resolved, do NOT say UniProt AC is missing.`;

  const userBlock = [
    skills,
    `Sources catalog:\n${sourcesCatalog.slice(0, 4000)}`,
    `Memory: gene=${memory.gene || ""} UniProt=${memory.uniprot_ac || ""} site=${memory.position || ""} ptm=${memory.ptm_type || ""}`,
    memory.findings_summary,
    extraEvidence ? `Evidence:\n${extraEvidence.slice(0, 6000)}` : "",
    `Question: ${question}`,
  ].join("\n\n");

  const messages: Array<{ role: "system" | "user" | "assistant"; content: string }> = [
    { role: "system", content: system },
    ...history.slice(-8).map((h) => ({
      role: h.role as "user" | "assistant",
      content: h.content,
    })),
    { role: "user", content: userBlock },
  ];

  const llm = getLlm();
  const { content } = await llm.chatCompletion(messages, { maxTokens: 2048, temperature: 0.35 });
  return content;
}

async function synthesizeConcept(
  question: string,
  history: Array<{ role: string; content: string }>,
  skills: string,
  lang: "zh" | "en",
): Promise<string> {
  const system =
    lang === "zh"
      ? `你是 qPTM 生物学教育助手，回答分子与细胞生物学概念问题（蛋白质、基因、细胞、翻译后修饰等）。
**不要**拒绝生物学相关问题。回答清晰、结构化；若与 PTM 研究相关可简要提及联系。
**不要**在文末追加示例追问——界面会单独展示推荐问题。`
      : `You are the qPTM biology education assistant for molecular and cell biology concepts (proteins, genes, cells, PTMs).
Do NOT refuse biology-related questions. Be clear and structured; mention PTM links when natural.
Do NOT add follow-up example questions at the end — the UI shows them separately.`;

  const messages: Array<{ role: "system" | "user" | "assistant"; content: string }> = [
    { role: "system", content: system },
    ...history.slice(-8).map((h) => ({
      role: h.role as "user" | "assistant",
      content: h.content,
    })),
    { role: "user", content: `${skills}\n\nQuestion: ${question}` },
  ];

  const llm = getLlm();
  const { content } = await llm.chatCompletion(messages, { maxTokens: 2048, temperature: 0.35 });
  return content;
}

function chunkText(text: string, size = 80): string[] {
  const chunks: string[] = [];
  for (let i = 0; i < text.length; i += size) chunks.push(text.slice(i, i + size));
  return chunks;
}
