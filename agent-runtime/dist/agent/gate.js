const GREETING_RE = /^(hi|hello|hey|你好|您好|早上好|晚上好)\b/i;
const HELP_RE = /^(help|如何使用|怎么用|帮助)\b/i;
const CAPABILITY_RE = /what can you do|你能做什么|功能介绍|capabilities/i;
/** Chinese biology terms — no `\b` (JS word boundaries do not work on CJK). */
const BIO_KEYWORDS_ZH = /蛋白质|蛋白|氨基酸|肽|酶|基因|染色体|细胞|核酸|转录|翻译|复制|代谢|凋亡|自噬|免疫|膜|受体|核糖体|生物体|激酶|磷酸化|翻译后修饰|位点|通路|疾病|癌症|文献|修饰|信号|分子|生物学|细胞器|线粒体|细胞核|DNA|RNA/i;
/** English biology terms. */
const BIO_KEYWORDS_EN = /\b(protein|gene|kinase|phospho|ptm|post-translational|ubiquitin|acetyl|methyl|site|uniprot|pathway|cell|organism|mutation|disease|cancer|enzyme|peptide|amino\s+acid|dna|rna|chromosome|apoptosis|receptor|antibody|histone|metabolism|signaling|signalling)\b/i;
const CONCEPT_INTENT_RE = /什么是|何为|介绍一下?|解释一下?|what\s+is|what\s+are|define|explain|overview\s+of|概念|基础|入门|significance\s+of|importance\s+of|role\s+of|meaning\s+of|tell\s+me\s+about/i;
const CONCEPT_TOPIC_RE = /蛋白质|蛋白|ptm|翻译后修饰|磷酸化|激酶|细胞|基因|酶|protein|phosphorylation|kinase|cell|gene|enzyme|post-translational|amino\s+acid|peptide|dna|rna/i;
const EDUCATIONAL_ZH_RE = /的意义|的作用|的功能|是什么|有啥用|为什么重要|研究意义|有什么作用|有何作用|指什么/i;
function isBiologyRelated(message, entities) {
    if (entities.gene || entities.uniprot_ac || entities.pmid)
        return true;
    return BIO_KEYWORDS_ZH.test(message) || BIO_KEYWORDS_EN.test(message);
}
function isConceptQuestion(message, entities) {
    if (entities.gene || entities.position)
        return false;
    const hasIntent = CONCEPT_INTENT_RE.test(message) ||
        EDUCATIONAL_ZH_RE.test(message) ||
        /\b(meaning|significance|importance|purpose)\b/i.test(message);
    if (!hasIntent)
        return false;
    return CONCEPT_TOPIC_RE.test(message) || !entities.uniprot_ac;
}
export function detectLang(text) {
    const zh = (text.match(/[\u4e00-\u9fff]/g) || []).length;
    const latin = (text.match(/[a-z]/gi) || []).length;
    return zh >= 2 && zh >= latin * 0.35 ? "zh" : "en";
}
export function classifyQueryMode(message, entities) {
    const m = (message || "").trim();
    if (!m)
        return "research";
    if (GREETING_RE.test(m))
        return "greeting";
    if (HELP_RE.test(m))
        return "help";
    if (CAPABILITY_RE.test(m))
        return "capability";
    if (/collect|采集|pmid.*抽取|literature collection/i.test(m) && entities.pmid)
        return "collection";
    if (entities.pmid && /pmid|文献|paper|abstract/i.test(m))
        return "pmid_lookup";
    if (/literature|pubmed|论文|文献综述|recent papers/i.test(m))
        return "literature";
    if (/这些|上面|继续|对比|compare|follow up|刚才/i.test(m))
        return "followup";
    if (!isBiologyRelated(m, entities)) {
        return "off_topic";
    }
    if (isConceptQuestion(m, entities))
        return "concept";
    if (/什么是|what is|explain|概念|机制概述|overview of/i.test(m) && !entities.position)
        return "concept";
    return "research";
}
export function gateReply(mode, lang) {
    if (mode === "greeting") {
        return lang === "zh"
            ? "你好！我是 qPTM 生物学助手，可解答翻译后修饰、激酶底物、定量动力学与疾病关联等问题。试试：「哪些激酶磷酸化 AKT1 S473？」"
            : "Hello! I'm the qPTM biology assistant for PTM sites, kinases, quantitative dynamics, and disease links. Try: \"Which kinases phosphorylate AKT1 S473?\"";
    }
    if (mode === "help") {
        return lang === "zh"
            ? "在输入框提问 PTM 相关问题；点击 **Deep Research** 按钮可进行深度调研（澄清需求后综合多数据库与文献）。上传 PDF 可进入文献数据采集流程。"
            : "Ask PTM questions in the chat box. Use **Deep Research** for in-depth investigation across databases and literature. Upload a PDF to start literature data collection.";
    }
    if (mode === "capability") {
        return lang === "zh"
            ? "我整合 qPTM 定量库与 30+ PTM 相关数据库，支持激酶/底物、条件定量、定位、功能疾病、药物调控等；可联网检索与文献检索。深度调研请使用 Deep Research。"
            : "I integrate qPTM quantitative data with 30+ PTM databases (kinases, conditions, localization, disease, drugs) plus web and literature search. Use Deep Research for comprehensive reports.";
    }
    if (mode === "off_topic") {
        return lang === "zh"
            ? "我主要回答分子与细胞生物学、蛋白质与翻译后修饰相关问题。例如：「蛋白质在细胞中有什么作用？」或「TP53 S15 在 DNA 损伤后如何被磷酸化？」"
            : "I focus on molecular and cell biology, proteins, and post-translational modifications. For example: \"What is the role of proteins in cells?\" or \"How is TP53 S15 phosphorylated after DNA damage?\"";
    }
    return null;
}
export function needsLiterature(message) {
    return /literature|paper|pubmed|recent studies|文献|论文|研究进展/i.test(message);
}
export function needsWebSearch(message) {
    return /latest|recent news|2024|2025|2026|最新|进展|trend/i.test(message);
}
