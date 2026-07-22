"""Pydantic models for API request/response schemas."""

from pydantic import BaseModel, Field
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────

class PTMType(str, Enum):
    phosphorylation = "phosphorylation"
    acetylation = "acetylation"
    ubiquitylation = "ubiquitylation"
    methylation = "methylation"
    glycosylation = "glycosylation"
    sumoylation = "sumoylation"


class Organism(str, Enum):
    human = "human"
    mouse = "mouse"
    rat = "rat"
    yeast = "yeast"
    all = "all"


class SearchField(str, Enum):
    any = "any"
    gene = "gene"
    uniprot = "uniprot"
    protein = "protein"
    function = "function"
    sample = "sample"
    condition = "condition"


class WorkflowStage(str, Enum):
    idle = "idle"
    conditions = "conditions"       # Stage 1: where/when
    kinase = "kinase"               # Stage 2: who
    function = "function"           # Stage 3: why it matters
    synthesis = "synthesis"         # Final summary


# ── qPTM API response models ───────────────────────────────────────

class PTMEvent(BaseModel):
    pmid: str | None = None
    uniprot_ac: str
    gene: str
    position: int
    ptm_type: str
    sequence_window: str | None = None
    sample: str | None = None
    condition: str | None = None
    log2_ratio: float | None = None
    p_value: float | None = None
    stars: int | None = None
    fdr_flag: bool | None = None


class SearchResult(BaseModel):
    total: int
    page: int
    per_page: int
    events: list[PTMEvent]


class SiteSummary(BaseModel):
    uniprot_ac: str
    position: int
    ptm_type: str
    stars: int | None = None
    total_events: int
    total_conditions: int
    total_samples: int
    sequence_window: str | None = None


class SiteDetail(BaseModel):
    summary: SiteSummary
    events: list[PTMEvent]


class ProteinInfo(BaseModel):
    uniprot_ac: str
    gene: str
    protein_name: str
    organism: str
    function_desc: str | None = None
    ptm_sites: list[dict] = Field(default_factory=list)


class ConditionInfo(BaseModel):
    condition_name: str
    condition_abbr: str | None = None
    description: str | None = None
    event_count: int
    samples: list[str] = Field(default_factory=list)


class KinaseInfo(BaseModel):
    kinase_gene: str
    kinase_uniprot: str | None = None
    evidence_type: str  # "experimental" or "predicted"
    source_db: str
    inhibitor: str | None = None


class DatabaseStats(BaseModel):
    total_events: int
    total_sites: int
    total_proteins: int
    total_conditions: int
    total_samples: int
    by_organism: dict[str, dict[str, int]] = Field(default_factory=dict)
    by_ptm_type: dict[str, dict[str, int]] = Field(default_factory=dict)


# ── External DB response models ────────────────────────────────────

class PSPRegulatoryAnnotation(BaseModel):
    uniprot_ac: str
    position: int
    ptm_type: str
    on_function: list[str] = Field(default_factory=list)
    on_process: list[str] = Field(default_factory=list)
    on_prot_interact: list[str] = Field(default_factory=list)
    on_other_interact: list[str] = Field(default_factory=list)
    notes: str | None = None
    pmids: list[str] = Field(default_factory=list)


class UniProtAnnotation(BaseModel):
    uniprot_ac: str
    gene: str | None = None
    protein_name: str | None = None
    function: str | None = None
    ptm_description: str | None = None
    domains: list[str] = Field(default_factory=list)
    disease_associations: list[str] = Field(default_factory=list)
    subcellular_location: str | None = None


class IPTMnetEnzyme(BaseModel):
    enzyme_gene: str
    enzyme_uniprot: str | None = None
    enzyme_type: str  # kinase, acetyltransferase, E3 ligase, etc.
    substrate_uniprot: str
    substrate_position: int
    ptm_type: str
    evidence: str  # experimental, predicted, text-mined


class IPTMnetPPI(BaseModel):
    interactor_a: str
    interactor_b: str
    ptm_site_description: str
    interaction_type: str  # induces, disrupts
    evidence: str


# ── Chat API models ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class ToolCallEvent(BaseModel):
    """SSE event: agent is calling a tool."""
    tool_name: str
    arguments: dict


class ToolResultEvent(BaseModel):
    """SSE event: tool returned results."""
    tool_name: str
    success: bool
    summary: str
    data_count: int


class StageUpdateEvent(BaseModel):
    """SSE event: workflow stage changed."""
    stage: WorkflowStage
    description: str
