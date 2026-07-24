"""Workflow state machine — tracks conversation state across the PTM logic line.

The state tracks:
  - Current stage (idle → WHO → WHEN → WHERE → WHY → synthesis)
  - Target protein/site being investigated
  - Findings accumulated at each stage

This state is per-session and kept in memory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.models.schemas import WorkflowStage

logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    """Per-session workflow state for the qPTM agent."""

    session_id: str = ""

    # Current workflow stage
    current_stage: WorkflowStage = WorkflowStage.idle

    # Target protein/site being investigated
    target_gene: str | None = None
    target_uniprot_ac: str | None = None
    target_position: int | None = None
    target_ptm_type: str | None = None

    # Stage 1 WHO: kinases / enzymes / drugs that regulate the site
    kinases_found: list[dict[str, Any]] = field(default_factory=list)
    enzymes_found: list[dict[str, Any]] = field(default_factory=list)
    drugs_found: list[dict[str, Any]] = field(default_factory=list)

    # Stage 2 WHEN: quantitative kinetics / conditions
    conditions_found: list[dict[str, Any]] = field(default_factory=list)
    total_conditions: int = 0

    # Stage 3 WHERE: cellular context / subcellular localization
    localization_found: list[dict[str, Any]] = field(default_factory=list)

    # Stage 4 WHY: functional consequences / disease / interactions
    functions_found: list[dict[str, Any]] = field(default_factory=list)
    disease_associations: list[dict[str, Any]] = field(default_factory=list)
    interactions_found: list[dict[str, Any]] = field(default_factory=list)

    # Conversation metadata
    turn_count: int = 0
    stages_completed: list[WorkflowStage] = field(default_factory=list)

    # Research plan (planning-first agent)
    current_plan: Any | None = None  # ResearchPlan, stored as dict for serialization
    current_step_index: int = 0
    plan_entities: dict[str, Any] = field(default_factory=dict)

    # ── Stage transitions ──

    def advance_to(self, stage: WorkflowStage) -> None:
        """Move to a new stage, marking the previous one as completed."""
        if self.current_stage != WorkflowStage.idle and self.current_stage not in self.stages_completed:
            self.stages_completed.append(self.current_stage)
        self.current_stage = stage
        logger.info(
            f"Session {self.session_id}: stage transition → {stage.value} "
            f"(completed: {[s.value for s in self.stages_completed]})"
        )

    def reset(self) -> None:
        """Reset state for a new investigation (new protein/site)."""
        self.current_stage = WorkflowStage.idle
        self.target_gene = None
        self.target_uniprot_ac = None
        self.target_position = None
        self.target_ptm_type = None
        self.kinases_found.clear()
        self.enzymes_found.clear()
        self.drugs_found.clear()
        self.conditions_found.clear()
        self.total_conditions = 0
        self.localization_found.clear()
        self.functions_found.clear()
        self.disease_associations.clear()
        self.interactions_found.clear()
        self.stages_completed.clear()
        self.current_plan = None
        self.current_step_index = 0
        self.plan_entities.clear()

    # ── Target management ──

    def set_target(
        self,
        gene: str | None = None,
        uniprot_ac: str | None = None,
        position: int | None = None,
        ptm_type: str | None = None,
    ) -> None:
        """Set or update the investigation target."""
        if gene:
            self.target_gene = gene
        if uniprot_ac:
            self.target_uniprot_ac = uniprot_ac
        if position:
            self.target_position = position
        if ptm_type:
            self.target_ptm_type = ptm_type

    @property
    def has_target(self) -> bool:
        """Whether a protein target has been identified."""
        return self.target_uniprot_ac is not None or self.target_gene is not None

    @property
    def target_description(self) -> str:
        """Human-readable description of the current target."""
        parts = []
        if self.target_gene:
            parts.append(self.target_gene)
        if self.target_uniprot_ac:
            parts.append(f"({self.target_uniprot_ac})")
        if self.target_position:
            residue = ""
            if self.target_ptm_type:
                residue = self.target_ptm_type[:3] + " "
            parts.append(f"{residue}at position {self.target_position}")
        return " ".join(parts) if parts else "No target set"

    # ── Findings accumulation ──

    def add_kinases(self, kinases: list[dict[str, Any]]) -> None:
        """Record Stage 1 WHO kinase findings."""
        self.kinases_found = kinases

    def add_enzymes(self, enzymes: list[dict[str, Any]]) -> None:
        """Record Stage 1 WHO enzyme findings from iPTMnet."""
        self.enzymes_found = enzymes

    def add_drugs(self, drugs: list[dict[str, Any]]) -> None:
        """Record Stage 1 WHO drug / upstream regulator findings."""
        self.drugs_found = drugs

    def add_conditions(self, conditions: list[dict[str, Any]], total: int = 0) -> None:
        """Record Stage 2 WHEN kinetics / condition findings."""
        self.conditions_found = conditions
        self.total_conditions = total or len(conditions)

    def add_localization(self, localization: list[dict[str, Any]]) -> None:
        """Record Stage 3 WHERE localization / context findings."""
        self.localization_found = localization

    def add_functions(self, functions: list[dict[str, Any]]) -> None:
        """Record Stage 4 WHY functional consequence findings."""
        self.functions_found = functions

    def add_disease(self, disease: list[dict[str, Any]]) -> None:
        """Record Stage 4 WHY disease association findings."""
        self.disease_associations = disease

    def add_interactions(self, interactions: list[dict[str, Any]]) -> None:
        """Record Stage 4 WHY PTM-dependent interaction findings."""
        self.interactions_found = interactions

    # ── Serialization ──

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to a dict (for debugging or API response)."""
        return {
            "session_id": self.session_id,
            "current_stage": self.current_stage.value,
            "target_gene": self.target_gene,
            "target_uniprot_ac": self.target_uniprot_ac,
            "target_position": self.target_position,
            "target_ptm_type": self.target_ptm_type,
            "kinases_count": len(self.kinases_found),
            "enzymes_count": len(self.enzymes_found),
            "drugs_count": len(self.drugs_found),
            "total_conditions": self.total_conditions,
            "localization_count": len(self.localization_found),
            "functions_count": len(self.functions_found),
            "disease_count": len(self.disease_associations),
            "interactions_count": len(self.interactions_found),
            "turn_count": self.turn_count,
            "stages_completed": [s.value for s in self.stages_completed],
        }


# ── Session manager ───────────────────────────────────────────────

class SessionManager:
    """Manages conversation states per session ID (in-memory)."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationState] = {}

    def get_or_create(self, session_id: str) -> ConversationState:
        """Get existing session state or create a new one."""
        if session_id not in self._sessions:
            state = ConversationState(session_id=session_id)
            self._sessions[session_id] = state
            logger.info(f"Created new session: {session_id}")
        return self._sessions[session_id]

    def get(self, session_id: str) -> ConversationState | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def reset_session(self, session_id: str) -> ConversationState:
        """Reset a session's state (start a new investigation)."""
        state = self.get_or_create(session_id)
        state.reset()
        return state


# Global session manager
session_manager = SessionManager()
