#!/usr/bin/env python3
"""qPTM Agent layered evaluation harness (Q1–Q30)."""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("AGENT_URL", "http://127.0.0.1:8100")
OUT_DIR = Path(__file__).resolve().parent
TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "240"))

QUESTIONS = [
    # Layer 1
    {"id": "Q1", "layer": 1, "stage": "WHO",
     "q": "Which kinase phosphorylates TP53 at S15?",
     "expect_tools": ["qptm_kinases", "iptmnet_enzymes"],
     "expect_keywords": ["CK1", "CSNK1", "ATM", "ATR", "DNA-PK", "PRKDC", "CHEK"],
     "notes": "基本激酶查询；基因名→UniProt"},
    {"id": "Q2", "layer": 1, "stage": "WHO",
     "q": "What enzyme acetylates TP53 at K382?",
     "expect_tools": ["iptmnet_enzymes"],
     "expect_keywords": ["EP300", "CREBBP", "p300", "CBP"],
     "notes": "非磷酸化酶查询"},
    {"id": "Q3", "layer": 1, "stage": "WHO",
     "q": "Which E3 ligase ubiquitinates TP53?",
     "expect_tools": ["iptmnet_enzymes", "ubibrowser_interactions"],
     "expect_keywords": ["MDM2"],
     "notes": "不指定位点的泛素化"},
    {"id": "Q4", "layer": 1, "stage": "WHO",
     "q": "What drugs are known to affect TP53 phosphorylation?",
     "expect_tools": ["pmads_drug_ptm", "decryptm_drug_ptm"],
     "expect_keywords": ["drug", "etoposide", "doxorubicin", "nutlin"],
     "notes": "药物-PTM"},
    {"id": "Q5", "layer": 1, "stage": "WHEN",
     "q": "Under what conditions is TP53 S15 phosphorylated?",
     "expect_tools": ["qptm_site_conditions"],
     "expect_keywords": ["etoposide", "doxorubicin", "DNA damage", "UV", "IR", "radiation"],
     "notes": "实验条件"},
    {"id": "Q6", "layer": 1, "stage": "WHEN",
     "q": "What is the fold change of TP53 S15 phosphorylation after etoposide treatment?",
     "expect_tools": ["qptm_site_conditions", "qptm_search"],
     "expect_keywords": ["log2", "fold", "ratio", "etoposide"],
     "notes": "定量数值"},
    {"id": "Q7", "layer": 1, "stage": "WHERE",
     "q": "Where is TP53 localized in the cell?",
     "expect_tools": ["uniprot_annotation", "compartments_localization"],
     "expect_keywords": ["nucleus", "nuclear", "cytoplasm"],
     "notes": "亚细胞定位"},
    {"id": "Q8", "layer": 1, "stage": "WHERE",
     "q": "Is TP53 S15 in a nuclear localization signal region?",
     "expect_tools": ["inuloc_nls_nes"],
     "expect_keywords": ["NLS", "nuclear localization", "not", "outside", "within"],
     "notes": "位点 vs NLS 坐标推理"},
    {"id": "Q9", "layer": 1, "stage": "WHY",
     "q": "Does phosphorylation of TP53 S15 stabilize or destabilize the protein?",
     "expect_tools": ["ptm_stability"],
     "expect_keywords": ["stabiliz", "MDM2", "destabiliz"],
     "notes": "稳定性 + effect_direction"},
    {"id": "Q10", "layer": 1, "stage": "WHY",
     "q": "What diseases are associated with TP53 PTM sites?",
     "expect_tools": ["uniprot_annotation", "ptmd_disease", "dbptm_functional", "psp_disease_sites"],
     "expect_keywords": ["cancer", "Li-Fraumeni", "tumor", "disease"],
     "notes": "多疾病源整合"},
    # Layer 2
    {"id": "Q11", "layer": 2, "stage": "ALL",
     "q": "Tell me everything about TP53 S15 phosphorylation",
     "expect_tools": ["qptm_kinases", "iptmnet_enzymes", "qptm_site_conditions", "uniprot_annotation", "ptm_stability"],
     "expect_stages": ["kinase", "conditions", "where", "function"],
     "expect_keywords": ["kinase", "condition", "localiz", "stabil"],
     "notes": "完整四阶段"},
    {"id": "Q12", "layer": 2, "stage": "WHY-skip",
     "q": "TP53 S15 is phosphorylated by CK1 — so what?",
     "expect_tools": ["ptm_stability", "psp_regulatory", "dbptm_functional"],
     "expect_keywords": ["function", "stabil", "MDM2", "apoptosis", "transcription"],
     "notes": "跳过 WHO，进 WHY"},
    {"id": "Q13", "layer": 2, "stage": "COMPARE",
     "q": "Compare TP53 S15 and S46 phosphorylation",
     "expect_tools": ["qptm_kinases", "iptmnet_enzymes", "psp_regulatory", "ptm_stability"],
     "expect_keywords": ["S15", "S46", "HIPK", "apoptosis"],
     "notes": "双位点比较 / 工具轮次"},
    {"id": "Q14", "layer": 2, "stage": "WHO+WHY",
     "q": "I know TP53 S15 is phosphorylated after DNA damage. Who does it and why does it matter?",
     "expect_tools": ["qptm_kinases", "iptmnet_enzymes", "ptm_stability", "psp_regulatory"],
     "expect_keywords": ["kinase", "ATM", "ATR", "stabil", "MDM2"],
     "notes": "跳过 WHEN"},
    # Layer 3
    {"id": "Q15", "layer": 3, "stage": "MUTATION",
     "q": "Which somatic mutations disrupt TP53 S15 phosphorylation?",
     "expect_tools": ["activedriver_mutations", "psp_ptmvar"],
     "expect_keywords": ["mutation", "S15", "variant"],
     "notes": "突变-PTM", "gap_ok": True},
    {"id": "Q16", "layer": 3, "stage": "MUTATION",
     "q": "What happens if TP53 S46 is mutated to phenylalanine?",
     "expect_tools": ["activedriver_mutations", "psp_ptmvar", "psp_regulatory"],
     "expect_keywords": ["S46F", "HIPK", "apoptosis", "phosphorylat"],
     "notes": "S46F 推理", "gap_ok": True},
    {"id": "Q17", "layer": 3, "stage": "MUTATION",
     "q": "Which cancer mutations in KRAS affect its post-translational modifications?",
     "expect_tools": ["activedriver_mutations", "psp_ptmvar"],
     "expect_keywords": ["G12", "G13", "farnesyl", "ubiquit", "mutation"],
     "notes": "KRAS 覆盖度", "gap_ok": True},
    {"id": "Q18", "layer": 3, "stage": "PPI",
     "q": "Does TP53 S15 phosphorylation affect its interaction with MDM2?",
     "expect_tools": ["iptmnet_ptm_ppi", "ptmint_ppi"],
     "expect_keywords": ["MDM2", "interaction", "disrupts", "induces", "affinity"],
     "notes": "PTM-PPI", "gap_ok": True},
    {"id": "Q19", "layer": 3, "stage": "STRUCTURE",
     "q": "Which PTM sites on TP53 are at protein-protein interaction interfaces?",
     "expect_tools": [],
     "expect_keywords": ["interface", "cannot", "not available", "do not have", "no tool", "unable", "limitation"],
     "notes": "结构缺口——应诚实", "expect_honest_gap": True},
    {"id": "Q20", "layer": 3, "stage": "CROSSTALK",
     "q": "Is there crosstalk between TP53 S15 phosphorylation and K382 acetylation?",
     "expect_tools": ["ptmcode_associations"],
     "expect_keywords": ["crosstalk", "cannot", "not available", "do not have", "unknown", "unable", "limitation", "no direct"],
     "notes": "crosstalk 缺口", "expect_honest_gap": True},
    {"id": "Q21", "layer": 3, "stage": "CROSSTALK",
     "q": "Which PTM sites on histone H3 are known to have crosstalk?",
     "expect_tools": ["ptmcode_associations"],
     "expect_keywords": ["H3", "K4", "K9", "K27", "crosstalk", "cannot", "not available"],
     "notes": "组蛋白 crosstalk", "expect_honest_gap": True},
    {"id": "Q22", "layer": 3, "stage": "PROTEOFORM",
     "q": "What proteoforms of TP53 have been experimentally observed?",
     "expect_tools": [],
     "expect_keywords": ["proteoform", "cannot", "not available", "do not have", "unable", "limitation", "no"],
     "notes": "proteoform 缺失", "expect_honest_gap": True},
    {"id": "Q23", "layer": 3, "stage": "PROTEOFORM",
     "q": "Can TP53 be simultaneously phosphorylated at S15 and acetylated at K382?",
     "expect_tools": [],
     "expect_keywords": ["uncertain", "cannot", "unknown", "not determined", "no direct", "do not have", "unable"],
     "notes": "组合 PTM 不确定", "expect_honest_gap": True},
    {"id": "Q24", "layer": 3, "stage": "STRUCTURE",
     "q": "Is TP53 S15 buried or exposed on the protein surface?",
     "expect_tools": [],
     "expect_keywords": ["cannot", "not available", "do not have", "SASA", "unable", "limitation", "no structural"],
     "notes": "SASA 缺口", "expect_honest_gap": True},
    {"id": "Q25", "layer": 3, "stage": "DOMAIN",
     "q": "Is TP53 S15 located in a functional domain?",
     "expect_tools": ["interpro_domains", "pfam_domains"],
     "expect_keywords": ["domain", "outside", "TAD", "transactivation", "not within"],
     "notes": "位点-域坐标"},
    {"id": "Q26", "layer": 3, "stage": "CONSERVATION",
     "q": "Is TP53 S15 phosphorylation conserved in mouse?",
     "expect_tools": ["uniprot_annotation"],
     "expect_keywords": ["mouse", "conserv", "Trp53", "P02340", "cannot", "homolog"],
     "notes": "跨物种保守性缺口", "expect_honest_gap": True},
    # Layer 4
    {"id": "Q27", "layer": 4, "stage": "ERROR",
     "q": "Which kinase phosphorylates XYZ123 at S999?",
     "expect_tools": [],
     "expect_keywords": ["not found", "no ", "unknown", "could not", "unable", "no evidence", "no kinase"],
     "notes": "不存在蛋白——优雅失败"},
    {"id": "Q28", "layer": 4, "stage": "CLARIFY",
     "q": "Tell me about PTM",
     "expect_tools": [],
     "expect_keywords": ["protein", "site", "which", "specify", "example", "gene", "more specific"],
     "notes": "宽泛问题——引导"},
    {"id": "Q29", "layer": 4, "stage": "ZH",
     "q": "TP53 S15的磷酸化激酶是什么？它有什么功能影响？",
     "expect_tools": ["qptm_kinases", "iptmnet_enzymes", "ptm_stability", "psp_regulatory"],
     "expect_keywords": ["激酶", "功能", "稳定", "MDM2", "磷酸化"],
     "notes": "中文 + WHO+WHY"},
    {"id": "Q30", "layer": 4, "stage": "AKT1",
     "q": "AKT1 S473 phosphorylation — who, when, where, why?",
     "expect_tools": ["qptm_kinases", "iptmnet_enzymes", "qptm_site_conditions", "ptm_stability", "psp_regulatory"],
     "expect_keywords": ["mTOR", "MTOR", "PDK", "kinase", "activ"],
     "notes": "非TP53四阶段"},
]


