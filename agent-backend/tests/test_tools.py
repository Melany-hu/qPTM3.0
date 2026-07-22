#!/usr/bin/env python3
"""End-to-end test suite for the qPTM Agent.

Tests all tools, workflow state machine, and API endpoints.
Run: python tests/test_tools.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools.registry import registry
from app.tools.qptm_tools import register_qptm_tools
from app.tools.iptmnet_tools import register_iptmnet_tools
from app.tools.uniprot_tools import register_uniprot_tools
from app.tools.psp_tools import register_psp_tools
from app.tools.dbptm_tools import register_dbptm_tools
from app.tools.stability_tools import register_stability_tools
from app.workflow.state import ConversationState, SessionManager
from app.workflow.stages import (
    detect_stage_from_message,
    advance_stage,
    get_stage_suggestion,
    get_stage_label,
    get_stage_order,
)
from app.models.schemas import WorkflowStage


def test_tool_registration():
    """Test that all tools register correctly."""
    print("=== Test: Tool Registration ===")
    register_qptm_tools()
    register_iptmnet_tools()
    register_uniprot_tools()
    register_psp_tools()
    register_dbptm_tools()
    register_stability_tools()

    expected = 9
    actual = len(registry.tool_names)
    assert actual == expected, f"Expected {expected} tools, got {actual}"
    assert "ptm_stability" in registry.tool_names, "ptm_stability should be registered"
    print(f"  PASS: {actual} tools registered: {registry.tool_names}")
    print()


def test_uniprot_annotation():
    """Test UniProt annotation tool with TP53."""
    print("=== Test: UniProt Annotation (P04637 / TP53) ===")
    result = registry.execute("uniprot_annotation", {"uniprot_ac": "P04637"})

    assert result["gene"] == "TP53", f"Expected gene TP53, got {result.get('gene')}"
    assert result["protein_name"], "Protein name should not be empty"
    assert result["function"], "Function should not be empty"
    assert result["ptm_description"], "PTM description should not be empty"
    assert len(result["disease_associations"]) > 0, "Should have disease associations"
    assert result["subcellular_location"], "Subcellular location should not be empty"

    print(f"  PASS: Gene={result['gene']}, Protein={result['protein_name'][:40]}")
    print(f"  Function: {result['function'][:80]}...")
    print(f"  PTM: {result['ptm_description'][:80]}...")
    print(f"  Disease associations: {len(result['disease_associations'])}")
    print(f"  Domains: {len(result['domains'])}")
    print()


def test_iptmnet_enzymes():
    """Test iPTMnet enzymes tool with TP53."""
    print("=== Test: iPTMnet Enzymes (P04637 / TP53) ===")
    result = registry.execute("iptmnet_enzymes", {"uniprot_ac": "P04637"})

    assert result["total"] > 0, "Should find enzymes for TP53"
    enzymes = result["enzymes"]
    assert any(e["enzyme_gene"] == "ATM" for e in enzymes), "Should find ATM as a kinase"

    print(f"  PASS: Found {result['total']} enzymes")
    for e in enzymes[:5]:
        print(f"    {e['enzyme_gene']} ({e['enzyme_type']}) -> pos {e['substrate_position']}, {e['ptm_type']}")
    print()


def test_iptmnet_enzymes_filtered():
    """Test iPTMnet enzymes with position filter."""
    print("=== Test: iPTMnet Enzymes (P04637, position=55) ===")
    result = registry.execute("iptmnet_enzymes", {"uniprot_ac": "P04637", "position": 55})

    assert result["total"] > 0, "Should find enzyme for TP53 T55"
    assert any(e["enzyme_gene"] == "TAF1" for e in result["enzymes"]), "Should find TAF1"

    print(f"  PASS: Found {result['total']} enzyme(s) for position 55")
    for e in result["enzymes"]:
        print(f"    {e['enzyme_gene']} ({e['enzyme_type']})")
    print()


def test_iptmnet_ptm_ppi():
    """Test iPTMnet PTM-dependent PPI tool."""
    print("=== Test: iPTMnet PTM-dependent PPI (P04637) ===")
    result = registry.execute("iptmnet_ptm_ppi", {"uniprot_ac": "P04637"})

    assert result["total"] > 0, "Should find PTM-dependent interactions"

    print(f"  PASS: Found {result['total']} interactions")
    for i in result["interactions"][:3]:
        print(f"    {i['interactor_a']} <-> {i['interactor_b']} ({i['interaction_type']})")
    print()


def test_psp_regulatory_no_data():
    """Test PSP regulatory tool gracefully handles missing data file."""
    print("=== Test: PSP Regulatory (no data file) ===")
    result = registry.execute("psp_regulatory", {"uniprot_ac": "P04637", "position": 15})

    assert result["available"] == False, "Should report data not available"
    assert "download" in result["summary"].lower(), "Should mention downloading"

    print(f"  PASS: Gracefully handles missing data: {result['summary'][:80]}...")
    print()


def test_dbptm_no_data():
    """Test dbPTM tool gracefully handles missing data."""
    print("=== Test: dbPTM Functional (no data file) ===")
    result = registry.execute("dbptm_functional", {"uniprot_ac": "P04637"})

    # Should either return web fallback or "not available" message
    assert "summary" in result, "Should always return a summary"

    print(f"  PASS: Gracefully handles missing data: {result['summary'][:80]}...")
    print()


def test_ptm_stability():
    """Test PTM stability tool with TP53."""
    print("=== Test: PTM Stability (P04637 / TP53) ===")
    result = registry.execute("ptm_stability", {"uniprot_ac": "P04637"})

    assert result["found"] == True, "Should find stability data for TP53"
    assert result["total"] > 0, "Should have entries"
    assert result["gene"] == "TP53", f"Expected gene TP53, got {result.get('gene')}"
    assert result["stabilize_count"] > 0, "Should have stabilizing PTMs"
    assert result["destabilize_count"] > 0, "Should have destabilizing PTMs"

    # Verify entry structure
    entry = result["entries"][0]
    assert "effect_direction" in entry, "Entry should have effect_direction"
    assert "mechanism" in entry, "Entry should have mechanism"
    assert "ptm_type" in entry, "Entry should have ptm_type"

    print(f"  PASS: Found {result['total']} entries (stab={result['stabilize_count']}, destab={result['destabilize_count']})")
    print()


def test_ptm_stability_filtered():
    """Test PTM stability tool with position and PTM type filters."""
    print("=== Test: PTM Stability (P04637, position=15) ===")
    result = registry.execute("ptm_stability", {"uniprot_ac": "P04637", "position": 15})

    assert result["found"] == True, "Should find data for TP53 position 15"
    assert result["total"] >= 1, "Should have at least 1 entry"
    # All entries should be for position 15 or general (None)
    for e in result["entries"]:
        assert e["position"] == 15 or e["position"] is None, \
            f"Entry position should be 15 or None, got {e['position']}"

    print(f"  PASS: Found {result['total']} entries for position 15")

    # Test PTM type filter
    print("=== Test: PTM Stability (P04637, ptm_type=methylation) ===")
    result = registry.execute("ptm_stability", {"uniprot_ac": "P04637", "ptm_type": "methylation"})

    assert result["found"] == True, "Should find methylation data for TP53"
    for e in result["entries"]:
        assert e["ptm_type"] == "methylation", f"Should be methylation, got {e['ptm_type']}"

    print(f"  PASS: Found {result['total']} methylation entries")
    print()


def test_ptm_stability_not_found():
    """Test PTM stability tool with protein not in dataset."""
    print("=== Test: PTM Stability (P31749 / AKT1 - not in dataset) ===")
    result = registry.execute("ptm_stability", {"uniprot_ac": "P31749"})

    assert result["found"] == False, "Should not find data for AKT1"
    assert result["available"] == True, "Dataset should be available"
    assert "34 proteins" in result["summary"], "Should mention dataset coverage"

    print(f"  PASS: Correctly reports no data: {result['summary'][:80]}...")
    print()


def test_ptm_stability_htt():
    """Test PTM stability tool with HTT (corrected accession P42858)."""
    print("=== Test: PTM Stability (P42858 / HTT) ===")
    result = registry.execute("ptm_stability", {"uniprot_ac": "P42858"})

    assert result["found"] == True, "Should find data for HTT"
    assert result["gene"] == "HTT", f"Expected gene HTT, got {result.get('gene')}"
    assert result["total"] > 0, "Should have entries"

    print(f"  PASS: Found {result['total']} entries for HTT")
    print()


def test_qptm_tools_error_handling():
    """Test qPTM tools handle connection errors gracefully."""
    print("=== Test: qPTM Tools Error Handling (no backend) ===")
    # qPTM API is not running, so these should return errors, not crash
    result = registry.execute("qptm_search", {"query": "TP53"})
    assert "error" in result or "summary" in result, "Should return error or summary"

    result = registry.execute("qptm_site_conditions", {"uniprot_ac": "P04637", "position": 15})
    assert "error" in result or "summary" in result, "Should return error or summary"

    result = registry.execute("qptm_kinases", {"uniprot_ac": "P04637", "position": 15})
    assert "error" in result or "summary" in result, "Should return error or summary"

    print("  PASS: All qPTM tools handle connection errors gracefully")
    print()


def test_workflow_state_machine():
    """Test workflow state machine transitions."""
    print("=== Test: Workflow State Machine ===")

    # Test stage detection
    test_cases = [
        ("Under what conditions is TP53 S15 phosphorylated?", WorkflowStage.conditions),
        ("Which kinase phosphorylates TP53 S15?", WorkflowStage.kinase),
        ("What is the functional effect of phosphorylating TP53 S15?", WorkflowStage.function),
        ("TP53 S15的条件是什么？", WorkflowStage.conditions),  # Chinese
        ("哪个激酶磷酸化TP53 S15？", WorkflowStage.kinase),  # Chinese
    ]
    for msg, expected in test_cases:
        detected = detect_stage_from_message(msg)
        assert detected == expected, f"Expected {expected}, got {detected} for '{msg}'"
    print(f"  PASS: Stage detection ({len(test_cases)} cases, including Chinese)")

    # Test stage advancement
    sm = SessionManager()
    state = sm.get_or_create("test-wf")
    state.set_target(gene="TP53", uniprot_ac="P04637", position=15, ptm_type="phosphorylation")
    state.advance_to(WorkflowStage.conditions)
    state.add_conditions([{"condition_name": "etoposide"}], total=3)

    next_stage = advance_stage(state)
    assert next_stage == WorkflowStage.kinase, f"Should advance to kinase, got {next_stage}"

    state.add_kinases([{"kinase_gene": "ATM", "evidence_type": "experimental"}])
    next_stage = advance_stage(state)
    assert next_stage == WorkflowStage.function, f"Should advance to function, got {next_stage}"

    state.add_functions([{"source": "UniProt", "function": "transcription factor"}])
    next_stage = advance_stage(state)
    assert next_stage == WorkflowStage.synthesis, f"Should advance to synthesis, got {next_stage}"

    print(f"  PASS: Stage advancement (idle → conditions → kinase → function → synthesis)")

    # Test stage suggestions
    state2 = sm.get_or_create("test-sugg")
    sugg = get_stage_suggestion(state2)
    assert "three-stage" in sugg["suggestion"], "Idle suggestion should mention three stages"
    print(f"  PASS: Stage suggestions generated correctly")

    # Test state serialization
    state_dict = state.to_dict()
    assert state_dict["current_stage"] == "synthesis"
    assert state_dict["target_gene"] == "TP53"
    assert state_dict["total_conditions"] == 3
    print(f"  PASS: State serialization works")

    # Test reset
    state.reset()
    assert state.current_stage == WorkflowStage.idle
    assert state.target_gene is None
    print(f"  PASS: State reset works")
    print()


def test_unknown_tool():
    """Test that unknown tools return an error."""
    print("=== Test: Unknown Tool Error ===")
    result = registry.execute("nonexistent_tool", {})
    assert "error" in result, "Should return error for unknown tool"
    print(f"  PASS: {result['error']}")
    print()


def test_invalid_uniprot():
    """Test UniProt tool with invalid accession."""
    print("=== Test: Invalid UniProt Accession ===")
    result = registry.execute("uniprot_annotation", {"uniprot_ac": "INVALID123"})
    assert result.get("function") is None or result.get("gene") is None, \
        "Should not find data for invalid accession"
    print(f"  PASS: Handles invalid accession gracefully")
    print()


def main():
    print("qPTM Agent — End-to-End Test Suite")
    print("=" * 50)
    print()

    tests = [
        test_tool_registration,
        test_uniprot_annotation,
        test_iptmnet_enzymes,
        test_iptmnet_enzymes_filtered,
        test_iptmnet_ptm_ppi,
        test_psp_regulatory_no_data,
        test_dbptm_no_data,
        test_ptm_stability,
        test_ptm_stability_filtered,
        test_ptm_stability_not_found,
        test_ptm_stability_htt,
        test_qptm_tools_error_handling,
        test_workflow_state_machine,
        test_unknown_tool,
        test_invalid_uniprot,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            failed += 1
            print()

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed == 0:
        print("All tests passed!")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
