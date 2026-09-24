# Common Patterns for Publication Figures

These patterns are used across the repository for consistent, publication-ready figures. Apply them when building bar charts, multi-panel layouts, and print-safe graphics. Step-by-step flows that use many of these ideas are in [tutorials.md](tutorials.md); for chart types not covered there, use the closing section of that file and [demos.md](demos.md).

> **Ku-academic override:** These are upstream patterns, not unconditional local
> defaults. The policy gate in [SKILL.md](../SKILL.md) wins. In particular, do
> not truncate quantitative bar axes, hide identities, encode categories with
> alpha/hue alone, use red/green semantics alone, or select an ultra-wide canvas
> before checking final venue dimensions.

---

## Ultra-wide aspect for multi-metric panels

For 3-4 metrics or many categories in a single row, a wide canvas can be studied
as a reference layout so bars/labels do not crowd vertically.

- **Example:** `figsize=(45, 12)` or `(28, 6)`.
- **Local rule:** Do not copy these dimensions as a default. Derive the canvas
  from the journal's physical single/double-column width and label density; split
  the figure when the final-size text would otherwise become unreadable.
- **Why:** Lets the reader scan left-to-right without squinting; keeps y-axis and legend readable.

---

## Dedicated legend panel

When multiple curves or groups make the legend large, put it in its own subplot so it doesn't cover data.

- **Steps:**
  1. Create one extra subplot (e.g. last in the grid).
  2. Call `ax.set_axis_off()` on that axis.
  3. Build the legend on that axis (e.g. gather handles/labels from other axes and call `ax.legend(handles, labels)` there), or use a single legend that you place in the extra axis.
- **Result:** Data panels stay clean; legend is fully visible.

---

## Categorical bars without x-tick labels

When the x-axis is "method" or "condition" and the legend already identifies them, hide x ticks and rely on the legend/title.

- **Code:** `ax.set_xticks([])` or set tick labels to empty.
- **Use when:** Only when every category remains unambiguously identified by
  direct labels, a legend, or panel titles. Otherwise retain the ticks.

---

## Dynamic y-axis scaling

For non-bar charts, a disclosed narrow y-range may be scientifically useful.
Quantitative bars keep a zero baseline by default.

- **Idea:** Use something like `data.min() - margin` to `data.max() + margin` (e.g. margin = small fraction of range or one std).
- **Local prohibition:** Do not apply an 80-100 truncation to bars. A rare
  non-zero bar baseline needs scientific necessity, a visible break, and a
  caption explaining the visual consequence.

---

## Bar edge and hatch for print-safe separation

Bars that differ only by fill can blur in grayscale. Use edges and optional hatching.

- **Edges:** `edgecolor='black'`, `linewidth=1.5`-`3` for clear separation.
- **Hatch:** Same color with different hatch (e.g. `'/'`, `'\\'`, `'.'`) for ablation or subgroups so they remain distinct in print.

---

## Semantic color mapping

Keep semantic roles consistent across figures, but use a local registered
accessible palette and a redundant non-colour channel.

- **Upstream inventory:** Blue/green/red roles describe the source repository;
  they are not a Ku-academic default and must not become red-vs-green-only coding.
- **Neutral:** Reference or background categories.
- **Highlight:** Single callout only.

See [design-theory.md](design-theory.md) for the full palette and [api.md](api.md) for `PALETTE` and `DEFAULT_COLORS`.

## Related files

- [SKILL.md](../SKILL.md) — When to load this skill
- [api.md](api.md) — `PALETTE`, helpers, validation
- [demos.md](demos.md) — Real scripts mirroring these patterns
- [design-theory.md](design-theory.md) — Visual and color theory
- [tutorials.md](tutorials.md) — Walkthroughs that apply these patterns