def parse_sse(raw: str) -> dict:
    events = []
    tools = []
    tool_results = []
    stages = []
    plan = None
    texts = []
    errors = []
    sources = []
    steps = []

    blocks = re.split(r"\n\n+", raw)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        etype = None
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                etype = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not etype:
            continue
        data_str = "\n".join(data_lines)
        try:
            data = json.loads(data_str) if data_str else {}
        except json.JSONDecodeError:
            data = {"_raw": data_str}
        events.append({"type": etype, "data": data})
        if etype == "plan_created":
            plan = data
        elif etype == "tool_call":
            tools.append({"name": data.get("tool_name"), "args": data.get("arguments")})
        elif etype == "tool_result":
            tool_results.append({
                "name": data.get("tool_name"),
                "success": data.get("success"),
                "summary": (data.get("summary") or "")[:300],
                "data_count": data.get("data_count"),
            })
        elif etype == "stage_update":
            stages.append(data.get("stage") or data.get("label"))
        elif etype == "step_started":
            steps.append({"step": data.get("step"), "stage": data.get("stage"),
                          "tool": data.get("tool"), "title": data.get("title")})
        elif etype == "text":
            texts.append(data.get("content") or "")
        elif etype == "error":
            errors.append(data.get("message") or str(data))
        elif etype == "sources":
            sources = data.get("citations") or []

    answer = "".join(texts)
    return {
        "tools_called": [t["name"] for t in tools if t.get("name")],
        "tool_calls": tools,
        "tool_results": tool_results,
        "stages": [s for s in stages if s],
        "plan_steps": steps,
        "plan": plan,
        "answer": answer,
        "answer_len": len(answer),
        "errors": errors,
        "n_sources": len(sources),
        "n_events": len(events),
    }


