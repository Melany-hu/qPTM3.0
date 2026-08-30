"""Conversational gate — classify query mode and static replies."""

from __future__ import annotations

import re
from typing import Any

from app.agent.entities import is_plausible_gene, parse_query_entities
from app.models.schemas import WorkflowStage
from app.workflow.stages import _STAGE_KEYWORDS, _keyword_hit

def _mentions_llps(message: str) -> bool:
    """Detect liquid–liquid phase separation (LLPS) intent in a query."""
    llps_keywords = (
        "phase separation", "llps", "condensate", "droplet", "dscope",
        "phasllps", "phosllps", "membraneless", "stress granule", "p-body",
        "相分离", "液液相分离", "凝聚体", "无膜细胞器",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in llps_keywords)


def _mentions_ppi(message: str) -> bool:
    """Detect protein–protein interaction intent."""
    ppi_keywords = (
        "ppi", "protein-protein", "protein interaction", "interact", "interactor",
        "binding partner", "complex", "string", "biogrid", "intact",
        "互作", "相互作用", "结合伙伴", "蛋白互作", "复合物",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in ppi_keywords)


def _mentions_pathway(message: str) -> bool:
    """Detect pathway / signaling-map intent."""
    pathway_keywords = (
        "pathway", "pathways", "signaling", "signalling", "reactome", "kegg",
        "pathbank", "smpdb", "cascade", "transduction", "metabolic map",
        "通路", "信号通路", "信号转导", "代谢通路",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in pathway_keywords)


def _mentions_mutation(message: str, entities: dict[str, Any] | None = None) -> bool:
    """Detect mutation / variant / PTM-disruption precision-medicine intent."""
    if entities and entities.get("mutation_label"):
        return True
    mut_keywords = (
        "mutation", "mutations", "mutant", "missense", "somatic", "germline",
        "variant", "variants", "clinvar", "mc3", "pcawg", "ptmvar", "nssnp",
        "snp", "snv", "disrupt", "disrupts", "destroy", "abolish", "rewiring",
        "rewire", "loss of phosphorylation", "site loss", "site gain",
        "kinase-dead", "kinase dead", "gain-of-function", "loss-of-function",
        "gof", "lof", "enzyme activity", "kinase activity",
        "突变", "体细胞", "胚系", "变异", "破坏", "废除", "位点丢失", "位点获得",
        "重布线", "激酶重连", "激酶失活", "酶活性", "激酶活性",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in mut_keywords)


def _build_pubtator_query(entities: dict[str, Any], message: str) -> str:
    """Build a PubTator keyword query from parsed entities and user context."""
    if entities.get("pubtator_query"):
        return str(entities["pubtator_query"])[:240]
    if entities.get("pmid"):
        return f"PMID:{entities['pmid']}"
    # Field/method surveys: prefer English PubMed keywords
    if entities.get("query_mode") == QUERY_MODE_LITERATURE or _is_literature_survey_question(
        message or "", entities
    ):
        return _literature_pubtator_query(message or entities.get("query") or "")

    parts: list[str] = []
    gene = entities.get("gene")
    position = entities.get("position")
    ptm_type = (entities.get("ptm_type") or "").strip()
    uniprot = entities.get("uniprot_ac")
    mut_label = entities.get("mutation_label")

    if gene:
        parts.append(str(gene))
    if mut_label:
        parts.append(str(mut_label))
    elif position:
        parts.append(str(position))
    if ptm_type:
        parts.append(ptm_type)
    if (
        mut_label
        or entities.get("narrative") == "mutation_precision"
        or _mentions_mutation(message or entities.get("query") or "", entities)
    ):
        parts.append("mutation")
        parts.append("cancer")
    if uniprot and not gene:
        parts.append(str(uniprot))

    if parts:
        return " ".join(parts)

    # Fall back to the user message with workflow boilerplate stripped
    cleaned = re.sub(
        r"\b(who|when|where|why|stage|search|query|tell me|what|which|how)\b",
        " ",
        message,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:240] if cleaned else message.strip()[:240]


def _mentions_domain(message: str) -> bool:
    """Detect protein domain / family architecture intent."""
    domain_keywords = (
        "domain", "domains", "family", "families", "interpro", "pfam",
        "architecture", "motif", "superfamily", "fold",
        "located in a functional domain", "in a functional domain",
        "结构域", "蛋白家族", "结构域架构", "功能域",
    )
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in domain_keywords)


def _mentions_stability(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "stabiliz", "destabiliz", "stability", "half-life", "half life",
        "degradation", "turnover", "mdm2 affinity",
        "稳定", "去稳定", "降解", "半衰期",
    )
    return any(k in msg_lower for k in keys)


def _mentions_nls(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "nls", "nes", "nuclear localization signal", "nuclear export signal",
        "localization signal", "核定位信号", "核输出信号", "核定位",
    )
    return any(k in msg_lower for k in keys)


def _mentions_drug(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "drug", "drugs", "inhibitor", "compound", "dose-response",
        "decryptm", "pmads", "drugbank", "treatment affect",
        "药物", "抑制剂", "化合物",
    )
    return any(k in msg_lower for k in keys)


def _mentions_crosstalk(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "crosstalk", "cross-talk", "cross talk", "ptm-ptm", "ptm–ptm",
        "simultaneously phosphorylated", "simultaneously acetylated",
        "串扰", "协同修饰", "同时磷酸化", "同时乙酰化",
    )
    return any(k in msg_lower for k in keys)


def _mentions_structure_gap(message: str) -> bool:
    """Structural accessibility / PPI interface — AlphaFold covers global structure only."""
    msg_lower = message.lower()
    keys = (
        "alphafold", "plddt", "predicted structure", "structure prediction",
        "buried", "exposed", "solvent accessible", "sasa", "surface accessibility",
        "protein surface", "ppi interface", "interaction interface",
        "structural context", "structure context",
        "埋藏", "暴露", "溶剂可及", "表面可及", "相互作用界面", "结构上下文",
    )
    return any(k in msg_lower for k in keys)


