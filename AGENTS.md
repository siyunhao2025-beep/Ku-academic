# Working on Cool-Academic

For a research task, read SKILL.md, then modules/workflow.md and task-relevant modules.
Do not load every upstream repository or run third-party installers automatically.

For repository development:
- Keep the Skill identifier research-mother and a single research-mother/ directory in the installation ZIP.
- Preserve scientific quantities, units, claims and evidence strength. Never treat tests or examples as research results.
- Keep manuscripts, full-text corpora, datasets, credentials and vendor archives out of Git and release packages.
- Preserve existing interfaces and tests; keep copied upstream licenses separate.
- Before delivery run python -m unittest discover -s tests -v and python scripts/check_repository.py.
- Build releases with python scripts/build_distribution.py --out dist; update config/distribution-files.json when adding distributable files.
- Update README.md, docs/GETTING_STARTED.md and docs/USE_CASES.md when commands or interfaces change.
- A registry entry is not a host installation; PDF extraction is not reading; schema validation is not scientific verification.
- The legacy import is a one-time provenance-preserving operation. Do not re-import over local changes or bypass hash checks.
- Ship no field-specific content. `domains/example-domain` is a neutral template: keep its parameter values `null` and its `learned_capability_cards` empty, and do not put a named research field, instrument, event or conclusion into the master Skill text, the docs or the examples. Examples stay generic on purpose.
- Keep domain-specific terminology out of the repository. This is a general-purpose tool; naming any one field both narrows its audience and leaks the author's own research direction.
- Never bypass a paywall, login or captcha when obtaining papers. `scripts/sourcing.py` plans and tracks only; `scripts/corpus.py` performs downloads and enforces open-access or explicit user authorization.
- Report token figures with both the accounting basis and the counting method. Conversation tokens are not measurable locally, so that line must say so instead of being omitted.
