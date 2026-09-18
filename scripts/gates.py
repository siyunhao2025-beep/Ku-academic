#!/usr/bin/env python3
"""The five-gate validation pipeline for manuscript paragraphs.

Gate order is fixed and not configurable. There is deliberately no --only or
--skip flag: the specification requires strict sequencing, and the cheapest way
to guarantee a rule is to not provide the switch that breaks it.

  1 content_filter    block the writing assistant talking about itself
  2 topic_anchoring  每句回到全文核心主旨
  3 bullseye         science-question alignment, text-figure match, data narrative
  4 deai_polish      remove templated phrasing without changing meaning
  5 citation         reference resolution and placement, conclusion box included

Red-lock integrity is re-verified at the boundary of every gate that may alter
text. If a rewritten paragraph loses, changes or invents a red-locked fact, that
gate rejects for the whole paragraph -- the gate cannot pass it through.

Two honesty rules are built in rather than documented only:

* Gate 1 must not delete a sentence that describes the study's own model or
  algorithm. That false positive is called out in the specification, so the
  discriminator between "the study's model" and "the writing assistant" is
  implemented, and ambiguous hits are flagged for semantic review instead of
  being silently dropped.
* Gate 3 compares text against figure data only when figure data was actually
  provided. If none was provided it reports cannot_check. It never guesses what a
  figure shows.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import locks  # noqa: E402

GATES = ("content_filter", "topic_anchoring", "bullseye", "deai_polish", "citation")
BOXES = ("intro", "data", "results", "conclusion")

# Gate 1
BLACKLIST = ("大模型", "LLM", "上下文窗口", "token", "算力受限", "模型限制", "AI助手",
             "AI 助手", "无法处理", "受限于模型能力", "上下文长度", "context window",
             "token limit", "as an ai", "language model")
AI_SELF = ("作为 ai", "作为ai", "我是一个", "作为一个语言模型", "我的上下文", "本次对话",
           "当前对话", "写作助手", "我无法处理", "我不能处理", "我的算力", "这个对话",
           "本轮对话", "我的能力限制")
STUDY_MARKERS = ("本研究", "本文", "我们", "研究模型", "该模型", "训练", "数据集",
                 "算法", "观测", "实验", "方法", "模型架构", "our study", "we ")

# Gate 2 / 3
LINK_MARKERS = ("为了", "旨在", "在于", "目的是", "用以", "说明", "表明", "显示",
                "支撑", "支持", "对应", "反映了", "印证", "检验", "回答",
                "we therefore", "in order to", "aim", "demonstrat", "indicat", "support")
INTERPRET_MARKERS = ("表明", "说明", "相比", "高于", "低于", "大于", "小于", "对比",
                     "异常", "一致", "差异", "倍", "显著", "相反", "符合", "偏离",
                     "compared", "higher", "lower", "consistent", "in contrast",
                     "difference", "times", "anomal")
FIG_CITE = re.compile(r"(?:Fig(?:ure)?\.?|图)\s*([0-9]+[a-z]?)", re.IGNORECASE)

# Gate 4
DEAI_CLICHES = ("综上所述", "总而言之", "众所周知", "不言而喻", "值得注意的是",
                "需要指出的是", "从某种意义上说", "毫无疑问", "plays an important role",
                "it is worth noting", "in conclusion", "furthermore, it is")
TRIPLE_PARALLEL = re.compile(r"(.{4,20})[，,]\1[，,]\1")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------- gate 1
def gate_content_filter(text, **_):
    hits, rejected, flagged, passed = [], [], [], []
    for sentence in locks.sentences(text):
        low = sentence.lower()
        matched = [w for w in BLACKLIST if w.lower() in low]
        if not matched:
            continue
        self_ref = [w for w in AI_SELF if w.lower() in low]
        study = [w for w in STUDY_MARKERS if w.lower() in low]
        entry = {"sentence": sentence, "keywords": matched,
                 "ai_self_markers": self_ref, "study_markers": study}
        if self_ref:
            entry["decision"] = "reject"
            rejected.append(entry)
        elif study:
            # Hard constraint: a sentence about the study's own model or algorithm
            # must survive, even though it mentions a blacklisted word.
            entry["decision"] = "pass_as_study_description"
            passed.append(entry)
        else:
            entry["decision"] = "flag_for_semantic_review"
            flagged.append(entry)
        hits.append(entry)
    if rejected:
        verdict, report = "reject", ("%d sentence(s) narrate the writing assistant itself; "
                                     "regenerate without meta-narration" % len(rejected))
    elif flagged:
        verdict, report = "flag", ("%d sentence(s) matched the blacklist and need semantic "
                                   "review; none may be deleted before that review" % len(flagged))
    else:
        verdict, report = "pass", ("no meta-narration; %d study-description mention(s) kept"
                                   % len(passed))
    return {"verdict": verdict, "report": report,
            "details": {"hits": hits, "rejected": len(rejected), "flagged": len(flagged),
                        "passed_as_study": len(passed)}}


# --------------------------------------------------------------- gate 2
def _anchor_terms(manuscript):
    terms = set()
    for chunk in [manuscript.get("core_thesis", "")] + list(manuscript.get("core_questions", [])):
        terms |= locks._content_terms(chunk)
    return terms


def gate_topic_anchoring(text, *, manuscript, box, **_):
    anchors = _anchor_terms(manuscript)
    questions = manuscript.get("core_questions", [])
    rows, weak, off = [], [], []
    for sentence in locks.sentences(text):
        terms = locks._content_terms(sentence)
        shared = sorted(terms & anchors)
        rows.append({"sentence": sentence, "shared_anchors": shared})

    doc_shared = sorted({t for row in rows for t in row["shared_anchors"]})
    best = None
    if questions and doc_shared:
        scored = []
        for q in questions:
            overlap = len(locks._content_terms(q) & set(doc_shared))
            scored.append((overlap, q))
        scored.sort(reverse=True)
        if scored[0][0] > 0:
            best = scored[0][1]

    for row in rows:
        if row["shared_anchors"]:
            continue
        (off if not doc_shared else weak).append(row["sentence"])

    if not anchors:
        return {"verdict": "flag",
                "report": "no core thesis or core questions were supplied, so anchoring "
                          "cannot be judged; record them first",
                "details": {"cannot_check": True}}
    if box in ("results", "conclusion") and not doc_shared:
        verdict, report = "reject", ("the paragraph shares no term with the core thesis; "
                                     "results and conclusions must serve the main line")
    elif off:
        verdict, report = "reject", ("%d sentence(s) are unrelated to the core thesis even "
                                     "though the paragraph does relate" % len(off))
    elif weak:
        verdict, report = "flag", ("%d sentence(s) carry no anchor term; add a link sentence "
                                   "explaining how they serve the core question" % len(weak))
    else:
        verdict, report = "pass", "every sentence shares at least one anchor with the core thesis"
    return {"verdict": verdict, "report": report,
            "details": {"paragraph_anchors": doc_shared, "supports_question": best,
                        "weak_sentences": weak, "off_topic_sentences": off,
                        "method": "heuristic_term_overlap (semantic judgement stays with the model)"}}


# --------------------------------------------------------------- gate 3
def gate_bullseye(text, *, paragraph, box, **_):
    sentences = locks.sentences(text)
    figures = paragraph.get("figures", []) or []
    cited = sorted({m for m in FIG_CITE.findall(text)})
    declared = sorted({str(f.get("id", "")).lstrip("Figfigure.图 ") for f in figures})

    # (1) science-question alignment
    linky = any(m in text for m in LINK_MARKERS)
    quantities = [f for f in locks.extract(text)["facts"] if f["level"] == "red"]
    off_target = bool(quantities) and not linky and box in ("results", "conclusion")

    # (2) text-figure match, only against figures that were actually provided
    figure_problems, figure_status = [], "cannot_check"
    if figures:
        figure_status = "checked"
        for c in cited:
            if declared and c not in declared:
                figure_problems.append({"type": "figure_not_declared", "figure": c,
                                        "detail": "text cites a figure that was not provided"})
        declared_values = {str(v) for f in figures for v in (f.get("values") or [])}
        if declared_values:
            untraceable = sorted({q["value"] for q in quantities
                                  if q["value"] not in declared_values})
            for value in untraceable:
                    figure_problems.append({
                        "type": "number_not_found_in_figure",
                        "value": value,
                        "detail": "this number is not among the provided figure values; "
                                  "confirm it comes from elsewhere in the paper"})

    # (3) data narrative
    dumpy = []
    for sentence in sentences:
        reds = [f for f in locks.extract(sentence)["facts"] if f["level"] == "red"]
        if len(reds) >= 2 and not any(m in sentence for m in INTERPRET_MARKERS):
            dumpy.append(sentence)

    hard = [p for p in figure_problems if p["type"] == "figure_not_declared"]
    if hard:
        verdict, report = "reject", "text cites figure(s) that were not provided: %s" % (
            ", ".join(p["figure"] for p in hard))
    elif off_target:
        verdict, report = "reject", ("the paragraph reports quantities without stating which "
                                     "science question they answer; name the target explicitly")
    elif figure_problems or dumpy:
        verdict, report = "flag", ("%d figure note(s), %d data-listing sentence(s); "
                                   "improve before archiving" % (len(figure_problems), len(dumpy)))
    else:
        verdict, report = "pass", "on target, figure text consistent, data interpreted"
    return {"verdict": verdict, "report": report,
            "details": {"figures_cited": cited, "figures_declared": declared,
                        "figure_status": figure_status, "figure_problems": figure_problems,
                        "off_target": off_target, "data_listing_sentences": dumpy,
                        "interpretation_markers_present": linky}}


# --------------------------------------------------------------- gate 4
def gate_deai_polish(text, *, paragraph, domain_terms=(), text_after=None, **_):
    sentences = locks.sentences(text)
    cliches = [c for c in DEAI_CLICHES if c in text]
    triples = TRIPLE_PARALLEL.findall(text)
    lengths = [len(s) for s in sentences]
    spread = round(statistics.pstdev(lengths), 1) if len(lengths) > 1 else 0.0
    uniform = len(lengths) >= 4 and spread < max(2.0, 0.15 * (sum(lengths) / len(lengths)))
    dashes = text.count("—") + text.count("——")

    notes = []
    if uniform:
        notes.append("sentence lengths are near-uniform (spread %.1f); vary rhythm rather "
                     "than deleting adverbs" % spread)
    if triples:
        notes.append("%d triple parallelism found; keep at most one" % len(triples))
    if dashes >= 4:
        notes.append("dash density high (%d)" % dashes)

    result = {"cliche_phrases": cliches, "triple_parallelism": triples,
              "sentence_length_spread": spread, "uniform_rhythm": uniform,
              "dash_count": dashes, "notes": notes}

    # The part that actually protects the paper: nothing red may move.
    if text_after is not None:
        integrity = locks.verify(text, text_after, list(domain_terms))
        result["red_lock_check"] = integrity
        if not integrity["ok"]:
            return {"verdict": "reject",
                    "report": "polish changed protected facts: missing=%s changed=%s "
                              "added=%s escalated_lost=%s"
                              % (integrity["red_missing"], integrity["red_changed"],
                                 integrity["red_added"], integrity["red_escalated_lost"]),
                    "details": result}
    elif not notes and not cliches:
        return {"verdict": "flag",
                "report": "no polish result was supplied, so the red-lock check could not "
                          "run. Supply text_after (identical text is a valid answer) to "
                          "complete this gate; an unverified polish cannot be archived",
                "details": result}

    if cliches or notes:
        verdict, report = "flag", "polish needed: " + "; ".join(
            ([("%d cliche phrase(s)" % len(cliches))] if cliches else []) + notes)
    else:
        verdict, report = "pass", "no templated phrasing detected; red locks intact"
    return {"verdict": verdict, "report": report, "details": result}


# --------------------------------------------------------------- gate 5
def gate_citation(text, *, paragraph, manuscript, box, min_conclusion_citations=2, **_):
    references = {r.get("key"): r for r in manuscript.get("references", [])}
    unknown, uncited = [], []
    for sentence in locks.sentences(text):
        cited_here = [k for k in references if k and k in sentence]
        reds = [f for f in locks.extract(sentence)["facts"] if f["level"] == "red"]
        if reds and not cited_here and box in ("results", "conclusion"):
            uncited.append(sentence)

    for key in paragraph.get("citations", []) or []:
        if key not in references:
            unknown.append(key)

    total = sum(len(p.get("citations", []) or []) for p in manuscript.get("paragraphs", [])
                if p.get("box") == "conclusion")
    hint_terms = [t.lower() for t in manuscript.get("citation_domain_keywords", [])]
    recommendations = []
    if box == "conclusion":
        for key, ref in references.items():
            blob = ("%s %s" % (ref.get("title", ""), ref.get("abstract", ""))).lower()
            if hint_terms and any(t in blob for t in hint_terms):
                recommendations.append({"key": key, "title": ref.get("title", ""),
                                        "reason": "matches the project's citation domain keywords"})

    if unknown:
        verdict, report = "reject", "citation key(s) not present in the reference list: %s" % (
            ", ".join(unknown))
    elif box == "conclusion" and total < min_conclusion_citations:
        verdict, report = "flag", ("the conclusion box cites %d reference(s), below the "
                                   "configured minimum of %d; add relevant support at the "
                                   "comparison, limitation or outlook sentences"
                                   % (total, min_conclusion_citations))
    elif uncited:
        verdict, report = "flag", ("%d quantitative sentence(s) in the %s box carry no "
                                   "citation" % (len(uncited), box))
    else:
        verdict, report = "pass", "every citation resolves; placement is adequate"
    return {"verdict": verdict, "report": report,
            "details": {"unknown_keys": unknown, "uncited_quantitative": uncited,
                        "conclusion_citations_total": total,
                        "recommended_existing_references": recommendations,
                        "note": "recommendations reuse references already in the list; "
                                "this module never invents a reference"}}


DISPATCH = {
    "content_filter": gate_content_filter,
    "topic_anchoring": gate_topic_anchoring,
    "bullseye": gate_bullseye,
    "deai_polish": gate_deai_polish,
    "citation": gate_citation,
}


def run_pipeline(manuscript, domain_terms=None, min_conclusion_citations=2):
    domain_terms = list(domain_terms or manuscript.get("domain_keywords", []) or [])
    results = []
    for paragraph in manuscript.get("paragraphs", []):
        pid = paragraph.get("id", "?")
        box = paragraph.get("box", "results")
        original = paragraph.get("text", "")
        current = original
        chain, blocked_at = [], None
        for gate_id in GATES:                       # fixed order, no skipping
            kwargs = {"manuscript": manuscript, "paragraph": paragraph, "box": box,
                      "domain_terms": domain_terms,
                      "min_conclusion_citations": min_conclusion_citations}
            if gate_id == "deai_polish":
                kwargs["text_after"] = paragraph.get("text_after")
            outcome = DISPATCH[gate_id](current, **kwargs)
            outcome = dict(outcome, gate=gate_id)
            if gate_id == "deai_polish" and paragraph.get("text_after") and outcome["verdict"] != "reject":
                current = paragraph["text_after"]
            chain.append(outcome)
            if outcome["verdict"] == "reject":
                blocked_at = gate_id
                break
        results.append({"id": pid, "box": box, "blocked_at": blocked_at,
                        "final_verdict": ("rejected" if blocked_at else
                                          ("flagged" if any(g["verdict"] == "flag" for g in chain)
                                           else "passed")),
                        "gates": chain,
                        "gates_not_run": list(GATES[len(chain):])})
    summary = {
        "paragraphs": len(results),
        "passed": sum(1 for r in results if r["final_verdict"] == "passed"),
        "flagged": sum(1 for r in results if r["final_verdict"] == "flagged"),
        "rejected": sum(1 for r in results if r["final_verdict"] == "rejected"),
        "blocked_at": {g: sum(1 for r in results if r["blocked_at"] == g) for g in GATES},
        "archivable": [r["id"] for r in results if r["final_verdict"] == "passed"],
        "not_archivable": [r["id"] for r in results if r["final_verdict"] != "passed"],
    }
    return {"created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "core_thesis": manuscript.get("core_thesis", ""),
            "gate_order": list(GATES),
            "domain_terms": domain_terms,
            "results": results, "summary": summary}


def render_report(ledger):
    lines = ["# 五道关卡校验报告", ""]
    lines.append("- 核心主旨：%s" % (ledger.get("core_thesis") or "(未提供)"))
    lines.append("- 关卡顺序：%s" % " → ".join(ledger["gate_order"]))
    lines.append("- 生成时间：%s" % ledger.get("created", ""))
    lines.append("")
    s = ledger["summary"]
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 结果 | 段落数 |")
    lines.append("|---|---|")
    lines.append("| 全部通过（可入库） | %d |" % s["passed"])
    lines.append("| 需修改（flag） | %d |" % s["flagged"])
    lines.append("| 驳回（需重写） | %d |" % s["rejected"])
    lines.append("")
    lines.append("**可入库段落：** %s" % (", ".join(s["archivable"]) or "无"))
    lines.append("")
    lines.append("**不可入库段落：** %s" % (", ".join(s["not_archivable"]) or "无"))
    lines.append("")
    for r in ledger["results"]:
        lines.append("## %s（%s 箱）→ %s" % (r["id"], r["box"], r["final_verdict"]))
        lines.append("")
        for g in r["gates"]:
            lines.append("- **[%s] %s** — %s" % (g["gate"], g["verdict"], g["report"]))
        if r["gates_not_run"]:
            lines.append("- _未执行（前序驳回）：%s_" % ", ".join(r["gates_not_run"]))
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Five-gate manuscript validation pipeline")
    sub = ap.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run all five gates in fixed order")
    r.add_argument("manuscript")
    r.add_argument("--out", required=True)
    r.add_argument("--report", default="")
    r.add_argument("--domain-terms", nargs="*", default=None)
    r.add_argument("--min-conclusion-citations", type=int, default=2)

    p = sub.add_parser("report", help="render a gates.json as Markdown")
    p.add_argument("gates")
    p.add_argument("--out", default="")

    args = ap.parse_args(argv)
    try:
        if args.command == "run":
            ledger = run_pipeline(read_json(args.manuscript), args.domain_terms,
                                  args.min_conclusion_citations)
            write_json(args.out, ledger)
            if args.report:
                Path(args.report).parent.mkdir(parents=True, exist_ok=True)
                Path(args.report).write_text(render_report(ledger), encoding="utf-8")
            s = ledger["summary"]
            print("gates: %s" % args.out)
            print("passed=%d flagged=%d rejected=%d" % (s["passed"], s["flagged"], s["rejected"]))
            print("archivable: %s" % (", ".join(s["archivable"]) or "none"))
            return 0
        ledger = read_json(args.gates)
        text = render_report(ledger)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
            print("report: %s" % args.out)
        else:
            print(text)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
