#!/usr/bin/env python3
"""
图件护栏：把 modules/figures.md 里能机器判定的规则变成硬检查。

用法：
  python scripts/figures.py palettes                 打印内置无障碍色板十六进制值
  python scripts/figures.py init <workspace>         生成 figures/manifest.json 骨架
  python scripts/figures.py check <workspace>        校验全部图件，阻断项非零退出

它检查什么（见 modules/figures.md）：
  - 三类图齐全：roadmap 线路图 / schematic 示意图 / data 数据图（示意图可显式声明不需要+理由）
  - 数据图只用无障碍色板，禁止 jet/rainbow；多系列必须有颜色之外的冗余通道
  - 系列数 >6 判为应拆图；示意图必须标 conceptual + “概念示意/Conceptual”
  - source_data / script / outputs 文件真实存在，且至少一个矢量输出
  - contract 2.0 锁定已声明依赖的 SHA-256、最终版面尺寸与交付可编辑性
  - visual_review 必须给出 reviewed_by + reviewed_at；脚本不替代人眼，只校验审查证据
  - 数据图必须形成 source_data(结果目录) -> script -> outputs 的可复现链

它不检查什么（明确边界）：
  - 不能判断图好不好看、坐标轴标得对不对、数字与正文是否一致——这些必须人眼过。
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

# ---------- 无障碍色板（科学公认；Okabe-Ito 2008；Paul Tol colour schemes） ----------
PALETTES = {
    "okabe-ito": ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442",
                  "#0072B2", "#D55E00", "#CC79A7"],
    "tol-bright": ["#4477AA", "#66CCEE", "#228833", "#CCBB44", "#EE6677",
                   "#AA3377", "#BBBBBB"],
    "tol-muted": ["#CC6677", "#332288", "#DDCC77", "#117733", "#88CCEE",
                  "#882255", "#44AA99", "#999933", "#AA4499"],
    "tol-high-contrast": ["#004488", "#DDAA33", "#BB5566"],
    # 感知均匀的连续/顺序色板（matplotlib 内置，这里只登记名字）
    "viridis": "<sequential, matplotlib>",
    "cividis": "<sequential, matplotlib, color-vision-deficiency friendly>",
    "magma": "<sequential, matplotlib>",
    "plasma": "<sequential, matplotlib>",
    "inferno": "<sequential, matplotlib>",
}
FORBIDDEN_PALETTES = {"jet", "rainbow", "hsv", "gist_rainbow", "gist_ncar", "nipy_spectral"}
REDUNDANT_CHANNELS = {"marker shape", "line style", "hatching", "direct label",
                      "marker", "linestyle", "shape"}
VECTOR_SUFFIX = {".pdf", ".svg", ".eps"}
MAX_SERIES = 6
CONCEPT_WORDS = ("概念示意", "概念图", "示意", "conceptual", "schematic", "illustration")
EDITABILITY_CLASSES = {"live-vector-text", "outlined-text", "embedded-raster", "mixed"}


def configure_console_output():
    """Keep dynamic manifest text printable on legacy Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (OSError, ValueError):
            pass


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_at_least(value, major, minor):
    try:
        parts = tuple(int(part) for part in str(value).split("."))
    except (TypeError, ValueError):
        return False
    return (parts + (0, 0))[:2] >= (major, minor)


def _positive_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _check_declared_hash(ws, rel, expected, label, fid, errors):
    if not isinstance(rel, str) or not rel.strip():
        errors.append(f"[{fid}] {label} 路径为空")
        return
    try:
        path = (ws / rel).resolve()
        safe = not Path(rel).is_absolute() and path.is_relative_to(ws.resolve())
    except (ValueError, OSError):
        safe = False
        path = None
    if not safe:
        errors.append(f"[{fid}] {label} 路径越出工作区：{rel!r}")
        return
    if path is None or not path.is_file():
        errors.append(f"[{fid}] {label} 文件不存在：{rel!r}")
        return
    if not isinstance(expected, str) or len(expected) != 64:
        errors.append(f"[{fid}] 缺有效的 {label} SHA-256：{rel!r}")
        return
    if sha256_file(path).lower() != expected.lower():
        errors.append(f"[{fid}] {label} SHA-256 不匹配：{rel!r}；图件依赖已过期")


def cmd_palettes(_):
    print("无障碍分类色板（按顺序取前 k 个，不要跳取；≤8 类首选 okabe-ito）\n")
    for name in ("okabe-ito", "tol-bright", "tol-muted", "tol-high-contrast"):
        colors = PALETTES[name]
        print(f"{name}（{len(colors)} 色）")
        for i, c in enumerate(colors):
            print(f"  {i+1}. {c}")
        print()
    print("顺序/连续数据用：viridis / cividis（色盲友好）/ magma / plasma / inferno")
    print("禁止：jet / rainbow / hsv / gist_rainbow —— 感知不均匀且对色盲不友好")
    print("\n多系列（>1）必须再加一个颜色之外的通道：marker shape / line style / "
          "hatching / direct label。")


