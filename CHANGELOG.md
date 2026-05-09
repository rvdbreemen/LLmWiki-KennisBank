# Changelog

All notable changes to LLmWiki-KennisBank are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-05-09

### Added

- `scripts/build-karpathy-index.py` builds `02-wiki/index.md` and `02-wiki/log.md` in the format that Understand-Anything's `parse-knowledge-base.py` requires (`## Section` headings + `[[wikilink]]` rows for index, `## [YYYY-MM-DD] OPERATION | Title` rows for log). It scans `02-wiki/` frontmatter (using PyYAML when available, with a minimal fallback parser) and clusters articles into 5–12 categories via, in priority order: a `category` frontmatter field, the first non-generic tag, or the `wiki-<domain>-...` filename prefix. `wiki-memory` types are pinned to a trailing `Memory-snapshots` section. Log entries come from `01-raw/sessies/raw-sessie-YYYY-MM-DD-*.md` filenames, with titles read from frontmatter when present. Flags: `--dry-run`, `--force` (writes `.bak` before overwrite), `--vault-root`, `--wiki-dir`, `--sessies-dir`. Refuses to overwrite without `--force`; honours dry-run.
- README and POST-INSTALL document the optional `/understand-knowledge` (Understand-Anything plugin) workflow as Step 8: install plugin, build index, run skill, browse dashboard. Existing graphify integration stays unchanged; the two are complementary (graphify uses semantic embeddings + hyperedges, Understand-Anything uses wikilinks + per-batch LLM analysis with categorised layers and a guided tour).

### Changed

- `POST-INSTALL.md` step numbering shifted: graphify stays at Step 7, the new knowledge-graph dashboard step is Step 8, autoresearch is Step 9, backfill is Step 10.

### Background

The integration grew out of a hands-on test of Understand-Anything against a real KennisBank vault. The detector requires `index.md` and `log.md` and does not generate them itself; `/wiki` does not write a centralised index either. `build-karpathy-index.py` closes that gap so users do not run into the same `Not a Karpathy-pattern wiki` error during their first `/understand-knowledge` invocation.

## [0.2.0] — 2026-05-08

### Added

- `AGENTS.md`, `TROUBLESHOOTING.md`, `POST-INSTALL.md`, `CONFIGURATION.md`, `OBSIDIAN.md` — install, troubleshooting, post-install walkthrough, configuration reference, Obsidian setup.
- `scripts/doctor.sh` — 12-check health verifier for vault, scripts, templates, commands, skill installation.
- `commands/import.md` (`/import` slash command) plus three importers: `scripts/import-cc-history.py`, `scripts/import-claudeai-export.py`, `scripts/import-folder.py` (with `--list-cowork-candidates`).
- `commands/sessiestart.md` (`/sessiestart` slash command) — briefing flow at session start.
- `setup.sh` flags: `--yes`, `--no-commands`, `--no-skill`, `--help` for non-interactive install.

### Fixed

- Documentation discrepancies surfaced by the publish-check: `THRESHOLD_DAYS` removed (never existed), `MIN_CONFIDENCE` and `MAX_NEW_LINKS` documented, `LEARNINGS_FILE` clarified as a convention not a config, doctor's Python warning relaxed, README numbering repaired.

## [0.1.0] — 2026-04-26

### Added

- Initial release. Core slash commands (`/sessielog`, `/wiki`, `/intake`, `/stale`), four utility scripts (`auto-crosslink.py`, `intake-scan.py`, `semantic-tiling.py`, `stale-check.py`), session-log and wiki-article templates, vault scaffolding via `setup.sh`, `/autoresearch` skill, `CLAUDE.md.template`.

[Unreleased]: https://github.com/Jvdbreemen/LLmWiki-KennisBank/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Jvdbreemen/LLmWiki-KennisBank/releases/tag/v0.3.0
[0.2.0]: https://github.com/Jvdbreemen/LLmWiki-KennisBank/releases/tag/v0.2.0
[0.1.0]: https://github.com/Jvdbreemen/LLmWiki-KennisBank/releases/tag/v0.1.0