def _mentions_gwas(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "gwas", "genome-wide", "genome wide", "snp", "risk allele", "trait association",
        "全基因组", "关联研究", "风险等位基因",
    )
    return any(k in msg_lower for k in keys)


def _mentions_tf_motif(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "transcription factor", "tf binding", "tf motif", "dna binding",
        "jaspar", "pwm", "转录因子", "结合基序",
    )
    return any(k in msg_lower for k in keys)


def _mentions_proteoform(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "proteoform", "proteoforms", "combinatorial ptm", "combinatorial modification",
        "simultaneously modified", "co-modified", "comodified",
        "蛋白变体", "蛋白质变体", "组合修饰", "同时修饰",
    )
    return any(k in msg_lower for k in keys)


def _mentions_conservation(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "conserved", "conservation", "ortholog", "homolog", "across species",
        "in mouse", "in rat", "in yeast",
        "保守", "同源", "跨物种", "小鼠中",
    )
    return any(k in msg_lower for k in keys)


def _mentions_disease(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "disease", "cancer", "tumor", "tumour", "clinical", "patient",
        "biomarker", "li-fraumeni",
        "疾病", "癌症", "肿瘤", "临床", "标志物",
    )
    return any(k in msg_lower for k in keys)


def _user_provided_kinase(message: str) -> bool:
    """User already named the writer enzyme — skip WHO rediscovery."""
    msg_lower = message.lower()
    # Questions asking *which* kinase must never be treated as provided
    if re.search(
        r"(which kinase|what (?:enzyme|kinase)|who phosphorylates|"
        r"哪个激酶|什么酶|激酶是什么|谁磷酸化)",
        msg_lower,
    ):
        return False
    # Require a concrete gene-like token after "by" / "是" (ASCII or CJK name),
    # never bare interrogatives (什么/哪/谁) — ``\w`` matches CJK in Unicode mode.
    patterns = (
        r"phosphorylated by\s+[A-Za-z][A-Za-z0-9_-]{1,20}",
        r"acetylated by\s+[A-Za-z][A-Za-z0-9_-]{1,20}",
        r"ubiquitinated by\s+[A-Za-z][A-Za-z0-9_-]{1,20}",
        r"modified by\s+[A-Za-z][A-Za-z0-9_-]{1,20}",
        r"kinase is\s+[A-Za-z][A-Za-z0-9_-]{1,20}",
        r"由[A-Za-z\u4e00-\u9fff]{2,20}磷酸化",
        r"被[A-Za-z\u4e00-\u9fff]{2,20}磷酸化",
        r"激酶是(?!什么|哪|谁)([A-Za-z][A-Za-z0-9_-]{1,20})",
    )
    return any(re.search(p, msg_lower) for p in patterns)


def _user_provided_when(message: str) -> bool:
    """User already stated the condition/stimulus — skip WHEN rediscovery."""
    msg_lower = message.lower()
    patterns = (
        r"i know .+(phosphorylated|acetylated|modified|ubiquitinated).+(after|under|upon|following)",
        r"already know .+(after|under|upon|following)",
        r"(phosphorylated|acetylated|modified)\s+after\s+[\w\s-]{0,40}(damage|treatment|stress|stimulation)",
        r"已知.+(磷酸化|乙酰化|修饰).+(后|下|时)",
        r"我(已经)?知道.+(磷酸化|乙酰化).+(后|下)",
    )
    # Only treat as "provided WHEN" when user is asking for WHO/WHY, not asking WHEN itself
    asking_when = any(
        k in msg_lower
        for k in (
            "under what condition", "fold change", "log2", "when is", "when does",
            "time course", "kinetics", "何时", "什么条件", "倍数", "时间点",
        )
    )
    if asking_when:
        return False
    return any(re.search(p, msg_lower) for p in patterns)


def _is_broad_overview(message: str) -> bool:
    msg_lower = message.lower()
    keys = (
        "everything about", "tell me everything", "comprehensive",
        "who, when, where, why", "who when where why",
        "全面", "完整讲", "全部信息", "who，when，where，why",
    )
    return any(k in msg_lower for k in keys)


def _detect_capability_gaps(message: str) -> list[str]:
    """Known product gaps — planner annotates; synthesis must not invent answers."""
    gaps: list[str] = []
    if _mentions_structure_gap(message):
        gaps.append(
            "structural_context (AlphaFold global pLDDT only — no SASA / buried-exposed / PPI-interface tool)"
        )
    if _mentions_proteoform(message):
        gaps.append("proteoform (no combinatorial PTM / proteoform catalog tool)")
    if _mentions_crosstalk(message):
        # PTMcode2 exists but coverage is incomplete; still flag honesty requirement
        gaps.append(
            "crosstalk (PTMcode2 associations only — do not invent mechanisms beyond evidence)"
        )
    if _mentions_conservation(message):
        gaps.append(
            "cross_species_conservation (no dedicated conservation tool; UniProt homolog hints only)"
        )
    return gaps
# ── Query-mode gate (conversational vs research) ──────────────────

# Static / light replies (no tools)
QUERY_MODE_RESEARCH = "research"
QUERY_MODE_GREETING = "greeting"
QUERY_MODE_HELP = "help"
QUERY_MODE_CONCEPT = "concept"  # educational: what is PTM / why it matters
QUERY_MODE_CAPABILITY = "capability"  # can the agent do X? (SASA / proteoform / …)
QUERY_MODE_META_DB = "meta_db"  # product / database coverage facts
QUERY_MODE_CLARIFY = "clarify"
QUERY_MODE_OFF_TOPIC = "off_topic"