def cmd_init(ws):
    target = ws / "figures" / "manifest.json"
    if target.exists():
        print(f"已存在 {target}，不覆盖。")
        return
    skeleton = {
        "contract_version": "2.0",
        "_说明": "每张图一条；type∈roadmap/schematic/data；outputs 至少一个矢量(pdf/svg/eps)；"
                "锁定源数据/脚本/输出 SHA-256，并在最终版面尺寸复核；脚本只查证据不替你看。",
        "schematic_not_needed_reason": None,
        "figures": [
            {"id": "fig-roadmap", "type": "roadmap", "title": "", "version": "planned",
             "source_data": [], "script": "", "axes": {}, "colors": {},
             "caption": "", "conceptual": False, "outputs": [],
             "provenance": {"source_data": {}, "script": None, "outputs": {}},
             "final_size": {"slot_class": None, "width_mm": None, "height_mm": None},
             "editability": {"class": None, "notes": None},
             "visual_review": {"status": "pending", "reviewed_by": None,
                               "reviewed_at": None, "at_width_mm": None,
                               "at_height_mm": None, "container": None,
                               "editability_checked": False, "notes": None}, "notes": ""},
            {"id": "fig-schematic", "type": "schematic", "title": "",
             "source_data": [], "script": "", "axes": {}, "colors": {},
             "caption": "概念示意（Conceptual illustration），非观测结果。",
             "conceptual": True, "outputs": [],
             "provenance": {"source_data": {}, "script": None, "outputs": {}},
             "final_size": {"slot_class": None, "width_mm": None, "height_mm": None},
             "editability": {"class": None, "notes": None},
             "visual_review": {"status": "pending", "reviewed_by": None,
                               "reviewed_at": None, "at_width_mm": None,
                               "at_height_mm": None, "container": None,
                               "editability_checked": False, "notes": None}, "notes": ""},
            {"id": "fig1", "type": "data", "title": "",
             "source_data": ["analysis/results/<your-result>.csv"],
             "script": "figures/plot_fig1.py",
             "axes": {"x": "<量 (单位)>", "y": "<量 (单位)>"}, "colorbar": None,
             "masks": "缺测如何处理",
             "colors": {"palette": "okabe-ito", "n_series": 2,
                        "redundant_encoding": "marker shape"},
             "uncertainty": {"type": "SD|SE|CI|none", "sampling_unit": "<per event/orbit/...>"},
             "caption": "", "conceptual": False,
             "outputs": ["figures/fig1.pdf", "figures/fig1.png"],
             "provenance": {"source_data": {}, "script": None, "outputs": {}},
             "final_size": {"slot_class": None, "width_mm": None, "height_mm": None},
             "editability": {"class": None, "notes": None},
             "visual_review": {"status": "pending", "reviewed_by": None,
                               "reviewed_at": None, "at_width_mm": None,
                               "at_height_mm": None, "container": None,
                               "editability_checked": False, "notes": None}, "notes": ""},
        ],
    }
    save(target, skeleton)
    print(f"已生成骨架：{target}")
    print("填好后运行 python scripts/figures.py check <workspace>")


def _exists(ws, rel):
    if not rel:
        return False
    try:
        p = (ws / rel).resolve()
        return p.is_relative_to(ws.resolve()) and p.exists()
    except (ValueError, OSError):
        return False


