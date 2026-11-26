#!/usr/bin/env python3
"""Simulated reviewer panel: 3-5 professional reviewers, scored independently.

Deliberate design choices, because they are the difference between a useful panel
and a flattering one:

* Reviewers are distinct personas and are never averaged together. Disagreement
  between reviewers is reported as its own outcome, because it is the single most
  informative thing a panel produces.
* A panel that finds no scientific objections fails the panel check rather than
  passing it. Silence about the science is not a clean review.
* Every non-positive finding needs one structured response before a high-scoring
  panel can move to human submission review. Coverage is not adequacy.
* There is no acceptance probability and no acceptance guarantee anywhere in this
  module. The strongest label it can emit is a readiness-for-human-check label.

This module never edits the manuscript and never invents new results, sample sizes
or analyses to satisfy a reviewer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

# Seven dimensions, 0-5 each. Same rubric as docs/PHASE_GATES.md Gate 5.
DIMENSIONS = [
    ("argument_clarity", "论证清晰度"),
    ("completeness", "完整性"),
    ("literature_support", "文献支持"),
    ("method_clarity", "方法清晰度"),
    ("originality_expression", "原创性表达"),
    ("organization", "组织与衔接"),
    ("platform_fit", "与目标期刊契合度"),
]
MAX_PER_DIMENSION = 5
PANEL_TOTAL = MAX_PER_DIMENSION * len(DIMENSIONS)   # 35
PASS_THRESHOLD = 28
DISAGREEMENT_SPREAD = 7
MIN_SCIENCE_FINDINGS = 3

REVIEW_INPUTS = [
    ("manuscript", "当前完整稿件"),
    ("journal_scope", "目标期刊范围与文章类型"),
    ("citation_audit", "引用身份与句子支持审计"),
    ("claim_evidence", "主张—证据审计"),
    ("figure_table", "图表审计"),
    ("methods_reporting_compliance", "方法、报告与合规审计"),
    ("reproducibility", "数据、代码与复现材料"),
]
REQUIRED_REVIEW_INPUTS = tuple(item_id for item_id, _ in REVIEW_INPUTS)
REVIEW_COVERAGE_STATUSES = ("REVIEWED", "PARTIAL", "MISSING", "SKIPPED")

SEVERITIES = ("blocker", "major", "minor", "positive")
FINDING_KINDS = ("science", "format")
STATUSES = ("open", "resolved", "author_decision")
RESPONSE_DISPOSITIONS = (
    "REVISED",
    "EVIDENCE_BASED_REBUTTAL",
    "AUTHOR_ACCEPTED_LIMITATION",
)

PERSONAS = {
    "handling-editor": {
        "role": "处理编辑",
        "focus": "范围与目标期刊是否契合、贡献是否足以支撑一篇完整论文、篇幅与结构是否成比例",
        "asks": "这篇稿件如果送到我手上，我会不会直接送审？如果不送，缺的是哪一块？",
    },
    "domain-expert": {
        "role": "领域专家",
        "focus": "论证链条是否成立、文献是否覆盖到真正的竞争性解释、结论是否超前于证据",
        "asks": "作者最关键的论断，被最强的反面证据检验过吗？",
    },
    "methods-reviewer": {
        "role": "方法与统计审稿人",
        "focus": "设计、匹配、基线、不确定度口径、样本与重采样单位、多重比较、稳健性",
        "asks": "把方法按原样重做一遍，结论还站得住吗？哪些参数决定了结论方向？",
    },
    "skeptical-reviewer": {
        "role": "怀疑论者",
        "focus": "反例、替代解释、过度声称、把关联写成因果、把计划写成已完成",
        "asks": "如果结论是错的，最可能错在哪一步？作者有没有排除它？",
    },
    "reproducibility-reviewer": {
        "role": "可复现性审稿人",
        "focus": "数据与代码可得性、运行记录、版本与环境、图件能否由源数据重建",
        "asks": "另一个人拿到这些材料，能复现出同一个数吗？",
    },
}
DEFAULT_PANEL = ["handling-editor", "domain-expert", "methods-reviewer", "skeptical-reviewer"]


def _default_review_coverage():
    return [{
        "input_id": input_id,
        "status": "MISSING",
        "evidence_locator": "",
        "reason": "not yet reviewed",
    } for input_id in REQUIRED_REVIEW_INPUTS]


def build_panel(manuscript, reviewers=None, context=""):
    ids = list(reviewers) if reviewers else list(DEFAULT_PANEL)
    if not 3 <= len(ids) <= 5:
        raise ValueError("panel size must be 3 to 5 reviewers, got %d" % len(ids))
    unknown = [r for r in ids if r not in PERSONAS]
    if unknown:
        raise ValueError("unknown reviewer(s): " + ", ".join(unknown))
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate reviewer in panel")
    return {
        "manuscript": str(manuscript),
        "context": context,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rubric": {"dimensions": [{"id": d, "label": l} for d, l in DIMENSIONS],
                   "scale": "0-%d per dimension" % MAX_PER_DIMENSION,
                   "panel_total": PANEL_TOTAL,
                   "pass_threshold": PASS_THRESHOLD,
                   "min_science_findings": MIN_SCIENCE_FINDINGS},
        "rules": [
            "Reviewers are scored independently and are never averaged into one number.",
            "Disagreement between reviewers is a first-class outcome, not noise.",
            "At least %d findings must concern scientific content, not formatting." % MIN_SCIENCE_FINDINGS,
            "Every non-positive finding needs one traceable point-by-point response before readiness.",
            "Do not invent new results, sample sizes or analyses to satisfy a reviewer.",
            "Never state an acceptance probability. The strongest label is readiness for human check.",
        ],
        "reviewers": [{
            "id": rid,
            "role": PERSONAS[rid]["role"],
            "focus": PERSONAS[rid]["focus"],
            "asks": PERSONAS[rid]["asks"],
            "scores": {d: None for d, _ in DIMENSIONS},
            "total": None,
            "verdict": "not_scored",
            "findings": [],
        } for rid in ids],
        "review_coverage": _default_review_coverage(),
        "panel_verdict": "INCOMPLETE",
        "verdict_reason": "no reviewer has been scored yet",
    }


def _reviewer(panel, rid):
    for r in panel["reviewers"]:
        if r["id"] == rid:
            return r
    raise ValueError("unknown reviewer id: " + rid)


def score_reviewer(panel, rid, scores, note=""):
    """scores: dict dimension->int. All seven required before a verdict is possible."""
    reviewer = _reviewer(panel, rid)
    for key, value in scores.items():
        if key not in dict(DIMENSIONS):
            raise ValueError("unknown dimension: " + key)
        value = int(value)
        if not 0 <= value <= MAX_PER_DIMENSION:
            raise ValueError("score for %s must be 0-%d" % (key, MAX_PER_DIMENSION))
        reviewer["scores"][key] = value
    if note:
        reviewer["note"] = note
    complete = all(v is not None for v in reviewer["scores"].values())
    reviewer["total"] = sum(reviewer["scores"].values()) if complete else None
    reviewer["verdict"] = ("meets_bar" if reviewer["total"] >= PASS_THRESHOLD else "below_bar") \
        if complete else "not_scored"
    return reviewer


def add_finding(panel, rid, severity, location, comment, kind="science", requires_author_data=False):
    reviewer = _reviewer(panel, rid)
    if severity not in SEVERITIES:
        raise ValueError("severity must be one of: " + ", ".join(SEVERITIES))
    if kind not in FINDING_KINDS:
        raise ValueError("kind must be one of: " + ", ".join(FINDING_KINDS))
    if not str(location).strip():
        raise ValueError("a finding must name an exact location")
    if not str(comment).strip():
        raise ValueError("a finding must contain the objection")
    finding = {
        "id": "%s.%d" % (rid, len(reviewer["findings"]) + 1),
        "severity": severity,
        "kind": kind,
        "location": location,
        "comment": comment,
        "requires_author_data": bool(requires_author_data),
        "status": "open",
    }
    reviewer["findings"].append(finding)
    return finding


def resolve_finding(panel, rid, finding_id, status, note=""):
    reviewer = _reviewer(panel, rid)
    if status not in STATUSES:
        raise ValueError("status must be one of: " + ", ".join(STATUSES))
    for f in reviewer["findings"]:
        if f["id"] == finding_id:
            f["status"] = status
            if note:
                f["note"] = note
            return f
    raise ValueError("unknown finding id: " + finding_id)


def _finding_by_id(panel, finding_id):
    findings = [finding for reviewer in panel.get("reviewers", [])
                for finding in reviewer.get("findings", [])]
    if any(not isinstance(finding, dict) for finding in findings):
        raise ValueError("every finding must be an object")
    matches = [finding for finding in findings if finding.get("id") == finding_id]
    if not matches:
        raise ValueError("unknown finding id: " + finding_id)
    if len(matches) > 1:
        raise ValueError("duplicate finding id: " + finding_id)
    return matches[0]


def record_response(panel, finding_id, disposition, response, change_locator="",
                    evidence_locator="", reason="", author_approved=False):
    """Attach one structured point-by-point response to an actionable finding."""
    finding = _finding_by_id(panel, finding_id)
    if finding.get("severity") == "positive":
        raise ValueError("positive findings do not require a response: " + finding_id)
    if "response" in finding:
        raise ValueError("finding already has a response: " + finding_id)
    disposition = str(disposition).upper()
    response = str(response).strip()
    change_locator = str(change_locator).strip()
    evidence_locator = str(evidence_locator).strip()
    reason = str(reason).strip()
    if disposition not in RESPONSE_DISPOSITIONS:
        raise ValueError("disposition must be one of: " + ", ".join(RESPONSE_DISPOSITIONS))
    if not response:
        raise ValueError("response text is required")
    if disposition == "REVISED" and not change_locator:
        raise ValueError("REVISED response requires a change locator")
    if disposition == "EVIDENCE_BASED_REBUTTAL" and not evidence_locator:
        raise ValueError("EVIDENCE_BASED_REBUTTAL requires an evidence locator")
    if disposition == "AUTHOR_ACCEPTED_LIMITATION":
        if not reason:
            raise ValueError("AUTHOR_ACCEPTED_LIMITATION requires a reason")
        if author_approved is not True:
            raise ValueError("AUTHOR_ACCEPTED_LIMITATION requires author_approved=true")
    finding["response"] = {
        "disposition": disposition,
        "response": response,
        "change_locator": change_locator,
        "evidence_locator": evidence_locator,
        "reason": reason,
        "author_approved": (
            disposition == "AUTHOR_ACCEPTED_LIMITATION" and author_approved is True
        ),
    }
    return finding["response"]


def response_coverage_state(panel):
    """Return exact-ID response coverage without scoring response adequacy."""
    seen = set()
    actionable = []
    covered = []
    gaps = []
    for reviewer in panel.get("reviewers", []):
        for finding in reviewer.get("findings", []):
            if not isinstance(finding, dict):
                raise ValueError("every finding must be an object")
            finding_id = finding.get("id")
            if not isinstance(finding_id, str) or not finding_id.strip():
                raise ValueError("every finding needs a non-empty id")
            if finding_id in seen:
                raise ValueError("duplicate finding id: " + finding_id)
            seen.add(finding_id)
            if finding.get("severity") == "positive":
                if "response" in finding:
                    raise ValueError("positive findings do not require a response: " + finding_id)
                continue
            actionable.append(finding_id)
            response = finding.get("response")
            if response is None:
                gaps.append({"finding_id": finding_id, "status": "MISSING"})
                continue
            if not isinstance(response, dict):
                raise ValueError("response must be an object: " + finding_id)
            disposition = response.get("disposition")
            if disposition not in RESPONSE_DISPOSITIONS:
                raise ValueError("invalid response disposition for %s: %s"
                                 % (finding_id, disposition))
            if not str(response.get("response", "")).strip():
                raise ValueError("response text is required: " + finding_id)
            if disposition == "REVISED" and not str(response.get("change_locator", "")).strip():
                raise ValueError("REVISED response requires a change locator: " + finding_id)
            if (disposition == "EVIDENCE_BASED_REBUTTAL"
                    and not str(response.get("evidence_locator", "")).strip()):
                raise ValueError(
                    "EVIDENCE_BASED_REBUTTAL requires an evidence locator: " + finding_id)
            if disposition == "AUTHOR_ACCEPTED_LIMITATION":
                if not str(response.get("reason", "")).strip():
                    raise ValueError(
                        "AUTHOR_ACCEPTED_LIMITATION requires a reason: " + finding_id)
                if response.get("author_approved") is not True:
                    raise ValueError(
                        "AUTHOR_ACCEPTED_LIMITATION requires author_approved=true: " + finding_id)
            covered.append(finding_id)
    return actionable, covered, gaps


def record_coverage(panel, input_id, status, evidence_locator="", reason=""):
    """Record whether one required upstream input was actually reviewed."""
    if input_id not in REQUIRED_REVIEW_INPUTS:
        raise ValueError("unknown review input: " + str(input_id))
    status = str(status).upper()
    if status not in REVIEW_COVERAGE_STATUSES:
        raise ValueError("coverage status must be one of: " + ", ".join(REVIEW_COVERAGE_STATUSES))
    evidence_locator = str(evidence_locator).strip()
    reason = str(reason).strip()
    if status == "REVIEWED" and not evidence_locator:
        raise ValueError("REVIEWED coverage requires an evidence locator")
    if status != "REVIEWED" and not reason:
        raise ValueError("%s coverage requires a reason" % status)

    coverage = panel.get("review_coverage")
    if coverage is None:
        coverage = _default_review_coverage()
        panel["review_coverage"] = coverage
    if not isinstance(coverage, list):
        raise ValueError("review_coverage must be a list")
    matches = [item for item in coverage
               if isinstance(item, dict) and item.get("input_id") == input_id]
    if len(matches) > 1:
        raise ValueError("duplicate review coverage input: " + input_id)
    if matches:
        entry = matches[0]
    else:
        entry = {"input_id": input_id}
        coverage.append(entry)
    entry.update({
        "status": status,
        "evidence_locator": evidence_locator,
        "reason": reason,
    })
    return entry


def review_coverage_state(panel):
    """Return normalized entries and explicit gaps without trusting file existence."""
    coverage = panel.get("review_coverage")
    if coverage is None:
        coverage = []
    if not isinstance(coverage, list):
        raise ValueError("review_coverage must be a list")

    indexed = {}
    for index, item in enumerate(coverage):
        if not isinstance(item, dict):
            raise ValueError("review_coverage entry %d must be an object" % index)
        input_id = item.get("input_id")
        if input_id not in REQUIRED_REVIEW_INPUTS:
            raise ValueError("unknown review input: " + str(input_id))
        if input_id in indexed:
            raise ValueError("duplicate review coverage input: " + input_id)
        status = item.get("status")
        if status not in REVIEW_COVERAGE_STATUSES:
            raise ValueError("invalid coverage status for %s: %s" % (input_id, status))
        locator = str(item.get("evidence_locator", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if status == "REVIEWED" and not locator:
            raise ValueError("REVIEWED coverage requires an evidence locator: " + input_id)
        if status != "REVIEWED" and not reason:
            raise ValueError("%s coverage requires a reason: %s" % (status, input_id))
        indexed[input_id] = {
            "input_id": input_id,
            "status": status,
            "evidence_locator": locator,
            "reason": reason,
        }

    entries = []
    gaps = []
    for input_id in REQUIRED_REVIEW_INPUTS:
        entry = indexed.get(input_id, {
            "input_id": input_id,
            "status": "MISSING",
            "evidence_locator": "",
            "reason": "coverage was not recorded",
        })
        entries.append(entry)
        if entry["status"] != "REVIEWED":
            gaps.append({
                "input_id": input_id,
                "status": entry["status"],
                "reason": entry["reason"],
            })
    return entries, gaps


def compute_verdict(panel):
    reviewers = panel["reviewers"]
    scored = [r for r in reviewers if r["total"] is not None]
    totals = [r["total"] for r in scored]
    findings = [f for r in reviewers for f in r["findings"]]
    open_findings = [f for f in findings if f["status"] == "open"]
    science = [f for f in findings if f["kind"] == "science"]
    blockers = [f for f in open_findings if f["severity"] == "blocker"]
    coverage, coverage_gaps = review_coverage_state(panel)
    actionable_responses, covered_responses, response_gaps = response_coverage_state(panel)
    panel["review_coverage"] = coverage

    if len(scored) < len(reviewers):
        verdict, reason = "INCOMPLETE", (
            "%d of %d reviewers scored; every reviewer must be scored before a verdict"
            % (len(scored), len(reviewers)))
    elif blockers:
        verdict, reason = "BLOCKED", (
            "%d open blocker finding(s): %s"
            % (len(blockers), ", ".join(f["id"] for f in blockers)))
    elif len(science) < MIN_SCIENCE_FINDINGS:
        verdict, reason = "INSUFFICIENT_SCIENTIFIC_COVERAGE", (
            "only %d scientific finding(s); a panel that raises no scientific objection has not "
            "reviewed the science" % len(science))
    elif max(totals) - min(totals) > DISAGREEMENT_SPREAD:
        verdict, reason = "PANEL_DISAGREEMENT", (
            "spread of %d points (max %d, min %d) exceeds %d; do not average this away, "
            "the author decides" % (max(totals) - min(totals), max(totals), min(totals),
                                    DISAGREEMENT_SPREAD))
    elif coverage_gaps:
        verdict, reason = "REVIEW_COVERAGE_INCOMPLETE", (
            "%d required review input(s) were not fully reviewed: %s"
            % (len(coverage_gaps), ", ".join(
                "%s=%s" % (item["input_id"], item["status"])
                for item in coverage_gaps)))
    elif min(totals) >= PASS_THRESHOLD and response_gaps:
        verdict, reason = "RESPONSE_COVERAGE_INCOMPLETE", (
            "%d actionable reviewer finding(s) have no point-by-point response: %s"
            % (len(response_gaps), ", ".join(item["finding_id"] for item in response_gaps)))
    elif min(totals) >= PASS_THRESHOLD:
        verdict, reason = "READY_FOR_HUMAN_SUBMISSION_CHECK", (
            "all %d reviewers scored >= %d/%d" % (len(scored), PASS_THRESHOLD, PANEL_TOTAL))
    else:
        below = [r["id"] for r in scored if r["total"] < PASS_THRESHOLD]
        verdict, reason = "REVISION_REQUIRED", (
            "below bar: " + ", ".join("%s=%d" % (r["id"], r["total"])
                                      for r in scored if r["total"] < PASS_THRESHOLD)
            + (" (reviewers: %s)" % ", ".join(below) if below else ""))

    panel["panel_verdict"] = verdict
    panel["verdict_reason"] = reason
    panel["summary"] = {
        "reviewers": len(reviewers),
        "scored": len(scored),
        "totals": {r["id"]: r["total"] for r in reviewers},
        "spread": (max(totals) - min(totals)) if totals else None,
        "findings": len(findings),
        "open_findings": len(open_findings),
        "science_findings": len(science),
        "format_findings": len(findings) - len(science),
        "blockers": len(blockers),
        "review_inputs": len(coverage),
        "reviewed_inputs": len(coverage) - len(coverage_gaps),
        "coverage_gaps": coverage_gaps,
        "actionable_responses": len(actionable_responses),
        "covered_responses": len(covered_responses),
        "response_gaps": response_gaps,
        "acceptance_probability": "not_estimated",
    }
    return panel


def render_report(panel):
    lines = []
    lines.append("# 审稿人评审意见")
    lines.append("")
    lines.append("- 稿件：%s" % panel.get("manuscript", ""))
    lines.append("- 审稿人数：%d" % len(panel["reviewers"]))
    lines.append("- 生成时间：%s" % panel.get("created", ""))
    lines.append("")
    s = panel.get("summary", {})
    lines.append("## 结论")
    lines.append("")
    lines.append("**%s** —— %s" % (panel["panel_verdict"], panel["verdict_reason"]))
    lines.append("")
    if s.get("spread") is not None:
        lines.append("分数离散度：%d（各审稿人总分 %s）" % (
            s["spread"], ", ".join("%s=%s" % (k, v) for k, v in s["totals"].items())))
        lines.append("")
    lines.append("> 本结论**不是**录用概率，也不保证录用。它只说明稿件在模拟评审下处于什么状态。")
    lines.append("")
    lines.append("## 审稿输入覆盖")
    lines.append("")
    lines.append("| 输入 | 状态 | 证据定位 | 未完整审阅原因 |")
    lines.append("|---|---|---|---|")
    labels = dict(REVIEW_INPUTS)
    coverage, _ = review_coverage_state(panel)
    for item in coverage:
        lines.append("| %s（`%s`） | %s | %s | %s |" % (
            labels[item["input_id"]], item["input_id"], item["status"],
            item["evidence_locator"].replace("|", "/") or "—",
            item["reason"].replace("|", "/") or "—"))
    lines.append("")
    lines.append("> 文件存在不等于已经审阅。任何 PARTIAL、MISSING 或 SKIPPED 项都会阻止就绪结论。")
    lines.append("")
    lines.append("## 逐条回应覆盖")
    lines.append("")
    lines.append("| 意见 ID | 处置 | 回应 | 变更、证据定位或保留理由 |")
    lines.append("|---|---|---|---|")
    actionable, _, response_gaps = response_coverage_state(panel)
    if not actionable:
        lines.append("| — | — | 当前没有需要回应的非正向意见 | — |")
    else:
        for finding_id in actionable:
            finding = _finding_by_id(panel, finding_id)
            response = finding.get("response") or {}
            locator = (response.get("change_locator") or response.get("evidence_locator")
                       or response.get("reason") or "—")
            text = response.get("response") or "**MISSING**"
            lines.append("| %s | %s | %s | %s |" % (
                finding_id,
                str(response.get("disposition", "—")).replace("|", "/"),
                str(text).replace("|", "/"),
                str(locator).replace("|", "/"),
            ))
    lines.append("")
    if response_gaps:
        lines.append("> 未覆盖意见：%s。逐条覆盖只检查结构与定位，不判断回应是否充分。" %
                     ", ".join(item["finding_id"] for item in response_gaps))
    else:
        lines.append("> 逐条覆盖完整；这不表示回应充分，也不证明改稿或反驳在科学上成立。")
    lines.append("")
    lines.append("## 各审稿人")
    lines.append("")
    for r in panel["reviewers"]:
        lines.append("### %s（%s）" % (r["role"], r["id"]))
        lines.append("")
        lines.append("- 关注点：%s" % r["focus"])
        lines.append("- 要回答的问题：%s" % r["asks"])
        if r["total"] is None:
            lines.append("- 评分：**未评分**")
        else:
            lines.append("- 总分：**%s / %d**（%s）" % (r["total"], PANEL_TOTAL, r["verdict"]))
            for dim, label in DIMENSIONS:
                lines.append("  - %s：%s" % (label, r["scores"][dim]))
        if r.get("note"):
            lines.append("- 备注：%s" % r["note"])
        lines.append("")
        if r["findings"]:
            lines.append("| ID | 严重度 | 类型 | 位置 | 意见 | 需作者补数据 | 状态 |")
            lines.append("|---|---|---|---|---|---|---|")
            for f in r["findings"]:
                lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                    f["id"], f["severity"], f["kind"], f["location"].replace("|", "/"),
                    f["comment"].replace("|", "/"),
                    "是" if f["requires_author_data"] else "否", f["status"]))
            lines.append("")
        else:
            lines.append("_未提出问题。注意：审稿人不提科学问题会被判为覆盖不足，而不是干净通过。_")
            lines.append("")
    lines.append("## 不允许做的事")
    lines.append("")
    lines.append("- 不为满足审稿人而编造新结果、新样本量、新显著性检验或新伦理审批。")
    lines.append("- 不把模拟意见说成真实同行评审意见。")
    lines.append("- 不给出录用概率。")
    return "\n".join(lines) + "\n"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_scores(raw):
    parts = [p.strip() for p in str(raw).split(",") if p.strip()]
    if len(parts) != len(DIMENSIONS):
        raise ValueError("expected %d comma-separated scores, got %d" % (len(DIMENSIONS), len(parts)))
    return {d: int(v) for (d, _), v in zip(DIMENSIONS, parts)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Simulated reviewer panel (3-5 independent reviewers)")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("panel", help="create a panel worksheet")
    p.add_argument("manuscript")
    p.add_argument("--out", required=True)
    p.add_argument("--reviewers", default="", help="comma-separated ids; default 4")
    p.add_argument("--context", default="")
    p.add_argument("--report", default="", help="optional path for a Markdown report")

    r = sub.add_parser("score", help="record one reviewer's seven dimension scores")
    r.add_argument("panel")
    r.add_argument("reviewer")
    r.add_argument("--scores", required=True, help="seven comma-separated integers, e.g. 4,4,5,3,4,4,4")
    r.add_argument("--note", default="")

    f = sub.add_parser("finding", help="record one finding")
    f.add_argument("panel")
    f.add_argument("reviewer")
    f.add_argument("--severity", required=True, choices=SEVERITIES)
    f.add_argument("--kind", default="science", choices=FINDING_KINDS)
    f.add_argument("--location", required=True)
    f.add_argument("--comment", required=True)
    f.add_argument("--requires-author-data", action="store_true")

    c = sub.add_parser("coverage", help="record whether one required upstream input was reviewed")
    c.add_argument("panel")
    c.add_argument("input_id", choices=REQUIRED_REVIEW_INPUTS)
    c.add_argument("--status", required=True, choices=REVIEW_COVERAGE_STATUSES)
    c.add_argument("--evidence-locator", default="")
    c.add_argument("--reason", default="")

    a = sub.add_parser("response", help="record one point-by-point response to a finding")
    a.add_argument("panel")
    a.add_argument("finding_id")
    a.add_argument("--disposition", required=True, choices=RESPONSE_DISPOSITIONS)
    a.add_argument("--response", dest="response_text", required=True)
    a.add_argument("--change-locator", default="")
    a.add_argument("--evidence-locator", default="")
    a.add_argument("--reason", default="")
    a.add_argument("--author-approved", action="store_true")

    v = sub.add_parser("verdict", help="compute the panel verdict")
    v.add_argument("panel")
    v.add_argument("--report", default="")

    args = ap.parse_args(argv)
    try:
        if args.command == "panel":
            ids = [x.strip() for x in args.reviewers.split(",") if x.strip()] or None
            panel = build_panel(args.manuscript, ids, args.context)
            panel = compute_verdict(panel)
            write_json(args.out, panel)
            print("panel: %s (%d reviewers: %s)"
                  % (args.out, len(panel["reviewers"]),
                     ", ".join(r["id"] for r in panel["reviewers"])))
            print("verdict: %s" % panel["panel_verdict"])
            if args.report:
                Path(args.report).parent.mkdir(parents=True, exist_ok=True)
                Path(args.report).write_text(render_report(panel), encoding="utf-8")
                print("report: %s" % args.report)
            return 0

        if args.command == "score":
            panel = read_json(args.panel)
            reviewer = score_reviewer(panel, args.reviewer, parse_scores(args.scores), args.note)
            panel = compute_verdict(panel)
            write_json(args.panel, panel)
            print("%s scored %s/%d" % (args.reviewer, reviewer["total"], PANEL_TOTAL))
            print("panel verdict: %s" % panel["panel_verdict"])
            return 0

        if args.command == "finding":
            panel = read_json(args.panel)
            finding = add_finding(panel, args.reviewer, args.severity, args.location,
                                  args.comment, args.kind, args.requires_author_data)
            write_json(args.panel, panel)
            print("recorded %s (%s)" % (finding["id"], finding["severity"]))
            return 0

        if args.command == "coverage":
            panel = read_json(args.panel)
            entry = record_coverage(panel, args.input_id, args.status,
                                    args.evidence_locator, args.reason)
            panel = compute_verdict(panel)
            write_json(args.panel, panel)
            print("coverage %s=%s" % (entry["input_id"], entry["status"]))
            print("panel verdict: %s" % panel["panel_verdict"])
            return 0

        if args.command == "response":
            panel = read_json(args.panel)
            response = record_response(
                panel, args.finding_id, args.disposition, args.response_text,
                args.change_locator, args.evidence_locator, args.reason,
                args.author_approved,
            )
            panel = compute_verdict(panel)
            write_json(args.panel, panel)
            print("response %s=%s" % (args.finding_id, response["disposition"]))
            print("panel verdict: %s" % panel["panel_verdict"])
            return 0

        panel = read_json(args.panel)
        panel = compute_verdict(panel)
        write_json(args.panel, panel)
        if args.report:
            Path(args.report).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report).write_text(render_report(panel), encoding="utf-8")
        print("%s :: %s" % (panel["panel_verdict"], panel["verdict_reason"]))
        print(json.dumps(panel["summary"], indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
