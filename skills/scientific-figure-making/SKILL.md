---
name: scientific-figure-making
description: >-
  Covers publication-ready matplotlib figures for academic papers, slides, and
  reports—bars, trends, scatter, heatmaps, and multi-panel layouts—with this
  repository’s house style, print/vector export conventions, and parity with
  figures4papers demos. Use when the user is finalizing or creating such figures
  in matplotlib, including requests for figures4papers style. Inside
  Ku-academic, always apply the local truth, provenance, accessibility, axis,
  and license gates before this skill's house-style suggestions. Do not use for
  interactive dashboards or web viz (Plotly, Altair, Bokeh), exploratory-only
  plots without a publication target, dominant 3D or geographic mapping, or
  Illustrator/Figma-first infographic workflows.
---

# Scientific figure making

## Mandatory Ku-academic policy gate

This is an independently triggerable third-party Skill installed from the locked
figures4papers revision recorded in [SOURCE.md](SOURCE.md). Its styling guidance
is subordinate to Ku-academic's scientific rules. Before opening a reference or
writing plotting code, read:

1. [the figure contract](../../modules/figures.md),
2. [the local figures4papers profile](../../modules/figures4papers-profile.md), and
3. [the analysis-to-figure contract](../../modules/analysis-methods-figures.md).

If a reference conflicts with those files, follow the local files. In particular:

- Use real, registered inputs and preserve
  `source_data -> plot_script -> outputs -> caption_or_explanation`.
- Start quantitative bars at zero. A non-zero bar baseline requires a scientific
  necessity, a visible axis break, and an explanation of its visual effect.
- Do not hide category labels unless titles, direct labels, or a legend preserve
  every identity without ambiguity.
- Do not encode categories, ablations, or evidence strength with hue or alpha
  alone. Add hatching, marker shape, line style, borders, or direct labels.
- Do not use red/green semantics as the sole channel. Prefer the accessible
  palettes registered by `scripts/figures.py` and verify grayscale/CVD legibility.
- Treat ultra-wide canvases as a reference-only layout idea. Derive physical size
  from the target venue's final single/double-column width and inspect that size.
- Disclose heatmap scale, normalization, range, clipping, missing-value mask, and
  units. Column-wise normalization destroys cross-column absolute comparability.
- Treat radar and 3D figures as reference-only and provide a checkable table,
  Cartesian plot, 2D projection, or other appropriate alternative.
- Never present demo/random data or a conceptual illustration as an observation.

Apply the license gate before reusing upstream text, code, data, or assets. This
directory is CC BY-NC 4.0 and is not relicensed by the repository's root MIT
license. For commercial or unclear reuse, do not copy or adapt upstream material;
use independently implemented general principles or obtain separate permission.

## Workflow

1. Audit the real input data, definitions, units, missingness, sampling unit, and
   uncertainty before choosing a chart.
2. Open only the task-relevant reference from the table below.
3. Implement a headless, rerunnable script with explicit parameters and stable
   outputs. Do not rely on notebook hidden state.
4. Export at least one editable vector file plus a preview raster.
5. Record inputs, script, outputs, axes/colorbar decisions, transformations,
   caption, locked source revision, and signed human visual review in the project
   figure manifest; run `python scripts/figures.py check <workspace>`.

Open `references/` only as needed; do not preload every file. Start from the table below, then follow links inside the document you opened (and into `figure_*` code via [references/demos.md](references/demos.md)) instead of loading the full reference set up front.

## When to load this skill

- Matplotlib figures for **papers, slides, or reports** that must match **this repo’s publication look** (fonts, palette, spines, legends, export).
- Requests involving **grouped bars, trend lines, heatmaps, multi-panel grids**, or **PDF/SVG/high-DPI** output in a scientific-figure context.
- References to **figures4papers** `figure_*` projects or “same style as the repo figures.”

## When not to load

- **Plotly, Altair, Bokeh**, or other interactive / web-first plotting.
- **EDA-only** plots where seaborn or pandas is enough until there is a publication target.
- Primary workflow is **3D, GIS**, or **non-matplotlib** tooling.
- **Illustrator / Figma–first** layout or infographic (not matplotlib data plots).

## Related files

| File | Open when |
|------|-----------|
| [references/tutorials.md](references/tutorials.md) | End-to-end walkthroughs (bar, trends, heatmap) |
| [references/api.md](references/api.md) | Function signatures, `PALETTE`, validation rules |
| [references/common-patterns.md](references/common-patterns.md) | Layout patterns, legend panel, print-safe bars |
| [references/design-theory.md](references/design-theory.md) | Typography, export policy, palette rationale |
| [references/demos.md](references/demos.md) | Canonical `figure_*` demo links in figures4papers |

## License and provenance

Read [SOURCE.md](SOURCE.md) before copying or adapting any upstream material and
retain [LICENSE](LICENSE) with redistributed copies of this Skill.