def check_one(ws, fig, require_release_provenance=False):
    """返回 (errors 阻断, warnings 建议)。"""
    errors, warnings = [], []
    fid = fig.get("id", "<无id>")
    ftype = fig.get("type")
    if ftype not in ("roadmap", "schematic", "data"):
        errors.append(f"[{fid}] type 必须是 roadmap/schematic/data，当前 {ftype!r}")
        return errors, warnings
    if not fig.get("caption"):
        errors.append(f"[{fid}] 缺 caption（图注必须自足）")

    outputs = fig.get("outputs") or []
    if not outputs:
        errors.append(f"[{fid}] 缺 outputs")
    else:
        missing = [o for o in outputs if not _exists(ws, o)]
        if missing:
            errors.append(f"[{fid}] 输出文件不存在：{missing}")
        if not any(Path(str(o)).suffix.lower() in VECTOR_SUFFIX for o in outputs):
            errors.append(f"[{fid}] 至少需要一个矢量输出 pdf/svg/eps，当前 {outputs}")

    # 人眼视觉审查证据
    vr = fig.get("visual_review") or {}
    if not isinstance(vr, dict):
        errors.append(f"[{fid}] visual_review 应为对象（status/reviewed_by/reviewed_at）")
    else:
        status = vr.get("status")
        if status == "passed":
            if not vr.get("reviewed_by") or not vr.get("reviewed_at"):
                errors.append(f"[{fid}] visual_review=passed 但缺 reviewed_by/reviewed_at"
                              "（不许凭文件存在填 passed）")
        elif status != "pending":
            warnings.append(f"[{fid}] visual_review.status 建议为 pending/passed，当前 {status!r}")
        if status != "passed":
            errors.append(f"[{fid}] 尚未完成人眼视觉审查（visual_review.status != passed）")

    if ftype == "roadmap":
        if fig.get("version") not in ("planned", "actual"):
            warnings.append(f"[{fid}] roadmap 建议标 version=planned/actual")
        # 主路径/替代路径属于人眼判断，脚本只要求有 source_data 或 script 之一说明可复现
        if not (fig.get("source_data") or fig.get("script")):
            warnings.append(f"[{fid}] roadmap 建议记录数据来源或绘制脚本，便于计划版/实际版比对")

    if ftype == "schematic":
        text = f"{fig.get('caption','')} {fig.get('notes','')}".lower()
        if not fig.get("conceptual") or not any(w.lower() in text for w in CONCEPT_WORDS):
            errors.append(f"[{fid}] 示意图必须 conceptual=true 且图注/notes 标明“概念示意/Conceptual”，"
                          "不得冒充观测结果")

    if ftype == "data":
        # 可复现链：source_data -> script -> outputs
        srcs = fig.get("source_data") or []
        if not srcs:
            errors.append(f"[{fid}] 数据图缺 source_data（不准用生成式工具造数据图）")
        else:
            miss = [s for s in srcs if not _exists(ws, s)]
            if miss:
                errors.append(f"[{fid}] source_data 不存在：{miss}")
            outside = [s for s in srcs if not str(s).startswith(("analysis/results", "inputs",
                                                                 "evidence", "private-corpus"))]
            if outside:
                warnings.append(f"[{fid}] source_data 不在结果/输入登记目录下：{outside}"
                                "（确认不是手工改过数字的文件）")
        if not fig.get("script") or not _exists(ws, fig["script"]):
            errors.append(f"[{fid}] 数据图缺可运行的绘图脚本 script（文件需真实存在）")

        colors = fig.get("colors") or {}
        pal = (colors.get("palette") or "").strip().lower()
        if pal in FORBIDDEN_PALETTES:
            errors.append(f"[{fid}] 禁用色板 {pal}（感知不均匀/色盲不友好），换 okabe-ito/tol/viridis")
        elif pal and pal not in PALETTES:
            warnings.append(f"[{fid}] 色板 {pal!r} 不在登记的无障碍名单内，需自行证明色盲可辨")
        elif not pal:
            errors.append(f"[{fid}] 数据图未指定 colors.palette")

        n_series = colors.get("n_series")
        if not isinstance(n_series, int) or n_series < 1:
            errors.append(f"[{fid}] colors.n_series 应为 ≥1 的整数")
        else:
            if n_series > MAX_SERIES:
                errors.append(f"[{fid}] {n_series} 个系列 > {MAX_SERIES}，应拆图，不要继续加颜色")
            if n_series > 1:
                ch = (colors.get("redundant_encoding") or "").strip().lower()
                if ch not in REDUNDANT_CHANNELS:
                    errors.append(f"[{fid}] {n_series} 个系列只靠颜色区分，必须加冗余通道"
                                  "（marker shape/line style/hatching/direct label）")

        unc = fig.get("uncertainty") or {}
        if not unc.get("type") or not unc.get("sampling_unit"):
            errors.append(f"[{fid}] 数据图缺 uncertainty.type/sampling_unit"
                          "（没有误差也要显式写 none 并说明）")

    if require_release_provenance:
        sources = fig.get("source_data") or []
        script = fig.get("script")
        provenance = fig.get("provenance") or {}
        source_hashes = provenance.get("source_data") if isinstance(provenance, dict) else {}
        output_hashes = provenance.get("outputs") if isinstance(provenance, dict) else {}
        source_hashes = source_hashes if isinstance(source_hashes, dict) else {}
        output_hashes = output_hashes if isinstance(output_hashes, dict) else {}
        for rel in sources:
            _check_declared_hash(ws, rel, source_hashes.get(rel), "source_data", fid, errors)
        if isinstance(script, str) and script.strip():
            script_hash = provenance.get("script") if isinstance(provenance, dict) else None
            _check_declared_hash(ws, script, script_hash, "script", fid, errors)
        elif not sources:
            errors.append(f"[{fid}] 发布图件至少需要 source_data 或生成脚本 script")
        for rel in outputs:
            _check_declared_hash(ws, rel, output_hashes.get(rel), "output", fid, errors)

        final_size = fig.get("final_size") or {}
        width = final_size.get("width_mm") if isinstance(final_size, dict) else None
        height = final_size.get("height_mm") if isinstance(final_size, dict) else None
        if not isinstance(final_size, dict) or not str(final_size.get("slot_class") or "").strip():
            errors.append(f"[{fid}] 缺 final_size.slot_class（真实期刊/文稿槽位）")
        if not _positive_number(width) or not _positive_number(height):
            errors.append(f"[{fid}] final_size.width_mm/height_mm 必须为正数")

        editability = fig.get("editability") or {}
        editability_class = editability.get("class") if isinstance(editability, dict) else None
        if editability_class not in EDITABILITY_CLASSES:
            errors.append(
                f"[{fid}] editability.class 必须是 {sorted(EDITABILITY_CLASSES)} 之一"
            )

        reviewed_width = vr.get("at_width_mm") if isinstance(vr, dict) else None
        reviewed_height = vr.get("at_height_mm") if isinstance(vr, dict) else None
        if _positive_number(width) and (
            not _positive_number(reviewed_width)
            or abs(float(reviewed_width) - float(width)) > 0.1
        ):
            errors.append(f"[{fid}] visual_review 未在最终宽度完成")
        if _positive_number(height) and (
            not _positive_number(reviewed_height)
            or abs(float(reviewed_height) - float(height)) > 0.1
        ):
            errors.append(f"[{fid}] visual_review 未在最终高度完成")
        if not isinstance(vr, dict) or not str(vr.get("container") or "").strip():
            errors.append(f"[{fid}] visual_review 缺最终容器 container")
        if not isinstance(vr, dict) or vr.get("editability_checked") is not True:
            errors.append(f"[{fid}] visual_review 必须确认 editability_checked=true")

    return errors, warnings


