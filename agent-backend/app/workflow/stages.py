"""Stage transition logic and proactive next-step suggestions.

Determines when to advance the workflow stage and generates contextual
suggestions for the user to proceed to the next stage.

Canonical logic line: WHO → WHEN → WHERE → WHY
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.models.schemas import WorkflowStage
from app.workflow.state import ConversationState

logger = logging.getLogger(__name__)


# ── Stage detection from user messages ────────────────────────────

# Keywords that signal which stage the user is asking about
_STAGE_KEYWORDS: dict[WorkflowStage, list[str]] = {
    WorkflowStage.kinase: [
        "kinase", "kinases", "enzyme", "catalyze", "catalyzes", "responsible",
        "which kinase", "who phosphorylates", "acetyltransferase",
        "correlation", "spearman", "ekpi", "quantitative correlation",
        "e3 ligase", "ligase", "demethylase", "methyltransferase",
        "glycosyltransferase", "sumo ligase", "writer", "eraser",
        "upstream", "drug", "drugs", "inhibitor", "antibody", "ligand",
        "who regulates", "regulates this", "who does it",
        "激酶", "酶", "催化", "负责", "谁磷酸化", "哪个激酶",
        "乙酰化酶", "泛素化", "甲基化酶", "糖基化", "sumo化", "谁调控",
        "调控了", "上游", "药物",
    ],
    WorkflowStage.conditions: [
        "condition", "conditions", "when", "time point", "time-course",
        "time course", "kinetics", "minutes", "hours", "transient", "sustained",
        "fold change", "log2", "ratio", "up-regulated", "down-regulated",
        "upregulated", "downregulated", "differential", "stimulus", "stimuli",
        "treatment", "under what",
        "条件", "何时", "时间点", "时程", "动力学", "倍数", "定量",
        "变化", "差异", "瞬时", "持续",
    ],
    WorkflowStage.where: [
        "where", "location", "localization", "localisation", "localized",
        "localised", "compartment", "subcellular", "cell type", "cell line",
        "tissue", "sample", "lipid raft", "organelle", "nucleus", "cytoplasm",
        "membrane", "nls", "nes", "nuclear localization signal",
        "nuclear export signal", "domain", "domains",
        "何地", "定位", "细胞器", "组织", "样本", "背景", "位置",
        "脂筏", "核定位", "膜定位", "胞质", "结构域", "功能域", "核定位信号",
    ],
    WorkflowStage.function: [
        "function", "functional", "effect", "consequence", "happen",
        "activity", "stability", "stabilize", "destabilize", "stabilizes",
        "destabilizes", "pathway", "process", "disease",
        "target", "therapeutic", "interaction", "binding",
        "cancer", "tumor", "tumour", "clinical", "mutation", "mutations",
        "clinvar", "somatic", "germline", "variant", "variants",
        "resistance", "sensitivity", "pharmacology", "biomarker",
        "mechanism", "outcome", "why", "so what", "crosstalk",
        "rewiring", "ptmvar", "missense", "disrupt",
        "phase separation", "llps", "condensate", "droplet", "phasllps", "phosllps",
        "dscope", "stress granule", "p-body", "membraneless",
        "功能", "作用", "后果", "影响", "活性", "稳定性", "稳定", "去稳定",
        "通路", "途径", "疾病", "靶点", "治疗", "相互作用",
        "突变", "变异", "体细胞", "胚系", "耐药", "敏感性",
        "相分离", "液液相分离", "凝聚体", "机制", "结局", "价值", "标志物",
        "为什么", "为何", "破坏", "重布线", "串扰",
    ],
}


def _keyword_hit(keyword: str, text: str) -> bool:
    """Match keywords; use token boundaries for Latin, substring for CJK."""
    if any("\u4e00" <= ch <= "\u9fff" for ch in keyword):
        return keyword in text
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def detect_stage_from_message(message: str) -> WorkflowStage | None:
    """Detect which workflow stage the user's message is about.

    Returns the most likely stage, or None if no stage-specific keywords found.
    """
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

    best_stage = max(scores, key=lambda s: scores[s])
    if scores[best_stage] > 0:
        return best_stage
    return None


# ── Stage advancement ─────────────────────────────────────────────

def should_advance_stage(state: ConversationState) -> WorkflowStage | None:
    """Determine if the workflow should advance to the next stage.

    Returns the next stage to advance to, or None if no advancement needed.
    Order: WHO (kinase) → WHEN (conditions) → WHERE → WHY (function) → synthesis
    """
    if state.current_stage == WorkflowStage.kinase:
        if (state.kinases_found or state.enzymes_found or state.drugs_found) and state.has_target:
            return WorkflowStage.conditions

    elif state.current_stage == WorkflowStage.conditions:
        if state.conditions_found and state.has_target:
            return WorkflowStage.where

    elif state.current_stage == WorkflowStage.where:
        if (state.localization_found or state.functions_found) and state.has_target:
            return WorkflowStage.function

    elif state.current_stage == WorkflowStage.function:
        if (state.functions_found or state.disease_associations or
                state.interactions_found) and state.has_target:
            return WorkflowStage.synthesis

    return None


def advance_stage(state: ConversationState) -> WorkflowStage | None:
    """Advance the workflow to the next stage if appropriate.

    Returns the new stage if advanced, None otherwise.
    """
    next_stage = should_advance_stage(state)
    if next_stage and next_stage != state.current_stage:
        state.advance_to(next_stage)
        return next_stage
    return None


# ── Proactive next-step suggestions ───────────────────────────────

def get_stage_suggestion(state: ConversationState) -> dict[str, Any]:
    """Generate a proactive next-step suggestion based on current state.

    Returns a dict with:
      - "stage": the suggested next stage
      - "suggestion": a contextual prompt for the user
      - "tools": which tools would be called
    """
    if state.current_stage == WorkflowStage.idle:
        return {
            "stage": WorkflowStage.kinase,
            "suggestion": (
                "I can help you investigate PTM sites through a four-stage logic line:\n"
                "1. **WHO** — who regulates it (drugs / enzymes)\n"
                "2. **WHEN** — when it happens (kinetics)\n"
                "3. **WHERE** — cell context & localization\n"
                "4. **WHY** — mechanism, outcome, and clinical value\n\n"
                "Tell me a protein or gene name to start (e.g., \"TP53\", \"AKT1\", \"RFTN1 S467\")."
            ),
            "tools": ["qptm_search", "qptm_kinases"],
        }

    if state.current_stage == WorkflowStage.kinase:
        if state.kinases_found or state.enzymes_found or state.drugs_found:
            gene = state.target_gene or state.target_uniprot_ac or "this protein"
            all_enzymes = state.kinases_found + state.enzymes_found
            names = [
                e.get("kinase_gene", e.get("enzyme_gene", ""))
                for e in all_enzymes
                if e.get("kinase_gene") or e.get("enzyme_gene")
            ]
            enzyme_str = f" ({', '.join(names[:3])})" if names else ""
            return {
                "stage": WorkflowStage.conditions,
                "suggestion": (
                    f"I identified regulators for **{gene}**{enzyme_str}. "
                    f"Would you like to see **WHEN** this site changes "
                    f"(time course / fold change / cancer vs normal)? (Stage 2)"
                ),
                "tools": ["qptm_site_conditions", "cancerproteome_disease"],
            }
        return {
            "stage": WorkflowStage.kinase,
            "suggestion": (
                "I haven't found regulator data yet. Let me search qPTM, iPTMnet, "
                "and drug–PTM resources for enzymes and upstream drugs."
            ),
            "tools": ["qptm_kinases", "iptmnet_enzymes", "pmads_drug_ptm", "drugbank_targets"],
        }

    if state.current_stage == WorkflowStage.conditions:
        if state.conditions_found:
            gene = state.target_gene or state.target_uniprot_ac or "this protein"
            pos = state.target_position or ""
            n = state.total_conditions or len(state.conditions_found)
            return {
                "stage": WorkflowStage.where,
                "suggestion": (
                    f"I found quantitative kinetics for **{gene}"
                    f"{' ' + str(pos) if pos else ''}** under {n} condition(s). "
                    f"Would you like to explore **WHERE** this happens "
                    f"(cell/tissue background and subcellular location)? (Stage 3)"
                ),
                "tools": ["compartments_localization", "uniprot_annotation", "interpro_domains", "pfam_domains"],
            }
        return {
            "stage": WorkflowStage.conditions,
            "suggestion": (
                "Let me search for quantitative PTM events (qPTM) and "
                "cancer tumor-vs-control quantification (CancerProteome)."
            ),
            "tools": ["qptm_search", "qptm_site_conditions", "cancerproteome_disease"],
        }

    if state.current_stage == WorkflowStage.where:
        gene = state.target_gene or state.target_uniprot_ac or "this protein"
        if state.localization_found or state.functions_found:
            return {
                "stage": WorkflowStage.function,
                "suggestion": (
                    f"I have localization / context for **{gene}**. "
                    f"Would you like to explore **WHY it matters** "
                    f"(mechanism, outcome, biomarker value)? (Stage 4)"
                ),
                "tools": ["psp_regulatory", "cancerproteome_disease", "ptmd_disease"],
            }
        return {
            "stage": WorkflowStage.where,
            "suggestion": (
                "Let me query COMPARTMENTS / UniProt for cellular context "
                "and subcellular localization."
            ),
            "tools": ["compartments_localization", "uniprot_annotation"],
        }

    if state.current_stage == WorkflowStage.function:
        if state.functions_found or state.disease_associations or state.interactions_found:
            gene = state.target_gene or state.target_uniprot_ac or "this protein"
            findings = []
            if state.functions_found:
                findings.append(f"{len(state.functions_found)} functional effect(s)")
            if state.disease_associations:
                findings.append(f"{len(state.disease_associations)} disease association(s)")
            if state.interactions_found:
                findings.append(f"{len(state.interactions_found)} interaction change(s)")
            return {
                "stage": WorkflowStage.synthesis,
                "suggestion": (
                    f"I've gathered WHY-it-matters data for **{gene}**: "
                    f"{', '.join(findings)}. Would you like a "
                    f"**comprehensive synthesis** along WHO → WHEN → WHERE → WHY?"
                ),
                "tools": [],
            }
        return {
            "stage": WorkflowStage.function,
            "suggestion": (
                "Let me query PhosphoSitePlus, CancerProteome, and PTMD for "
                "mechanism, outcome, and clinical value."
            ),
            "tools": ["psp_regulatory", "cancerproteome_disease", "ptmd_disease", "dbptm_functional"],
        }

    if state.current_stage == WorkflowStage.synthesis:
        gene = state.target_gene or state.target_uniprot_ac or "this protein"
        return {
            "stage": WorkflowStage.idle,
            "suggestion": (
                f"We've completed the full investigation of **{gene}** "
                f"across WHO → WHEN → WHERE → WHY. Would you like to:\n"
                f"- Investigate another PTM site on the same protein\n"
                f"- Explore a different protein\n"
                f"- Dive deeper into any specific finding?"
            ),
            "tools": [],
        }

    return {
        "stage": WorkflowStage.idle,
        "suggestion": "How can I help you investigate PTMs?",
        "tools": [],
    }


def get_stage_label(stage: WorkflowStage) -> str:
    """Human-readable label for a workflow stage."""
    labels = {
        WorkflowStage.idle: "Getting Started",
        WorkflowStage.kinase: "Stage 1: WHO",
        WorkflowStage.conditions: "Stage 2: WHEN",
        WorkflowStage.where: "Stage 3: WHERE",
        WorkflowStage.function: "Stage 4: WHY",
        WorkflowStage.synthesis: "Synthesis",
    }
    return labels.get(stage, str(stage))


def get_stage_order() -> list[WorkflowStage]:
    """Return the canonical stage progression order."""
    return [
        WorkflowStage.idle,
        WorkflowStage.kinase,
        WorkflowStage.conditions,
        WorkflowStage.where,
        WorkflowStage.function,
        WorkflowStage.synthesis,
    ]