# Tool + LLM modes
QUERY_MODE_LITERATURE = "literature"  # field/method survey via PubTator + LLM
QUERY_MODE_PMID_LOOKUP = "pmid_lookup"  # summarize a specific PMID
QUERY_MODE_COLLECTION = "collection"  # literature-mining pipeline (PMID → qratio CSV)
QUERY_MODE_COMPARE = "compare"  # compare two sites on (usually) one protein
QUERY_MODE_FOLLOWUP = "followup"  # continue prior target with a focused ask

QUERY_MODES_WITH_TOOLS = frozenset({
    QUERY_MODE_RESEARCH,
    QUERY_MODE_LITERATURE,
    QUERY_MODE_PMID_LOOKUP,
    QUERY_MODE_COMPARE,
    QUERY_MODE_FOLLOWUP,
})

QUERY_MODES_SITE_RESOLVE = frozenset({
    QUERY_MODE_RESEARCH,
    QUERY_MODE_COMPARE,
    QUERY_MODE_FOLLOWUP,
})

_STAGE_ORDER = (
    WorkflowStage.kinase,
    WorkflowStage.conditions,
    WorkflowStage.where,
    WorkflowStage.function,
)

_GREETING_RE = re.compile(
    r"^[\s\W]*("
    r"hi|hello|hey|yo|howdy|hiya|good\s*(morning|afternoon|evening|night)|"
    r"how\s+are\s+you(?:\s+doing)?|how'?s\s+it\s+going|"
    r"thanks?(?:\s+you)?|thank\s*you|ty|thx|cheers|bye|goodbye|see\s*you|"
    r"你好|您好|嗨|哈喽|早上好|下午好|晚上好|你好吗|谢谢|多谢|再见|拜拜"
    r")[\s\W!?.！？。]*$",
    re.I,
)

_HELP_RE = re.compile(
    r"("
    r"what\s+can\s+you\s+do|who\s+are\s+you|how\s+(do|can)\s+(i|you)\s+use|"
    r"what\s+are\s+you|help\s*me|your\s+capabilities|how\s+to\s+use|"
    r"introduce\s+yourself|what\s+is\s+this(\s+agent)?|"
    r"你能(做|干什么|做什么)|你会什么|你是谁|怎么用|如何使用|介绍一下(你自己)?|"
    r"有什么功能|帮助"
    r")",
    re.I,
)

# Conceptual / textbook questions about PTM itself (no protein target)
_CONCEPT_RE = re.compile(
    r"("
    r"what\s+(is|are)\s+(a\s+|an\s+)?(ptm|ptms|post[-\s]?translational\s+modification)s?\b|"
    r"what\s+(is|are)\s+post[-\s]?translational\s+modification|"
    r"(define|definition\s+of|explain|introduce|overview\s+of)\s+"
    r"(a\s+|an\s+)?(ptm|ptms|post[-\s]?translational\s+modification)s?\b|"
    r"\bptms?\b.{0,40}(what\s+(is|are)|mean|meaning|purpose|role|function|used\s+for|why\s+(is|are|important|matter))|"
    r"(why\s+(are|is|do)\s+).{0,20}(ptm|post[-\s]?translational)|"
    r"importance\s+of\s+(ptm|post[-\s]?translational)|"
    r"(tell\s+me\s+about|overview\s+of|introduction\s+to)\s+(ptm|ptms|post[-\s]?translational)|"
    r"(什么是|何为|介绍一下?|解释一下?)(ptm|翻译后修饰)|"
    r"(ptm|翻译后修饰)\s*(是什么|是啥|指什么|有什么用|有什么作用|有何作用|的作用|的意义|的功能|为什么重要)|"
    r"(ptm|翻译后修饰).{0,12}(作用|意义|功能|用途)"
    r")",
    re.I,
)

_PTM_SIGNAL_RE = re.compile(
    r"("
    r"ptm|phospho|acetyl|ubiquit|methyl|glycosyl|sumoy|"
    r"kinase|enzyme|ligase|residue|site|s\d+|t\d+|y\d+|k\d+|"
    r"phosphorylation|acetylation|mutation|variant|localization|"
    r"nls|ppi|crosstalk|proteoform|stability|fold\s*change|log2|"
    r"phosphoproteom|proteomics|ptmomics|"
    r"磷酸化|乙酰化|泛素化|甲基化|糖基化|激酶|位点|突变|定位|稳定性|"
    r"翻译后修饰|修饰位点|修饰组学|磷酸化组学|蛋白组"
    r")",
    re.I,
)

_LITERATURE_FIELD_RE = re.compile(
    r"("
    r"single[-\s]?cell|sc[-\s]?(ptm|phospho|proteom)|spatial\s+proteom|"
    r"phosphoproteom|ptmomics|ptm\s+omics|proteomics\s+method|"
    r"mass\s+spectrometry\s+(ptm|phospho)|"
    r"(is\s+there|are\s+there|does\s+.+\s+exist|emerging|frontier|state\s+of\s+the\s+art|"
    r"recent\s+(progress|advances)|literature\s+(on|about)|review\s+of)\b.{0,40}"
    r"(ptm|phospho|proteom|post[-\s]?translational)|"
    r"(ptm|phospho|proteom|post[-\s]?translational).{0,40}"
    r"(single[-\s]?cell|omics|technology|method|workflow|pipeline|platform)|"
    r"单细胞.{0,12}(ptm|翻译后修饰|磷酸化|修饰|蛋白组|组学)|"
    r"(ptm|翻译后修饰|磷酸化|修饰).{0,12}(单细胞|组学|技术|方法|平台|流程)|"
    r"(有没有|是否有|存在|发展|前沿|进展|综述).{0,20}"
    r"(单细胞|翻译后修饰|ptm|磷酸化组|修饰组|蛋白组)|"
    r"(单细胞翻译后修饰|单细胞ptm|单细胞磷酸化|单细胞修饰组学)"
    r")",
    re.I,
)