def cmd_check(ws):
    manifest = load(ws / "figures" / "manifest.json")
    if not manifest:
        print("[ERROR] 找不到 figures/manifest.json，先运行 figures.py init。")
        sys.exit(2)
    figs = manifest.get("figures") or []
    if not isinstance(figs, list) or not figs:
        print("[ERROR] manifest 里没有任何图。")
        sys.exit(1)

    all_errors, all_warnings = [], []
    contract_version = manifest.get("contract_version")
    require_release_provenance = _schema_at_least(contract_version, 2, 0)
    if contract_version and not str(contract_version).replace(".", "", 1).isdigit():
        all_errors.append(f"manifest.contract_version 无效：{contract_version!r}")
    elif not require_release_provenance:
        all_warnings.append(
            "旧图件清单未启用 contract_version 2.0 的依赖哈希、最终尺寸和可编辑性发布锁"
        )
    for fig in figs:
        e, w = check_one(ws, fig, require_release_provenance=require_release_provenance)
        all_errors += e
        all_warnings += w

    types = {f.get("type") for f in figs if isinstance(f, dict)}
    if "roadmap" not in types:
        all_errors.append("缺科研线路图 roadmap（P1 草图、P4 定稿）")
    if "data" not in types:
        all_errors.append("缺数据图 data")
    if "schematic" not in types:
        reason = manifest.get("schematic_not_needed_reason")
        if not reason or not str(reason).strip():
            all_errors.append("缺原理示意图 schematic；若确不需要，"
                              "在 manifest.schematic_not_needed_reason 写明理由")
        else:
            all_warnings.append(f"已声明不需要示意图：{reason}")

    print("=" * 60)
    print("[FIGURES] 图件护栏检查（scripts/figures.py）")
    print("=" * 60)
    if all_warnings:
        print("\n[WARN] 建议（不阻断）：")
        for w in all_warnings:
            print(f"   - {w}")
    if all_errors:
        print("\n[ERROR] 阻断项（必须处理，人眼审查无法由脚本替代）：")
        for e in all_errors:
            print(f"   [FAIL] {e}")
        print(f"\n共 {len(all_errors)} 项阻断、{len(all_warnings)} 项建议。")
        sys.exit(1)
    print(f"\n[OK] 机器可查项全部通过（{len(figs)} 张图），{len(all_warnings)} 项建议。")
    print("提醒：脚本只验证文件链与审查证据，图是否科学、美观、数字一致，仍需人眼核对。")


def main():
    configure_console_output()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("palettes")
    si = sub.add_parser("init"); si.add_argument("workspace")
    sc = sub.add_parser("check"); sc.add_argument("workspace")
    a = ap.parse_args()
    if a.cmd == "palettes":
        cmd_palettes(None)
    elif a.cmd == "init":
        cmd_init(Path(a.workspace))
    else:
        cmd_check(Path(a.workspace))


if __name__ == "__main__":
    main()
