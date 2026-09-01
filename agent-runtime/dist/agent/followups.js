import { getLlm } from "../llm/client.js";
import { detectLang } from "./gate.js";
export async function generateFollowUps(question, answer, memory, artifacts, mode, toolsUsed) {
    const lang = detectLang(question);
    const artifactCatalog = artifacts.catalogForPrompt(8);
    const toolsLine = toolsUsed.length ? toolsUsed.join(", ") : "none";
    const drRule = mode === "qa"
        ? lang === "zh"
            ? "其中 2-3 条 intent 必须为 deep_research，用于引导用户做深度调研。"
            : "Include 2-3 items with intent deep_research to guide deeper investigation."
        : lang === "zh"
            ? "全部 intent 为 qa（用户已在深度调研模式）。"
            : "All intent must be qa (user is already in deep research).";
    const prompt = lang === "zh"
        ? `根据本轮调研生成 5 个后续问题。必须结合实际用过的数据库与文献，不要泛泛而谈。
${drRule}
输出 JSON: [{"text":"...","intent":"qa"|"deep_research"}]

调查上下文: ${memory.gene || ""} ${memory.position || ""}
已用工具: ${toolsLine}
Artifacts: ${artifactCatalog}

用户问题: ${question}
回答摘要: ${(answer || "").slice(0, 2500)}`
        : `Generate 5 follow-up questions grounded in this investigation. Use actual databases/literature touched — no generic templates.
${drRule}
Output JSON: [{"text":"...","intent":"qa"|"deep_research"}]

Context: ${memory.gene || ""} ${memory.position || ""}
Tools used: ${toolsLine}
Artifacts: ${artifactCatalog}

Question: ${question}
Answer excerpt: ${(answer || "").slice(0, 2500)}`;
    try {
        const llm = getLlm();
        const { content } = await llm.chatCompletion([{ role: "user", content: prompt }], {
            maxTokens: 800,
            temperature: 0.4,
        });
        const parsed = parseFollowUpJson(content);
        if (parsed.length >= 3)
            return normalizeFollowUps(parsed, mode, lang);
    }
    catch {
        /* fallback below */
    }
    return fallbackFollowUps(mode, lang, memory);
}
function parseFollowUpJson(raw) {
    let text = raw.trim();
    if (text.startsWith("```")) {
        text = text.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "");
    }
    try {
        const data = JSON.parse(text);
        const arr = Array.isArray(data) ? data : [];
        return arr
            .map((item) => {
            if (typeof item === "string")
                return { text: item, intent: "qa" };
            if (item && typeof item === "object" && "text" in item) {
                const t = String(item.text);
                const intent = item.intent === "deep_research" ? "deep_research" : "qa";
                return { text: t, intent };
            }
            return null;
        })
            .filter((x) => x !== null && x.text.length >= 8);
    }
    catch {
        return [];
    }
}
function normalizeFollowUps(items, mode, lang) {
    let out = items.slice(0, 5);
    if (mode === "qa") {
        const drCount = out.filter((q) => q.intent === "deep_research").length;
        if (drCount < 2) {
            const extras = fallbackFollowUps("qa", lang, emptyMem()).filter((q) => q.intent === "deep_research");
            for (const e of extras) {
                if (out.length >= 5)
                    break;
                if (!out.some((x) => x.text === e.text))
                    out.push(e);
            }
        }
    }
    while (out.length < 5) {
        const fb = fallbackFollowUps(mode, lang, emptyMem());
        for (const f of fb) {
            if (!out.some((x) => x.text === f.text))
                out.push(f);
            if (out.length >= 5)
                break;
        }
    }
    return out.slice(0, 5);
}
function emptyMem() {
    return {
        gene: null,
        uniprot_ac: null,
        position: null,
        ptm_type: "phosphorylation",
        organism: "human",
        pmid: null,
        mutation_label: null,
        query_mode: null,
        findings_summary: "",
        entities: {},
    };
}
function fallbackFollowUps(mode, lang, memory) {
    const site = memory.gene && memory.position ? `${memory.gene} ${memory.position}` : "TP53 S15";
    if (lang === "zh") {
        const qa = [
            { text: `${site} 在哪些实验条件下被修饰？`, intent: "qa" },
            { text: `哪些激酶可能磷酸化 ${site}？`, intent: "qa" },
            {
                text: `对 ${site} 做全面深度调研（激酶、定量、功能疾病）`,
                intent: "deep_research",
            },
            {
                text: `综合数据库与文献，深度解析 ${site} 的调控机制`,
                intent: "deep_research",
            },
            { text: `${site} 与疾病或药物调控有何关联？`, intent: "qa" },
        ];
        return mode === "deep_research" ? qa.map((q) => ({ ...q, intent: "qa" })) : qa;
    }
    const qa = [
        { text: `Under which conditions is ${site} modified?`, intent: "qa" },
        { text: `Which kinases may phosphorylate ${site}?`, intent: "qa" },
        {
            text: `Run deep research on ${site} (kinases, quantitation, function/disease)`,
            intent: "deep_research",
        },
        {
            text: `Deep dive: integrate databases and literature for ${site} regulation`,
            intent: "deep_research",
        },
        { text: `What disease or drug links exist for ${site}?`, intent: "qa" },
    ];
    return mode === "deep_research" ? qa.map((q) => ({ ...q, intent: "qa" })) : qa;
}