_CAPABILITY_RE = re.compile(
    r"("
    r"\b(sasa|solvent\s+accessible|buried\s+vs\s+exposed|proteoform|combinatorial\s+ptm|"
    r"cross[-\s]?species\s+conservation|ppi\s+interface)\b|"
    r"(can\s+you|do\s+you\s+(support|have|cover)|is\s+it\s+possible\s+to|"
    r"able\s+to|support)\b.{0,40}"
    r"(sasa|proteoform|structure|conservation|crosstalk|compute|calculate|predict)|"
    r"(能不能|能否|可以|有没有|是否支持|会不会).{0,16}"
    r"(算|计算|查|分析|得到|提供).{0,20}"
    r"(sasa|可及性|埋藏|暴露|proteoform|蛋白变体|构象|结构|保守性|串扰)|"
    r"(有没有|是否有).{0,8}(proteoform|sasa|结构可及|组合修饰)|"
    r"(能力边界|做不到|无法(计算|查询)|不支持)"
    r")",
    re.I,
)

_META_DB_RE = re.compile(
    r"("
    r"(what|which)\s+(data|ptms?|modifications|databases?|resources?)\s+"
    r"(does|do|are\s+in|are\s+covered|does\s+qptm)|"
    r"qptm\s+(data|coverage|contents?|statistics|how\s+many|规模|数据|覆盖|包含)|"
    r"(how\s+many|number\s+of).{0,20}(events?|sites?|proteins?).{0,20}qptm|"
    r"(which|what)\s+(databases?|resources?).{0,30}(integrate|use|connect)|"
    r"(qptm|本系统|这个agent).{0,20}(有哪些|包含|覆盖|数据量|规模|对接)|"
    r"(有哪些|覆盖哪些|包含哪些).{0,12}(数据|数据库|ptm|修饰类型|资源)|"
    r"(数据范围|产品介绍|数据库介绍|资源列表)"
    r")",
    re.I,
)

_PMID_RE = re.compile(
    r"(?:pmid|pubmed(?:\s+id)?|文献)\s*[:#]?\s*(\d{7,8})\b",
    re.I,
)

_COLLECTION_RE = re.compile(
    r"("
    r"collect(?:ion)?|curat(?:e|ing)?|ingest|import|extract|mine|parse|scrap"
    r"|qratio|quantitative\s+table|supplementary\s+table|literature\s+metadata"
    r"|full\s*text|supplement(?:ary)?|data\s+collect"
    r"|数据收集|文献收集|抽取|入库|解析|定量表|补充表|全文|元数据|策展"
    r")",
    re.I,
)

_COMPARE_RE = re.compile(
    r"("
    r"\b(compare|comparison|versus|vs\.?)\b|"
    r"(比较|对比|相比|差异)"
    r")",
    re.I,
)

_FOLLOWUP_RE = re.compile(
    r"("
    r"^(那|那么|还有|另外|再|继续)|"
    r"(呢\s*[？?]?$)|"
    r"\b(what\s+about|how\s+about|and\s+also|also\s+tell|more\s+detail|"
    r"go\s+deeper|continue|next|tell\s+me\s+more)\b|"
    r"(再详细|详细一点|继续|接下来|还有呢|那.?呢)"
    r")",
    re.I,
)

_SITE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])([STYKR])(\d{1,4})(?![A-Za-z0-9])",
    re.I,
)


def _message_language(message: str) -> str:
    zh = sum(1 for ch in message if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in message if "a" <= ch.lower() <= "z")
    if zh >= 1 and zh >= max(1, latin) * 0.35:
        return "zh"
    return "en"


def _extract_site_positions(message: str) -> list[int]:
    """Unique residue positions in appearance order (S15, Ser15, …)."""
    found: list[int] = []
    for m in _SITE_TOKEN_RE.finditer(message or ""):
        pos = int(m.group(2))
        if pos not in found:
            found.append(pos)
    for m in re.finditer(
        r"(?<![A-Za-z0-9])(?:Ser|Thr|Tyr|Lys|Arg)(\d{1,4})(?![A-Za-z0-9])",
        message or "",
        re.I,
    ):
        pos = int(m.group(1))
        if pos not in found:
            found.append(pos)
    return found


def _extract_pmid(message: str) -> str | None:
    m = _PMID_RE.search(message or "")
    return m.group(1) if m else None


def _is_collection_request(
    message: str,
    entities: dict[str, Any],
    upload_filenames: list[str] | None = None,
) -> bool:
    """True when the user wants the PMID literature-mining / qratio pipeline."""
    text = (message or "").strip()
    if upload_filenames:
        from app.collection.uploads import classify_upload_filename

        for name in upload_filenames:
            kind = classify_upload_filename(name)
            if kind in ("fulltext", "supplementary"):
                return True
    # Standalone MS accession → download URLs (PXD / IPX / …)
    try:
        from app.collection.store import looks_like_resolve_urls_request

        if looks_like_resolve_urls_request(text):
            return True
    except Exception:
        pass
    if _COLLECTION_RE.search(text):
        return True
    pmid = entities.get("pmid") or _extract_pmid(text)
    if pmid and re.search(
        r"(collect|extract|curat|ingest|parse|qratio|收集|抽取|入库|解析)",
        text,
        re.I,
    ):
        entities["pmid"] = pmid
        return True
    return False


def _is_concept_question(message: str, entities: dict[str, Any]) -> bool:
    """True for educational PTM questions without a concrete protein/site target."""
    if entities.get("uniprot_ac") or entities.get("position") or entities.get("mutation_label"):
        return False
    gene = entities.get("gene")
    if gene and is_plausible_gene(gene):
        return False
    text = (message or "").strip()
    if _LITERATURE_FIELD_RE.search(text):
        return False
    if _CONCEPT_RE.search(text):
        return True
    if re.search(
        r"^(what\s+is|what\s+are|define|explain)\b.{0,60}\b(ptm|modification)",
        text,
        re.I,
    ):
        return True
    if re.search(r"^(ptm|翻译后修饰).{0,20}(是什么|有什么|作用|意义)", text, re.I):
        return True
    return False


