import { cfg } from "../config.js";
import { addFinding, mergeEntities, memoryPromptBlock, parseEntities, } from "../context/memory.js";
import { callQptmTool, biomcpSearchArticle, biomcpGetArticle, readQptmResource, webSearch, } from "../mcp/hub.js";
import { loadSkills, skillsForMode } from "../skills/loader.js";
import { getLlm } from "../llm/client.js";
import { mergeCitation } from "./citations.js";
import { detectLang } from "./gate.js";
import { retrieveToolsDeep } from "./retriever.js";
import { generateFollowUps } from "./followups.js";
function phase(p, label) {
    return { type: "phase_update", phase: p, label };
}
export async function* runDeepResearch(userMessage, history, session) {
    const memory = session.memory;
    const artifacts = session.artifacts;
    const lang = detectLang(userMessage);
    mergeEntities(memory, parseEntities(userMessage));
    yield phase("planning", lang === "zh" ? "制定调研计划" : "Planning research");
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
    const citations = [...session.citations];
    const toolsUsed = [];
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
                arguments_json: JSON.stringify({
                    gene: memory.gene,
                    position: memory.position,
                    uniprot_ac: memory.uniprot_ac,
                    query: userMessage,
                }),
            });
            addFinding(memory, tool, result.summary);
            artifacts.add("db_result", `${tool}`, result.summary, { tool });
            toolsUsed.push(tool);
            mergeCitation(citations, tool);
            yield {
                type: "tool_result",
                payload: {
                    tool_name: tool,
                    success: result.success,
                    summary: result.summary,
                    data_count: 1,
                },
                kind: "database",
            };
        }
    }
    yield phase("literature", lang === "zh" ? "文献检索与整合" : "Literature search");
    const litQueries = [
        userMessage,
        memory.gene && memory.position ? `${memory.gene} ${memory.position} phosphorylation` : "",
    ].filter(Boolean);
    const pmids = [];
    for (let i = 0; i < litQueries.length; i++) {
        const q = litQueries[i];
        const start = Date.now();
        const lit = await biomcpSearchArticle(q);
        const found = (lit.match(/PMID[:\s]*(\d{7,8})/gi) || []).length;
        artifacts.add("literature_search", q, lit.slice(0, 2000), {
            pmids: [...lit.matchAll(/(\d{7,8})/g)].slice(0, 10).map((m) => m[1]),
        });
        for (const m of lit.matchAll(/(\d{7,8})/g)) {
            if (pmids.length < 5)
                pmids.push(m[1]);
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
        const abstract = await biomcpGetArticle(`pmid:${pmid}`);
        artifacts.add("paper", `PMID:${pmid}`, abstract.slice(0, 2000), { pmids: [pmid] });
    }
    const web = await webSearch(`${userMessage} PTM site`);
    if (web && !web.startsWith("Web search failed")) {
        artifacts.add("web_search", userMessage, web.slice(0, 1500));
    }
    yield phase("synthesis", lang === "zh" ? "撰写深度调研报告" : "Writing research report");
    const report = await synthesizeDeepReport(userMessage, history, memory, artifacts, skills, sourcesCatalog, citations, lang);
    for (const chunk of chunkText(report, 120)) {
        yield { type: "text", content: chunk };
    }
    yield { type: "sources", citations };
    session.citations = citations;
    const followUps = await generateFollowUps(userMessage, report, memory, artifacts, "deep_research", toolsUsed);
    yield { type: "follow_up_questions", questions: followUps };
    yield { type: "done" };
}
async function buildPlan(question, memory, skills, catalog, lang) {
    const tools = retrieveToolsDeep(question, memory);
    const prompt = lang === "zh"
        ? `为 PTM 深度调研生成 JSON 计划。问题：${question}\n上下文：${memoryPromptBlock(memory)}\n可用工具：${tools.join(", ")}\n\n输出: {"summary":"...","steps":[{"step":1,"title":"...","entity":"kinase|condition|...","tools":["tool_name"],"rationale":"..."}]}\n最多 6 步。`
        : `Create JSON plan for PTM deep research. Question: ${question}\nContext: ${memoryPromptBlock(memory)}\nTools: ${tools.join(", ")}\n\nOutput: {"summary":"...","steps":[...]} max 6 steps.`;
    try {
        const llm = getLlm();
        const { content } = await llm.chatCompletion([
            { role: "system", content: `${skills}\n${catalog.slice(0, 3000)}` },
            { role: "user", content: prompt },
        ], { maxTokens: 1200, temperature: 0.2 });
        const parsed = JSON.parse(content.replace(/```json?\s*|\s*```/g, "").trim());
        if (parsed.steps?.length) {
            return {
                summary: parsed.summary || question,
                steps: parsed.steps.slice(0, cfg.drMaxPlanSteps),
            };
        }
    }
    catch {
        /* fallback */
    }
    return {
        summary: question,
        steps: [
            { step: 1, title: "Regulators", entity: "kinase", tools: tools.slice(0, 3), rationale: "WHO" },
            { step: 2, title: "Quantitation", entity: "condition", tools: tools.slice(3, 5), rationale: "WHEN" },
            { step: 3, title: "Function", entity: "function", tools: tools.slice(5, 8), rationale: "WHY" },
        ].filter((s) => s.tools.length),
    };
}
async function synthesizeDeepReport(question, history, memory, artifacts, skills, catalog, citations, lang) {
    const citeList = citations.map((c) => `${c.id}: ${c.database}`).join(", ");
    const system = lang === "zh"
        ? `你是 PTM 深度调研专家。撰写详尽、分节、引用充分的报告。明确区分：数据库事实 vs 机制推理假设。标注证据级别（实验/预测/策展）。引用：${citeList}`
        : `PTM deep research expert. Write a detailed, sectioned, well-cited report. Separate database facts from mechanistic hypotheses. Label evidence levels. Citations: ${citeList}`;
    const evidence = [
        memory.findings_summary,
        artifacts.catalogForPrompt(15),
        artifacts.getLiteratureContext(),
    ].join("\n\n");
    const messages = [
        { role: "system", content: `${system}\n\n${skills}\n${catalog.slice(0, 3500)}` },
        ...history.slice(-6).map((h) => ({
            role: h.role,
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
    }
    catch {
        const { content } = await getLlm().chatCompletion(messages, { maxTokens: 8192 });
        return content;
    }
}
function chunkText(text, size = 80) {
    const chunks = [];
    for (let i = 0; i < text.length; i += size)
        chunks.push(text.slice(i, i + size));
    return chunks;
}
