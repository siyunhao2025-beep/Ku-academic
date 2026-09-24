# Publication Figure Design Theory (Derived from Repository Scripts)

This theory is inferred from the Python plotting scripts in the [figures4papers](https://github.com/ChenLiu-1996/figures4papers) repository (the `figure_*` project folders). See [demos.md](demos.md) for links to those demos.

> **Ku-academic interpretation rule:** This document describes the locked
> upstream visual vocabulary; it does not override [SKILL.md](../SKILL.md) or
> the repository's local figure contracts. Treat extreme widths, hidden category
> ticks, dynamic bar-axis tightening, alpha-only ablations, and blue/green/red
> semantic coding as source observations that require local adaptation—not as
> defaults. Real-data provenance, accessible redundant encodings, quantitative
> bar zero baselines, disclosed scales, and final-size human review come first.

## 1) Core Matplotlib Style System

The dominant house style is minimalist, high-contrast, and publication-oriented:

- Typography:
  - Primary: `font.family = 'helvetica'` (used in 16 scripts).
  - Secondary exception: `font.family = 'sans-serif'` (2 scripts, mostly geometric illustrations).
  - Practical portability recommendation: prefer fallback stack `['Arial', 'Helvetica', 'DejaVu Sans', 'sans-serif']`.
- Size hierarchy:
  - Large-panel bar/comparison figures: `font.size = 24`, `axes.linewidth = 3`.
  - Paper subfigures/compact analytic plots: `font.size = 15-16`, `axes.linewidth = 2`.
- Axes cleanup:
  - `axes.spines.right = False`
  - `axes.spines.top = False`
- LaTeX usage:
  - `text.usetex = True` appears in TeX-heavy scripts (6 files), especially when math-rich labels are needed.
- Vector text:
  - `svg.fonttype = 'none'` appears when preserving editable text in vector exports.

## 2) Export and Output Policy

- DPI defaults:
  - Standard: `dpi=300` (dominant: 23 save calls).
  - Very dense bar panels: `dpi=600` (used in ImmunoStruct bars).
- Layout finalization:
  - `fig.tight_layout(pad=2)` is the default finishing pass (21 occurrences).
  - `pad=1` is used for compact multi-panel plots.
- Mostly opaque white-background output; occasional `bbox_inches='tight'` with explicit `pad_inches` for edge-to-edge composites.

## 3) Color Theory and Palette Structure

The repository uses a consistent semantic palette family:

- Anchor/brand blue:
  - `#0F4D92` and `#3775BA` (method-of-interest / reference baseline).
- Green performance bands (often incremental gains):
  - `#DDF3DE`, `#AADCA9`, `#8BCF8B`.
- Warm red/pink comparator bands:
  - `#F6CFCB`, `#E9A6A1`, `#B64342`.
- Neutral support grays:
  - `#CFCECE`, `#767676`, `#4D4D4D`, `#272727`.
- Occasional accent/highlight colors:
  - Gold `#FFD700`, magenta-like `#EA84DD`, teal `#42949E`, violet `#9A4D8E`.

Design intent:

- Use blue for "proposed" or key method.
- Use green shades for related positives/improvements.
- Use pink/red shades for alternatives or contrasts.
- Keep neutrals for baselines and background categories.

## 4) Layout and Composition Logic

Common geometric/layout decisions:

- **Ultra-Wide Aspect Ratios:** The repository uses extremely wide canvases
  (e.g., `figsize=(45, 12)` or `(28, 6)`). In Ku-academic this is
  reference-only: choose the final physical journal width first and split panels
  rather than shrinking labels into illegibility.
- **Dedicated Legend Panels:** In complex multi-axis figures, a sub-plot is often dedicated solely to the legend (`ax.set_axis_off()`). This keeps the data panels clean and prevents legend boxes from overlapping critical data regions.
- **Categorical Abstracting:** Some source bars hide x-tick labels. Locally this
  is allowed only when direct labels, titles, or a legend preserve every identity
  without ambiguity.
- **Dynamic Y-Axis Scaling:** Some source scripts tighten y-limits. Locally this
  may be considered for non-bar charts with disclosure; quantitative bars start
  at zero unless the explicit local exception is satisfied.
- **Consistency over Embellishment:** Multi-panel consistency is favored over per-axis embellishment. All subplots in a row share the same font sizes, linewidths, and color semantic mapping.

## 5) Bar Encoding Strategy

For publication-grade grouped/ablation bars:

- **In-Place Annotation:** Scientific values are often printed directly above bars (`ax.text`) with large fonts (36pt) to make exact numbers readable without a grid.
- **Manual Tick Positioning:** Uses `FixedLocator` for precise control over Y-axis granularity.
- **Strong edge treatment:** Bars use black edges (`edgecolor='black'`) with `linewidth=1.5-3` for sharp separation.
- **Alpha-Based Ablation:** The source uses alpha-based ablations. Ku-academic
  rejects alpha-only encoding; pair it with hatching, borders, direct labels, or
  another non-colour channel.
- **Hatch Encoding:** Optional hatch channels (slashes/backslashes/dots) are used for subtype overlays to remain readable in grayscale print.

## 6) Trend/Line Encoding Strategy

- Limited line count per axis (usually 2-4 primary curves).
- Use consistent line width around `2-3` with controlled alpha.
- Use `fill_between` for uncertainty when needed.
- Keep grid minimal or absent; rely on axis ticks and direct legend reading.

**Polar / radar:** Keep the number of series readable at publication size; use the same line-weight and label discipline as Cartesian trends. Repository examples live under `figure_VIGIL` (see [demos.md](demos.md)).

## 7) Scatter/Illustration Encoding Strategy

- Dense geometric scenes use lowered alpha and muted fills.
- Important trajectories/relations use saturated warm accents with arrows.
- Axis ticks often removed for conceptual diagrams.

## 8) Recommended Reusable rcParams Preset

```python
PUBLICATION_RCPARAMS = {
    "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "font.size": 16,            # use 24 for large comparison bars
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 2.5,      # 3 for big bars, 2 for compact figures
    "legend.frameon": False,
    "svg.fonttype": "none",
}
```

## 9) Upstream palette inventory (not the Ku-academic default)

```python
PALETTE = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "green_1": "#DDF3DE",
    "green_2": "#AADCA9",
    "green_3": "#8BCF8B",
    "red_1": "#F6CFCB",
    "red_2": "#E9A6A1",
    "red_strong": "#B64342",
    "neutral": "#CFCECE",
    "highlight": "#FFD700",
}
```

## 10) Locally adapted reproduction rules

To match the repository's visual identity for new figures:

1. Apply minimalist spines and frameless legends only when axes, units, and
   category identities remain complete; quantitative bar axes begin at zero.
2. Use Helvetica/Arial-like sans fonts with larger sizing for bars.
3. Use a registered accessible palette rather than blue/green/red semantics, and
   never let colour or alpha be the only category channel.
4. Treat `tight_layout`, 300/600 DPI, and wide canvases as starting points;
   choose them from final physical size and actually inspect exported files.
5. Use hatching, edges, marker/line styles, or direct labels for print-safe
   separation, then verify grayscale and common colour-vision deficiencies.

## Related files

- [SKILL.md](../SKILL.md) — When to load this skill
- [api.md](api.md) — Formal `PALETTE` and function contracts
- [demos.md](demos.md) — Repository scripts this theory summarizes
- [common-patterns.md](common-patterns.md) — Operational patterns from the theory
- [tutorials.md](tutorials.md) — Hands-on flows grounded in this theory