def _is_literature_survey_question(message: str, entities: dict[str, Any]) -> bool:
    """PTM field/method/frontier questions best answered via literature search + LLM."""
    if entities.get("uniprot_ac") or entities.get("position") or entities.get("mutation_label"):
        return False
    text = (message or "").strip()
    if not text:
        return False
    if _LITERATURE_FIELD_RE.search(text):
        gene = entities.get("gene")
        if gene and is_plausible_gene(gene) and re.search(
            r"\b([STYKR]\d+|Ser\d+|Thr\d+|Tyr\d+|Lys\d+)\b|"
            r"(phosphorylates?|kinase|acetylat|ubiquit)",
            text,
            re.I,
        ):
            return False
        return True
    gene = entities.get("gene")
    if gene and is_plausible_gene(gene):
        return False
    if _PTM_SIGNAL_RE.search(text) and re.search(
        r"(有没有|是否有|exists?|emerging|frontier|omics|组学|技术|方法|single[-\s]?cell|单细胞)",
        text,
        re.I,
    ):
        return True
    return False


def _is_capability_question(message: str, entities: dict[str, Any]) -> bool:
    """Agent capability / limitation questions (static honesty, no DB hunt)."""
    text = (message or "").strip()
    if not text:
        return False
    # Site-level research still wins if a concrete gene+site is present
    if entities.get("position") and entities.get("gene") and is_plausible_gene(entities.get("gene")):
        # unless the ask is purely about whether a gap feature exists
        if not re.search(r"(能不能|能否|可以吗|can\s+you|do\s+you\s+support|有没有工具)", text, re.I):
            return False
    if _CAPABILITY_RE.search(text):
        return True
    # Gap detectors alone + interrogative about ability
    gaps = _detect_capability_gaps(text)
    if gaps and re.search(
        r"(能不能|能否|可以|有没有|吗|can\s+you|do\s+you|support|possible)",
        text,
        re.I,
    ):
        return True
    return False


def _is_meta_db_question(message: str, entities: dict[str, Any]) -> bool:
    """Product / database coverage questions."""
    if entities.get("position") or entities.get("mutation_label"):
        return False
    gene = entities.get("gene")
    if gene and is_plausible_gene(gene) and not re.search(
        r"qptm|数据库|database|coverage|数据", message or "", re.I
    ):
        return False
    return bool(_META_DB_RE.search(message or ""))


def _is_compare_question(message: str, entities: dict[str, Any]) -> bool:
    text = message or ""
    positions = _extract_site_positions(text)
    if len(positions) >= 2 and _COMPARE_RE.search(text):
        return True
    if len(positions) >= 2 and re.search(
        r"\b(both|difference|differ|which\s+is)\b|哪个|有何不同|有什么区别",
        text,
        re.I,
    ):
        return True
    return False


def _is_followup_question(
    message: str,
    entities: dict[str, Any],
    state: Any,
) -> bool:
    """Short continuation that should reuse the session target."""
    if not state or not state.has_target:
        return False
    text = (message or "").strip()
    if not text or len(text) > 160:
        return False
    # Brand-new gene that differs from session → fresh research, not follow-up
    gene = entities.get("gene")
    if gene and is_plausible_gene(gene) and state.target_gene:
        if gene.upper() != str(state.target_gene).upper() and entities.get("position"):
            return False
    if _FOLLOWUP_RE.search(text):
        return True
    # Bare stage ask: "WHEN?", "条件呢", "定位"
    scores = _score_stages(text)
    if any(v > 0 for v in scores.values()) and not (
        gene and is_plausible_gene(gene) and entities.get("position") and len(text) > 40
    ):
        # Short stage-focused continuation
        if len(text) <= 80:
            return True
    # Bare alternate site: "S46", "那S46"
    positions = _extract_site_positions(text)
    if positions and len(text) <= 40 and not (gene and gene.upper() != str(state.target_gene or "").upper()):
        return True
    return False


def _literature_pubtator_query(message: str) -> str:
    """Map field questions to English PubMed-friendly keywords."""
    text = (message or "").strip()
    parts: list[str] = []

    if re.search(r"单细胞|single[-\s]?cell|\bsc[- ]?(ptm|phospho)", text, re.I):
        parts.append("single-cell")
    if re.search(r"磷酸化组|phosphoproteom|phosphorylation", text, re.I):
        parts.append("phosphoproteomics")
    elif re.search(r"翻译后修饰|修饰组|\bptm\b|ptmomics|post[-\s]?translational", text, re.I):
        parts.append("post-translational modification")
        parts.append("PTM")
    if re.search(r"蛋白组|proteomics", text, re.I) and "phosphoproteomics" not in parts:
        parts.append("proteomics")
    if re.search(r"质谱|mass spectrometry|\bms\b", text, re.I):
        parts.append("mass spectrometry")
    if re.search(r"空间|spatial", text, re.I):
        parts.append("spatial")

    if not parts:
        cleaned = re.sub(
            r"(有没有|是否有|什么是|怎么|如何|吗|呢|？|\?)",
            " ",
            text,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:200] or "single-cell phosphoproteomics PTM"

    if "single-cell" in parts and (
        "phosphoproteomics" in parts or "PTM" in parts or "post-translational modification" in parts
    ):
        return "single-cell phosphoproteomics OR single-cell PTM proteomics"
    return " ".join(dict.fromkeys(parts))[:200]


