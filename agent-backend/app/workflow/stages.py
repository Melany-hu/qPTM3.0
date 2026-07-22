"""Stage transition logic and proactive next-step suggestions.

Determines when to advance the workflow stage and generates contextual
suggestions for the user to proceed to the next stage.
"""

import logging
from typing import Any

from app.models.schemas import WorkflowStage
from app.workflow.state import ConversationState

logger = logging.getLogger(__name__)


# ── Stage detection from user messages ────────────────────────────

# Keywords that signal which stage the user is asking about
_STAGE_KEYWORDS: dict[WorkflowStage, list[str]] = {
    WorkflowStage.conditions: [
        "condition", "conditions", "when", "where", "cell type", "treatment",
        "stimulus", "stimuli", "time point", "time-course", "time course",
        "sample", "experiment", "tissue", "expressed", "quantified",
        "log2", "fold change", "ratio", "up-regulated", "down-regulated",
        "upregulated", "downregulated", "differential",
        "条件", "何时", "何地", "细胞", "处理", "刺激", "时间点", "样本",
        "实验", "组织", "表达", "定量", "变化", "差异",
    ],
    WorkflowStage.kinase: [
        "kinase", "enzyme", "catalyze", "catalyzes", "responsible",
        "phosphorylate", "phosphorylates", "acetylate", "acetyltransferase",
        "ubiquitinate", "e3 ligase", "ligase", "demethylase", "methyltransferase",
        "glycosyltransferase", "sumo ligase", "who", "writer", "eraser",
        "激酶", "酶", "催化", "负责", "磷酸化", "乙酰化", "泛素化",
        "甲基化", "糖基化", "sumo化", "谁",
    ],
    WorkflowStage.function: [
        "function", "functional", "effect", "consequence", "happen",
        "activity", "stability", "localization", "localisation",
        "pathway", "process", "disease", "drug", "target", "therapeutic",
        "interaction", "binding", "regulate", "regulation",
        "cancer", "tumor", "tumour", "clinical",
        "功能", "作用", "后果", "影响", "活性", "稳定性", "定位",
        "通路", "途径", "疾病", "药物", "靶点", "治疗", "相互作用",
    ],
}


def detect_stage_from_message(message: str) -> WorkflowStage | None:
    """Detect which workflow stage the user's message is about.

    Returns the most likely stage, or None if no stage-specific keywords found.
    """
    msg_lower = message.lower()
    scores: dict[WorkflowStage, int] = {
        WorkflowStage.conditions: 0,
        WorkflowStage.kinase: 0,
        WorkflowStage.function: 0,
    }

    for stage, keywords in _STAGE_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                scores[stage] += 1

    best_stage = max(scores, key=lambda s: scores[s])
    if scores[best_stage] > 0:
        return best_stage
    return None


# ── Stage advancement ─────────────────────────────────────────────

