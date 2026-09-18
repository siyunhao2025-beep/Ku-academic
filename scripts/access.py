#!/usr/bin/env python3
"""
引用分级与合法全文兜底。

解决的问题：不是每句话都需要读到全文。
  - 背景/书目句，有准确元数据就够；
  - 方法/存在性归因，至少要读到摘要；
  - 精确数字、定量对比，必须读到全文并定位到页/图/表；
  - 机制/因果断言，必须读到全文并核对原文措辞强度。
“拿不到全文”应当只精准卡死定量句与机制句，而不是把背景句、方法句也一起卡死。

本脚本：
  1) 按句子强度 sentence_tier 给出最低访问级别 access_level，逐条校验引用；
  2) 对需要全文的文献，走 Unpaywall 找合法开放获取版本（出版社/机构库/作者自存档），
     绝不使用盗版来源；无网络/无邮箱时明确报错并标“待确认”，不伪造可访问性。

用法：
  python scripts/access.py tiers
  python scripts/access.py resolve <doi> --email you@example.com
  python scripts/access.py check <workspace>
读取 audit/citation-provenance.json（兼容 evidence.json），写 audit/access-report.json。
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import research
except Exception:  # pragma: no cover
    research = None

# 访问深度序数：越高代表读到的内容越多
ACCESS_RANK = {"metadata_only": 0, "abstract_only": 1, "full_text": 2, "project_result": 3}

# 句子强度 -> 最低访问级别 + 是否必须定位页/图/表 + 中文说明
TIERS = {
    "background": {"min_access": "metadata_only", "needs_locator": False,
                   "label": "背景/书目句（领域概述，不主张具体结论）"},
    "method": {"min_access": "abstract_only", "needs_locator": False,
               "label": "方法/存在性归因（谁用了什么方法，不引具体数字与机制）"},
    "quantitative": {"min_access": "full_text", "needs_locator": True,
                     "label": "定量句（精确数字、幅度、比例、阈值、定量对比）"},
    "causal": {"min_access": "full_text", "needs_locator": True,
               "label": "机制/因果句（导致、由于、机制是、驱动）"},
}

# 只允许这些合法全文来源类别；脚本永远不会推荐盗版站
LEGAL_HOST_TYPES = {"publisher", "repository", "unpaywall"}
OA_STATUS_MEANING = {
    "gold": "期刊开放获取（出版社，通常 CC 许可）",
    "green": "作者自存/机构库版本（注意版本：accepted manuscript 与正式版可能有差异）",
    "hybrid": "订阅期刊中的单篇开放获取",
    "bronze": "出版社页面免费可读但无明确开放许可（可读，引用仍需核对版本）",
    "closed": "无合法免费全文",
}


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def normalise_doi(value):
    if research is not None:
        return research.doi(value)
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", str(value or ""), flags=re.I)
    return text.strip().lower()


def evaluate_citation(cit):
    """对一条引用记录做分级判定，返回 dict（errors/warnings/tier/access/needs_fulltext）。"""
    errors, warnings = [], []
    cid = cit.get("citation_id") or cit.get("id") or "<无编号>"

    tier = (cit.get("sentence_tier") or "").strip().lower()
    if not tier:
        # 未标强度 -> 按最严的 causal 处理，宁严勿松，并提醒补标
        tier = "causal"
        warnings.append(f"[{cid}] 未标 sentence_tier，按最严的 causal（机制句）处理，请补标")
    elif tier not in TIERS:
        errors.append(f"[{cid}] sentence_tier={tier!r} 非法，应为 "
                      f"background/method/quantitative/causal")
        tier = "causal"

    access = (cit.get("access_level") or cit.get("evidence_level") or "").strip().lower()
    if not access:
        access = "metadata_only"
        warnings.append(f"[{cid}] 未标 access_level，按最低 metadata_only 处理")
    elif access not in ACCESS_RANK:
        errors.append(f"[{cid}] access_level={access!r} 非法")

    locator = cit.get("locator") or ""
    if not locator and isinstance(cit.get("available_evidence"), str):
        # 允许从 available_evidence 文本里识别 p./Fig./Table 定位
        if re.search(r"(p{1,2}\.?\s*\d+|fig\.?\s*\d+|table\s*\d+|页|图\s*\d+|表\s*\d+)",
                     cit["available_evidence"], re.I):
            locator = cit["available_evidence"]

    spec = TIERS[tier]
    needs_fulltext = spec["min_access"] == "full_text"
    enough = ACCESS_RANK.get(access, 0) >= ACCESS_RANK[spec["min_access"]]

    if not enough:
        if needs_fulltext:
            errors.append(f"[{cid}] {spec['label']}需要全文（≥{spec['min_access']}），"
                          f"当前仅 {access}：必须获取全文并定位，或把句子显式降级为背景/方法句")
        else:
            errors.append(f"[{cid}] {spec['label']}至少需要 {spec['min_access']}，当前 {access}")

    if needs_fulltext and enough and spec["needs_locator"] and not locator:
        errors.append(f"[{cid}] 即使读到全文，{tier} 句也必须定位到具体页/图/表（locator），"
                      "不能用‘全文已读’含糊带过")

    return {"citation_id": cid, "tier": tier, "access": access, "locator": locator,
            "needs_fulltext": needs_fulltext and not enough,
            "doi": normalise_doi(cit.get("reference_key") or cit.get("doi") or ""),
            "errors": errors, "warnings": warnings}


def _http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchMother/0.5",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read(5_000_000))


def resolve_oa(doi_value, email, fetch=_http_get_json):
    """走 Unpaywall 查合法开放获取位置。无网络/无邮箱抛异常，绝不伪造。"""
    doi_value = normalise_doi(doi_value)
    if not doi_value:
        raise ValueError("需要一个 DOI")
    if not email or not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(email)):
        raise ValueError("Unpaywall 要求提供真实联系邮箱（--email），用于其礼貌 API 池")
    url = f"https://api.unpaywall.org/v2/{doi_value}?email={email}"
    try:
        data = fetch(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"doi": doi_value, "is_oa": False, "oa_status": "not_found",
                    "message": "Unpaywall 无此 DOI 记录"}
        raise RuntimeError(f"Unpaywall HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"无法访问 Unpaywall（网络不可达）：{exc}；请联网重试，"
                           "在此之前该文献按‘待确认’处理，不得假设可获取全文") from exc

    result = {"doi": doi_value, "is_oa": bool(data.get("is_oa")),
              "oa_status": data.get("oa_status", "unknown"),
              "oa_status_meaning": OA_STATUS_MEANING.get(data.get("oa_status"), ""),
              "locations": []}
    best = data.get("best_oa_location") or {}
    locations = data.get("oa_locations") or ([best] if best else [])
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        host_type = loc.get("host_type", "")
        entry = {"host_type": host_type,
                 "pdf_url": loc.get("url_for_pdf"), "landing_url": loc.get("url"),
                 "license": loc.get("license"), "version": loc.get("version"),
                 "legal": host_type in LEGAL_HOST_TYPES}
        if entry["pdf_url"] or entry["landing_url"]:
            result["locations"].append(entry)
    result["best_pdf"] = best.get("url_for_pdf") if best else None
    result["best_landing"] = best.get("url") if best else None
    return result


def cmd_tiers(_):
    print("句子强度分级与最低访问级别（达不到就精准阻断该句，不牵连背景句）：\n")
    for key, spec in TIERS.items():
        loc = "，并定位页/图/表" if spec["needs_locator"] else ""
        print(f"  {key:<13} 最低 {spec['min_access']:<14}{loc}")
        print(f"               {spec['label']}")
    print("\n拿不到全文时：定量句/机制句阻断；可显式把句子降级为背景/方法句并改写，")
    print("不得静默降级。合法全文用 access.py resolve <doi> --email <你邮箱> 走 Unpaywall。")


def cmd_resolve(doi_value, email):
    try:
        r = resolve_oa(doi_value, email)
    except (ValueError, RuntimeError) as exc:
        print(f"⛔ {exc}")
        sys.exit(2)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if not r["is_oa"]:
        print("\n无合法免费全文。该文献的定量/机制句按‘待确认’处理：通过图书馆/出版社获取，"
              "或把论断降级；不要使用盗版来源。")


def collect_citations(ws):
    """优先 citation-provenance.json，其次 evidence.json。"""
    prov = load_json(ws / "audit" / "citation-provenance.json")
    if isinstance(prov, dict) and isinstance(prov.get("citations"), list):
        return prov["citations"], "audit/citation-provenance.json"
    ev = load_json(ws / "evidence.json")
    rows = ev.get("evidence", ev) if isinstance(ev, dict) else ev
    if isinstance(rows, list):
        return rows, "evidence.json"
    return [], None


def cmd_check(ws):
    citations, source = collect_citations(ws)
    if not source:
        print("⛔ 找不到 audit/citation-provenance.json 或 evidence.json。")
        sys.exit(2)

    results = [evaluate_citation(c) for c in citations]
    blockers = [r for r in results if r["errors"]]
    must_get = [r for r in results if r["needs_fulltext"]]
    oa_candidates = [r for r in must_get if r["doi"]]

    report = {"source": source, "checked": len(results),
              "blockers": [{"citation_id": r["citation_id"], "errors": r["errors"]}
                           for r in blockers],
              "warnings": [{"citation_id": r["citation_id"], "warnings": r["warnings"]}
                           for r in results if r["warnings"]],
              "fulltext_needed_dois": [{"citation_id": r["citation_id"], "doi": r["doi"],
                                        "tier": r["tier"]} for r in oa_candidates]}
    out = ws / "audit" / "access-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=" * 64)
    print("🔎 引用分级与访问级别检查")
    print("=" * 64)
    print(f"来源：{source}，共 {len(results)} 条\n")

    if must_get:
        print("📄 必须读到全文才能写的句子（定量/机制）：")
        for r in must_get:
            doi_hint = f"（DOI {r['doi']}）" if r["doi"] else "（无 DOI，需人工获取）"
            print(f"   · [{r['citation_id']}] {r['tier']} 句 {doi_hint}")
            print(f"       合法找全文：python scripts/access.py resolve {r['doi'] or '<doi>'} "
                  f"--email <你邮箱>")
        print("       找不到全文就把句子显式降级为背景/方法句并改写，或标‘待确认’，不得硬写。\n")

    if blockers:
        print("⛔ 阻断项：")
        for r in blockers:
            for e in r["errors"]:
                print(f"   ❌ {e}")
    warn_rows = [r for r in results if r["warnings"]]
    if warn_rows:
        print("\n⚠️ 提醒：")
        for r in warn_rows:
            for w in r["warnings"]:
                print(f"   · {w}")

    if not blockers:
        print("✅ 各句访问级别满足其句子强度要求。")
    print(f"\n报告：{out}")
    if blockers:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tiers")
    sr = sub.add_parser("resolve"); sr.add_argument("doi"); sr.add_argument("--email", required=True)
    sc = sub.add_parser("check"); sc.add_argument("workspace")
    a = ap.parse_args()
    if a.cmd == "tiers":
        cmd_tiers(None)
    elif a.cmd == "resolve":
        cmd_resolve(a.doi, a.email)
    else:
        cmd_check(Path(a.workspace))


if __name__ == "__main__":
    main()