def _score_stages(message: str) -> dict[WorkflowStage, int]:
    """Keyword scores per stage (shared with follow-up / research detection)."""
    msg_lower = message.lower()
    scores: dict[WorkflowStage, int] = {
        WorkflowStage.kinase: 0,
        WorkflowStage.conditions: 0,
        WorkflowStage.where: 0,
        WorkflowStage.function: 0,
    }
    for stage, keywords in _STAGE_KEYWORDS.items():
        for kw in keywords:
            if _keyword_hit(kw, msg_lower):
                scores[stage] += 1
    if _mentions_stability(message) or _mentions_disease(message) or _mentions_ppi(message):
        scores[WorkflowStage.function] += 2
    if _mentions_nls(message) or _mentions_domain(message):
        scores[WorkflowStage.where] += 2
    if _mentions_drug(message):
        scores[WorkflowStage.kinase] += 2
    if _mentions_crosstalk(message):
        scores[WorkflowStage.function] += 2
    return scores


def _has_research_signal(
    message: str,
    entities: dict[str, Any],
    state: Any = None,
) -> bool:
    """True when the message is a concrete PTM research ask."""
    if entities.get("uniprot_ac") or entities.get("position") or entities.get("mutation_label"):
        return True
    gene = entities.get("gene")
    if gene and is_plausible_gene(gene):
        return True
    scores = _score_stages(message)
    if gene and any(v > 0 for v in scores.values()):
        return True
    if state and state.has_target and len(message.strip()) >= 2:
        if _PTM_SIGNAL_RE.search(message) or any(v > 0 for v in scores.values()):
            return True
    return False


def classify_query_mode(
    message: str,
    entities: dict[str, Any] | None = None,
    state: Any = None,
    upload_filenames: list[str] | None = None,
) -> str:
    """Gate query intent across static / literature / research modes.

    Gate tree::

        greeting / help / concept / capability / meta_db  → static
        collection                                        → literature-mining job
        literature / pmid_lookup                          → PubTator + LLM
        clarify                                           → ask for gene/site
        followup / compare / research                     → tool chain
        off_topic                                         → refuse + redirect
    """
    text = (message or "").strip()
    if not text and not upload_filenames:
        return QUERY_MODE_CLARIFY

    entities = entities or parse_query_entities(text)

    if _is_collection_request(text, entities, upload_filenames):
        pmid = _extract_pmid(text)
        if pmid:
            entities["pmid"] = pmid
        return QUERY_MODE_COLLECTION

    if _GREETING_RE.match(text):
        return QUERY_MODE_GREETING

    # Capability before help so "能算 SASA 吗" is not swallowed by "你能…"
    if _is_capability_question(text, entities):
        return QUERY_MODE_CAPABILITY
    if _is_meta_db_question(text, entities):
        return QUERY_MODE_META_DB
    if _HELP_RE.search(text) and not entities.get("gene") and not entities.get("position"):
        return QUERY_MODE_HELP

    pmid = _extract_pmid(text)
    if pmid and (
        re.search(r"(讲了什么|讲什么|说了什么|摘要|summary|about|what\s+does)", text, re.I)
        or re.fullmatch(r"(?:pmid|pubmed(?:\s+id)?)\s*[:#]?\s*\d{7,8}\s*[?？]?", text, re.I)
        or (not entities.get("gene") and not entities.get("position"))
    ):
        entities["pmid"] = pmid
        return QUERY_MODE_PMID_LOOKUP

    if _is_literature_survey_question(text, entities):
        return QUERY_MODE_LITERATURE
    if _is_concept_question(text, entities):
        return QUERY_MODE_CONCEPT
    if _is_compare_question(text, entities):
        return QUERY_MODE_COMPARE
    if _is_followup_question(text, entities, state):
        return QUERY_MODE_FOLLOWUP
    if _has_research_signal(text, entities, state):
        return QUERY_MODE_RESEARCH

    if _PTM_SIGNAL_RE.search(text) or re.search(r"\bptm\b|翻译后修饰|修饰", text, re.I):
        return QUERY_MODE_CLARIFY

    return QUERY_MODE_OFF_TOPIC


def _guided_next_stage_prompt(
    stages: list[WorkflowStage],
    entities: dict[str, Any],
    *,
    lang: str | None = None,
) -> str:
    """Ask whether the user wants the next unplanned stage(s) — do not auto-dump."""
    lang = lang or "en"
    planned = set(stages)
    remaining = [s for s in _STAGE_ORDER if s not in planned]
    if not remaining:
        return ""

    gene = entities.get("gene") or "this protein"
    pos = entities.get("position")
    target = f"{gene} S{pos}" if pos else str(gene)

    labels = {
        WorkflowStage.kinase: ("上游激酶/酶/药物", "upstream kinases, enzymes, or drugs"),
        WorkflowStage.conditions: ("实验条件与时程/定量", "experimental conditions, kinetics, or quantification"),
        WorkflowStage.where: ("细胞背景与亚细胞定位", "cell context and subcellular localization"),
        WorkflowStage.function: ("功能机制与临床意义", "functional mechanism and clinical significance"),
    }
    offers = [labels[s][0 if lang == "zh" else 1] for s in remaining[:3]]
    if lang == "zh":
        offer_txt = "、".join(offers)
        return (
            f"FOCUS ONLY on the planned stage(s). After answering, ask in Chinese whether "
            f"the user also wants related evidence for **{target}**: {offer_txt}？"
            f"Do NOT auto-answer those unplanned stages."
        )
    offer_txt = "; ".join(offers)
    return (
        f"FOCUS ONLY on the planned stage(s). After answering, politely ask whether the user "
        f"also wants related evidence for **{target}**: {offer_txt}? "
        f"Do NOT auto-answer those unplanned stages."
    )


