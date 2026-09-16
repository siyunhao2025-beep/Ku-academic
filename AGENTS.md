# Working on Ku-academic

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