def should_advance_stage(state: ConversationState) -> WorkflowStage | None:
    """Determine if the workflow should advance to the next stage.

    Returns the next stage to advance to, or None if no advancement needed.
    """
    # Only advance if we have findings for the current stage
    if state.current_stage == WorkflowStage.conditions:
        if state.conditions_found and state.has_target:
            return WorkflowStage.kinase

    elif state.current_stage == WorkflowStage.kinase:
        if (state.kinases_found or state.enzymes_found) and state.has_target:
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
        # User hasn't started investigating yet
        return {
            "stage": WorkflowStage.conditions,
            "suggestion": (
                "I can help you investigate PTM sites through a three-stage workflow:\n"
                "1. **Where & When** — experimental conditions\n"
                "2. **Who** — kinase/enzyme identification\n"
                "3. **Why it matters** — functional consequences\n\n"
                "Tell me a protein or gene name to start (e.g., \"TP53\", \"AKT1\", \"S15 phosphorylation of TP53\")."
            ),
            "tools": ["qptm_search"],
        }

    if state.current_stage == WorkflowStage.conditions:
        if state.conditions_found:
            gene = state.target_gene or state.target_uniprot_ac or "this protein"
            pos = state.target_position or ""
            n = state.total_conditions or len(state.conditions_found)
            top_conds = [
                c.get("condition_name", c.get("condition", ""))
                for c in state.conditions_found[:3]
                if c.get("condition_name") or c.get("condition")
            ]
            cond_str = f" ({', '.join(top_conds)})" if top_conds else ""
            return {
                "stage": WorkflowStage.kinase,
                "suggestion": (
                    f"I found that **{gene}{' ' + str(pos) if pos else ''}** is modified "
                    f"under {n} condition(s){cond_str}. "
                    f"Would you like to identify **which kinase or enzyme** is responsible "
                    f"for this modification? (Stage 2)"
                ),
                "tools": ["qptm_kinases", "iptmnet_enzymes"],
            }
        else:
            return {
                "stage": WorkflowStage.conditions,
                "suggestion": (
                    "Let me search for PTM events for this protein first. "
                    "Could you provide a gene name or UniProt accession?"
                ),
                "tools": ["qptm_search"],
            }

    if state.current_stage == WorkflowStage.kinase:
        if state.kinases_found or state.enzymes_found:
            gene = state.target_gene or state.target_uniprot_ac or "this protein"
            all_enzymes = state.kinases_found + state.enzymes_found
            names = [
                e.get("kinase_gene", e.get("enzyme_gene", ""))
                for e in all_enzymes
                if e.get("kinase_gene") or e.get("enzyme_gene")
            ]
            enzyme_str = f" ({', '.join(names[:3])})" if names else ""
            return {
                "stage": WorkflowStage.function,
                "suggestion": (
                    f"I identified {len(all_enzymes)} enzyme(s) for **{gene}**{enzyme_str}. "
                    f"Would you like to explore **what happens to {gene}'s function** "
                    f"when this site is modified? (Stage 3 — functional consequences, "
                    f"disease associations, and drug target potential)"
                ),
                "tools": ["psp_regulatory", "uniprot_annotation", "dbptm_functional", "iptmnet_ptm_ppi"],
            }
        else:
            return {
                "stage": WorkflowStage.kinase,
                "suggestion": (
                    "I haven't found kinase data yet. Let me search qPTM and iPTMnet "
                    "for enzymes associated with this site."
                ),
                "tools": ["qptm_kinases", "iptmnet_enzymes"],
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
                    f"I've gathered functional data for **{gene}**: "
                    f"{', '.join(findings)}. Would you like me to provide a "
                    f"**comprehensive synthesis** summarizing all three stages "
                    f"(conditions → kinase → function)? I can also suggest "
                    f"follow-up experiments."
                ),
                "tools": [],
            }
        else:
            return {
                "stage": WorkflowStage.function,
                "suggestion": (
                    "Let me query PhosphoSitePlus, UniProt, and dbPTM for "
                    "functional consequences of this modification."
                ),
                "tools": ["psp_regulatory", "uniprot_annotation", "dbptm_functional"],
            }

    if state.current_stage == WorkflowStage.synthesis:
        gene = state.target_gene or state.target_uniprot_ac or "this protein"
        return {
            "stage": WorkflowStage.idle,
            "suggestion": (
                f"We've completed the full investigation of **{gene}** "
                f"across all three stages. Would you like to:\n"
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
        WorkflowStage.conditions: "Stage 1: Where & When",
        WorkflowStage.kinase: "Stage 2: Who",
        WorkflowStage.function: "Stage 3: Why It Matters",
        WorkflowStage.synthesis: "Synthesis",
    }
    return labels.get(stage, str(stage))


def get_stage_order() -> list[WorkflowStage]:
    """Return the canonical stage progression order."""
    return [
        WorkflowStage.idle,
        WorkflowStage.conditions,
        WorkflowStage.kinase,
        WorkflowStage.function,
        WorkflowStage.synthesis,
    ]