def build_gate_reply(mode: str, message: str) -> str:
    """Deterministic professional reply for non-tool modes."""
    lang = _message_language(message)

    if mode == QUERY_MODE_GREETING:
        if lang == "zh":
            return (
                "你好！我是 **qPTM Agent**，专注于蛋白质翻译后修饰（PTM）研究。\n\n"
                "你可以询问修饰位点的激酶/酶、实验条件、亚细胞定位或功能意义等。例如：\n"
                "- `TP53 S15 的磷酸化激酶是什么？`\n"
                "- `AKT1 S473 在什么条件下磷酸化？`\n\n"
                "请给我一个**蛋白/基因名**（最好带位点，如 S15）。"
            )
        return (
            "Hello! I'm **qPTM Agent**, a research assistant for "
            "protein post-translational modifications (PTMs).\n\n"
            "Ask about kinases, conditions, localization, or functional significance "
            "of a modification site. For example:\n"
            "- `Which kinase phosphorylates TP53 at S15?`\n"
            "- `Under what conditions is AKT1 S473 phosphorylated?`\n\n"
            "Please give a **gene/protein** (ideally with a site, e.g. S15)."
        )

    if mode == QUERY_MODE_HELP:
        if lang == "zh":
            return (
                "我是 **qPTM Agent**，对接 qPTM 与多个 PTM 知识库"
                "（iPTMnet、PhosphoSitePlus、UniProt、ActiveDriverDB 等）。\n\n"
                "**我能做的：**\n"
                "1. 查询催化/调控该修饰的激酶、酶或药物\n"
                "2. 分析修饰发生的实验条件、时间点与定量变化\n"
                "3. 解读亚细胞定位、结构域、NLS/NES 等序列语境\n"
                "4. 评估功能机制、稳定性、疾病关联与临床意义\n"
                "5. 文献调研、PMID 摘要、双位点比较、会话追问\n\n"
                "**请提供：** 基因/UniProt + 可选位点（如 `TP53 S15`）。\n"
                "我**不会**回答与 PTM 无关的闲聊或通用问题。"
            )
        return (
            "I'm **qPTM Agent**, connected to qPTM and external PTM knowledge bases "
            "(iPTMnet, PhosphoSitePlus, UniProt, ActiveDriverDB, and more).\n\n"
            "**What I can do:**\n"
            "1. Find kinases, enzymes, or drugs that write a PTM\n"
            "2. Report conditions, time points, and quantitative changes\n"
            "3. Interpret localization, domains, NLS/NES, and sequence context\n"
            "4. Assess mechanism, stability, disease links, and clinical relevance\n"
            "5. Literature surveys, PMID lookup, site comparison, follow-ups\n\n"
            "**Please provide:** a gene/UniProt ID and optionally a site "
            "(e.g. `TP53 S15`).\n"
            "I do **not** answer unrelated chit-chat or general non-PTM questions."
        )

    if mode == QUERY_MODE_CAPABILITY:
        gaps = _detect_capability_gaps(message) or [
            "structural_context (no SASA / buried-exposed / PPI-interface tool)",
            "proteoform (no combinatorial PTM / proteoform catalog tool)",
            "cross_species_conservation (no dedicated conservation map)",
            "crosstalk (only sparse PTMcode2 associations)",
        ]
        if lang == "zh":
            lines = "\n".join(f"- {g}" for g in gaps)
            return (
                "## 能力边界说明\n\n"
                "针对你问的能力，我需要先说明：**当前工具链无法可靠完成以下分析**，"
                "因此我不会编造结论：\n\n"
                f"{lines}\n\n"
                "**我可以可靠提供的：** 位点级证据（激酶、定量条件、定位、疾病/稳定性等，"
                "来自 qPTM 与整合库）。\n\n"
                "若你有具体蛋白位点，可以直接问，例如：`TP53 S15 的磷酸化激酶是什么？`"
            )
        lines = "\n".join(f"- {g}" for g in gaps)
        return (
            "## Capability limits\n\n"
            "For the capability you asked about: **current tools cannot reliably answer "
            "the following**, so I will not invent results:\n\n"
            f"{lines}\n\n"
            "**What I can provide:** site-level evidence from qPTM "
            "and integrated databases (kinases, kinetics, localization, disease/stability).\n\n"
            "If you have a concrete site, ask e.g. `Which kinase phosphorylates TP53 at S15?`"
        )

    if mode == QUERY_MODE_META_DB:
        if lang == "zh":
            return (
                "## qPTM / 本 Agent 数据范围\n\n"
                "**核心库 qPTM**（https://qptm3.omicsbio.info）：\n"
                "- 千万级定量 PTM 事件（条件、时间点、log2 等）\n"
                "- 整合的位点–激酶等注释\n\n"
                "**对接的外部资源（节选）：**\n"
                "| 资源 | 用途 |\n"
                "|------|------|\n"
                "| iPTMnet / PhosphoSitePlus | 酶–底物、调控/疾病位点 |\n"
                "| UniProt / InterPro / Pfam | 功能、结构域 |\n"
                "| GPS 6.0 / UbiBrowser 等 | 预测或专项酶关系 |\n"
                "| ActiveDriverDB / PTMD / CancerProteome | 突变、疾病、肿瘤定量 |\n"
                "| PubTator3 | 补充文献 |\n\n"
                "**常见修饰类型：** 磷酸化、乙酰化、泛素化、甲基化、糖基化、SUMO 化等"
                "（覆盖度因库而异）。\n\n"
                "若要查具体位点证据，请给出基因+位点，例如 `TP53 S15`。"
            )
        return (
            "## qPTM / agent data coverage\n\n"
            "**Core database qPTM** (https://qptm3.omicsbio.info):\n"
            "- Millions of quantitative PTM events (conditions, time points, log2, …)\n"
            "- Integrated site–kinase annotations\n\n"
            "**External resources (selected):**\n"
            "| Resource | Role |\n"
            "|----------|------|\n"
            "| iPTMnet / PhosphoSitePlus | enzyme–substrate, regulatory/disease sites |\n"
            "| UniProt / InterPro / Pfam | function, domains |\n"
            "| GPS 6.0 / UbiBrowser, … | experimental or specialized enzyme links |\n"
            "| ActiveDriverDB / PTMD / CancerProteome | mutation, disease, tumor quant |\n"
            "| PubTator3 | literature supplement |\n\n"
            "**Common PTM types:** phosphorylation, acetylation, ubiquitination, "
            "methylation, glycosylation, SUMOylation (coverage varies by resource).\n\n"
            "For site evidence, ask with a gene + site, e.g. `TP53 S15`."
        )

    if mode == QUERY_MODE_CONCEPT:
        if lang == "zh":
            return (
                "## 什么是 PTM？\n\n"
                "**翻译后修饰（Post-Translational Modification, PTM）** 是指蛋白质在核糖体合成之后，"
                "氨基酸残基上再发生的化学修饰。它不改变基因序列，却能快速、可逆地改变蛋白的活性、定位、稳定性和相互作用。\n\n"
                "## 常见类型\n\n"
                "| 类型 | 典型残基 | 常见“写入酶” |\n"
                "|------|----------|----------------|\n"
                "| 磷酸化 | S / T / Y | 激酶（kinase） |\n"
                "| 乙酰化 | K | 乙酰转移酶（如 EP300） |\n"
                "| 泛素化 | K | E3 连接酶（如 MDM2） |\n"
                "| 甲基化 | K / R | 甲基转移酶 |\n"
                "| 糖基化、SUMO 化等 | 多种 | 相应酶系统 |\n\n"
                "## 有什么作用？\n\n"
                "1. **开关信号通路** — 如磷酸化激活/抑制激酶级联\n"
                "2. **调控蛋白稳定性** — 如磷酸化降低 MDM2 亲和力，稳定 p53\n"
                "3. **决定亚细胞定位** — 影响入核、出核、膜定位\n"
                "4. **改变蛋白互作与复合物组装**\n"
                "5. **疾病与药物相关** — 位点突变可破坏修饰；药物可改变 PTM 水平\n\n"
                "可以把它理解为蛋白质的“状态编码”：同一蛋白在不同修饰组合下，功能可以完全不同。\n\n"
                "---\n"
                "若要查**具体蛋白/位点**的证据（激酶、条件、定位、功能），请直接给出，例如：\n"
                "`TP53 S15 的磷酸化激酶是什么？`"
            )
        return (
            "## What is a PTM?\n\n"
            "A **post-translational modification (PTM)** is a chemical change added to a protein "
            "**after** it is synthesized. PTMs do not rewrite the gene sequence; instead they "
            "rapidly and often reversibly tune protein activity, localization, stability, and interactions.\n\n"
            "## Common types\n\n"
            "| Type | Typical residues | Typical writers |\n"
            "|------|------------------|-----------------|\n"
            "| Phosphorylation | S / T / Y | Kinases |\n"
            "| Acetylation | K | Acetyltransferases (e.g. EP300) |\n"
            "| Ubiquitination | K | E3 ligases (e.g. MDM2) |\n"
            "| Methylation | K / R | Methyltransferases |\n"
            "| Glycosylation, SUMOylation, … | Various | Dedicated enzyme systems |\n\n"
            "## Why do PTMs matter?\n\n"
            "1. **Signal switching** — e.g. phosphorylation turns pathways on/off\n"
            "2. **Stability control** — e.g. phospho-S15 can reduce MDM2 binding and stabilize p53\n"
            "3. **Localization** — nuclear import/export, membrane targeting\n"
            "4. **Interaction rewiring** — PTMs create or break protein interfaces\n"
            "5. **Disease & drugs** — mutations can abolish a site; compounds can shift PTM levels\n\n"
            "Think of PTMs as a **state code** on proteins: the same polypeptide can do different jobs "
            "depending on its modification pattern.\n\n"
            "---\n"
            "To look up **database evidence for a specific protein/site**, ask something like:\n"
            "`Which kinase phosphorylates TP53 at S15?`"
        )

    if mode == QUERY_MODE_CLARIFY:
        if lang == "zh":
            return (
                "这个问题还不够具体，我还无法开始数据库检索。\n\n"
                "请补充：\n"
                "1. **蛋白/基因**（如 TP53、AKT1）\n"
                "2. **位点**（如 S15、K382，可选）\n"
                "3. **关注点**（激酶？条件？定位？功能？疾病？）\n\n"
                "示例：`TP53 S15 磷酸化的上游激酶是什么？`\n"
                "如果只是想了解 PTM 概念，可以直接问：`PTM是什么？`"
            )
        return (
            "That question is too broad for a database search yet.\n\n"
            "Please specify:\n"
            "1. A **gene/protein** (e.g. TP53, AKT1)\n"
            "2. A **site** if you have one (e.g. S15, K382)\n"
            "3. What you care about (kinase, conditions, localization, function, disease)\n\n"
            "Example: `Which kinase phosphorylates TP53 at S15?`\n"
            "For a general definition, ask: `What is PTM?`"
        )

    # off_topic
    if lang == "zh":
        return (
            "我是面向 **PTM（翻译后修饰）** 的研究助手，无法回答与 PTM 无关的问题。\n\n"
            "如果你想查某个蛋白的修饰，请直接给出基因名和位点，例如：\n"
            "`TP53 S15` 或 `AKT1 S473 phosphorylation who/when/where/why`。\n"
            "若想了解概念，可以问：`PTM是什么？有什么作用？`"
        )
    return (
        "I'm a research assistant focused on **PTMs (post-translational modifications)** "
        "and can't help with unrelated topics.\n\n"
        "If you want to investigate a protein modification, send a gene and site, e.g.\n"
        "`TP53 S15` or `AKT1 S473 phosphorylation — who, when, where, why?`\n"
        "For a conceptual overview, ask: `What is PTM and why does it matter?`"
    )