def ask(message: str, session_id: str) -> dict:
    body = json.dumps({
        "message": message,
        "session_id": session_id,
        "history": [],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/chat",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            cid = resp.headers.get("X-Conversation-Id")
            raw = resp.read().decode("utf-8", "replace")
        parsed = parse_sse(raw)
        parsed["conversation_id"] = cid
        parsed["elapsed_s"] = round(time.time() - t0, 1)
        parsed["ok"] = True
        return parsed
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "elapsed_s": round(time.time() - t0, 1),
            "tools_called": [],
            "tool_results": [],
            "stages": [],
            "plan_steps": [],
            "answer": "",
            "answer_len": 0,
            "errors": [str(e)],
            "n_sources": 0,
        }


def score(item: dict, result: dict) -> dict:
    answer = result.get("answer") or ""
    tools = result.get("tools_called") or []
    expect_tools = item.get("expect_tools") or []
    expect_kw = item.get("expect_keywords") or []
    expect_stages = item.get("expect_stages") or []

    tool_hit = [t for t in expect_tools if t in tools] if expect_tools else []
    tool_miss = [t for t in expect_tools if t not in tools] if expect_tools else []
    kw_hit = [k for k in expect_kw if re.search(re.escape(k), answer, re.I)]
    stage_hit = [s for s in expect_stages if s in (result.get("stages") or [])]

    # Honesty heuristics for gap questions
    honest_phrases = [
        r"cannot", r"can't", r"do not have", r"don't have", r"not available",
        r"no (direct |dedicated )?tool", r"unable to", r"limitation",
        r"not (directly )?supported", r"no structural", r"uncertain",
        r"unknown", r"无法", r"没有.*(工具|数据|能力)", r"目前.*(无法|不能|缺少)",
        r"不确定", r"尚无",
    ]
    looks_honest = any(re.search(p, answer, re.I) for p in honest_phrases)

    # Hallucination risk: gap question with confident numeric/specific claim and no honesty
    halluc_risk = False
    if item.get("expect_honest_gap") and answer and not looks_honest and len(answer) > 200:
        # confident fabrication signals
        if re.search(r"\b(is buried|is exposed|SASA|Å|angstrom|proteoform [A-Z]|definitely|clearly shows)\b", answer, re.I):
            halluc_risk = True

    verdict = "PASS"
    notes = []
    if not result.get("ok"):
        verdict = "FAIL"
        notes.append("request failed")
    elif result.get("errors") and not answer:
        verdict = "FAIL"
        notes.append("SSE error, empty answer")
    else:
        if expect_tools and not tool_hit:
            verdict = "PARTIAL"
            notes.append("expected tools not called")
        if expect_kw and not kw_hit:
            if verdict == "PASS":
                verdict = "PARTIAL"
            notes.append("expected keywords missing")
        if expect_stages and len(stage_hit) < len(expect_stages):
            if verdict == "PASS":
                verdict = "PARTIAL"
            notes.append(f"stages incomplete: {stage_hit}/{expect_stages}")
        if item.get("expect_honest_gap"):
            if looks_honest:
                notes.append("honest gap acknowledgment")
            elif halluc_risk:
                verdict = "FAIL"
                notes.append("possible hallucination on known gap")
            else:
                if verdict == "PASS":
                    verdict = "PARTIAL"
                notes.append("gap question without clear honesty signal")

    return {
        "verdict": verdict,
        "tool_hit": tool_hit,
        "tool_miss": tool_miss,
        "kw_hit": kw_hit,
        "stage_hit": stage_hit,
        "looks_honest": looks_honest,
        "halluc_risk": halluc_risk,
        "score_notes": notes,
    }


def main():
    only = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    items = [q for q in QUESTIONS if not only or q["id"] in only or f"L{q['layer']}" in only]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_path = OUT_DIR / f"results_{stamp}.jsonl"
    summary_path = OUT_DIR / f"summary_{stamp}.md"
    latest_json = OUT_DIR / "latest_results.json"
    latest_md = OUT_DIR / "latest_summary.md"

    print(f"Running {len(items)} questions against {BASE}")
    print(f"Writing to {results_path}")
    all_rows = []

    with results_path.open("w", encoding="utf-8") as fout:
        for i, item in enumerate(items, 1):
            sid = f"eval-{item['id']}-{stamp}"
            print(f"\n[{i}/{len(items)}] {item['id']} ({item['stage']}): {item['q'][:80]}", flush=True)
            result = ask(item["q"], sid)
            scored = score(item, result)
            row = {
                **item,
                **{k: result.get(k) for k in (
                    "ok", "elapsed_s", "conversation_id", "tools_called",
                    "tool_results", "stages", "plan_steps", "answer_len",
                    "errors", "n_sources",
                )},
                "answer_preview": (result.get("answer") or "")[:1200],
                "answer_full": result.get("answer") or "",
                **scored,
            }
            # trim plan for size
            if result.get("plan"):
                row["plan_intent"] = (result["plan"].get("intent_summary")
                                      or result["plan"].get("question"))
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            all_rows.append(row)
            print(
                f"  -> {scored['verdict']} | {result.get('elapsed_s')}s | "
                f"tools={row['tools_called']} | stages={row['stages']} | "
                f"ans_len={row['answer_len']} | {scored['score_notes']}",
                flush=True,
            )

    # summary markdown
    lines = [
        f"# qPTM Agent Eval Report",
        f"",
        f"- Time: `{stamp}`",
        f"- Endpoint: `{BASE}`",
        f"- Questions: {len(all_rows)}",
        f"",
    ]
    by_v = {}
    for r in all_rows:
        by_v[r["verdict"]] = by_v.get(r["verdict"], 0) + 1
    lines.append("## Scoreboard")
    lines.append("")
    lines.append("| Verdict | Count |")
    lines.append("|---|---|")
    for k in ("PASS", "PARTIAL", "FAIL"):
        lines.append(f"| {k} | {by_v.get(k, 0)} |")
    lines.append("")

    for layer in (1, 2, 3, 4):
        layer_rows = [r for r in all_rows if r["layer"] == layer]
        if not layer_rows:
            continue
        titles = {1: "单阶段基础", 2: "跨阶段推理", 3: "能力边界", 4: "鲁棒性"}
        lines.append(f"## Layer {layer}: {titles[layer]}")
        lines.append("")
        lines.append("| ID | Stage | Verdict | Tools | Stages | Time | Notes |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in layer_rows:
            tools = ", ".join(r.get("tools_called") or []) or "—"
            stages = " → ".join(str(s) for s in (r.get("stages") or [])) or "—"
            notes = "; ".join(r.get("score_notes") or []) or r.get("notes", "")
            lines.append(
                f"| {r['id']} | {r['stage']} | **{r['verdict']}** | `{tools}` | {stages} | "
                f"{r.get('elapsed_s')}s | {notes} |"
            )
        lines.append("")
        for r in layer_rows:
            lines.append(f"### {r['id']}. {r['q']}")
            lines.append("")
            lines.append(f"- **Expected focus:** {r.get('notes')}")
            lines.append(f"- **Tools called:** `{r.get('tools_called')}`")
            if r.get("tool_miss"):
                lines.append(f"- **Missing expected tools:** `{r['tool_miss']}`")
            lines.append(f"- **Keyword hits:** `{r.get('kw_hit')}`")
            lines.append(f"- **Honest gap signal:** {r.get('looks_honest')}")
            if r.get("halluc_risk"):
                lines.append(f"- **Hallucination risk:** YES")
            preview = (r.get("answer_preview") or "").replace("\n", " ")[:500]
            lines.append(f"- **Answer preview:** {preview}…")
            lines.append("")

    md = "\n".join(lines)
    summary_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    latest_json.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone. Summary: {summary_path}")
    print(f"Scoreboard: {by_v}")


if __name__ == "__main__":
    main()
