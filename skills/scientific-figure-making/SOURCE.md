# Installed source, local changes, and license boundary

This local Codex skill was installed from:

- Repository: `ChenLiu-1996/figures4papers`
- Path: `scientific-figure-making/`
- Locked revision audited by the installer workflow:
  `3c181f85e82c6f24948fcaaf3be6696102b41d8d`
- Source URL: <https://github.com/ChenLiu-1996/figures4papers>
- Installed in this repository at: `skills/scientific-figure-making/`
- Installation date: `2026-09-24`
- License: CC BY-NC 4.0; see `LICENSE` in this directory

The repository is not a Codex/ChatGPT plugin: it has no plugin manifest,
MCP server, or app connector. This directory contains only the installable
`scientific-figure-making` skill (its `SKILL.md` and five references), plus
the license and source record added at installation time. It does not contain
the upstream repository's 25 plotting scripts, 39 PNG files, or 3 PDF files.

Direct copying or adaptation is limited to uses permitted by CC BY-NC 4.0,
including attribution, a license link, change indication, and noncommercial
use. For commercial or unclear use, independently implement general plotting
principles instead of copying source text, code, paper data, or images.

## Changes from the locked upstream Skill

The upstream `SKILL.md` and its five references were installed as the real
Skill, then adapted for Ku-academic under CC BY-NC 4.0:

- added a mandatory local policy and license gate;
- made Ku-academic's truth, provenance, accessibility, zero-baseline, heatmap,
  radar/3D, and human-review rules explicitly higher priority;
- annotated or narrowed upstream suggestions about truncated axes, hidden labels,
  alpha-only ablations, red/green semantics, and ultra-wide canvases;
- pinned every demo link to revision
  `3c181f85e82c6f24948fcaaf3be6696102b41d8d` instead of the moving `main` branch;
- added `agents/openai.yaml` for independent Skill discovery.

No upstream plotting scripts, demo data, PNG/PDF outputs, or paper assets are
included. The repository-root MIT license expressly does not relicense this
directory: all files under `skills/scientific-figure-making/` are distributed
under the CC BY-NC 4.0 terms in the adjacent `LICENSE`.
