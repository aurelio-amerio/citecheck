# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**citecheck** is a Claude Code plugin that validates citations in LaTeX research papers. It scores each `\cite{...}` reference against the cited paper's abstract (1–10) to flag hallucinated or misplaced references. It distributes as a plugin installable via:
```
/plugin marketplace add https://github.com/aurelio-amerio/citecheck
```

## Commands

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_parse_bib.py

# Run a specific test
pytest tests/test_parse_bib.py::test_name
```

No build step or external dependencies — all scripts use Python 3 stdlib only.

## Architecture

The tool is a **two-skill pipeline** orchestrated by Claude Code skills, with Python scripts handling data transformation at each stage.

### Skill 1: `/citecheck` (Quick Scoring)

Orchestrated by `skills/citecheck/SKILL.md`. Runs 11 steps:

1. Parse `.bib` → `bib_index.json` (via `parse_bib.py`)
2. Extract `\cite{...}` with paragraph + section context → `citations.json` (via `extract_citations.py`)
3. Determine which abstracts are missing from cache → `missing_keys.json` (via `compute_missing.py`)
4. Fetch abstracts from InspireHEP (arXiv → DOI → title fallback chain) → `.citecache/abstracts/` (via `fetch_abstracts.py`)
5. Group citations into JSON batches → `batch_N_input.json` (via `build_batches.py`)
6. Dispatch parallel `citecheck-scorer` subagents (Haiku) to score batches → `batch_N_output.json`
7. Collate all scores → `.citecheck/<basename>.md` + `.json` (via `collate_report.py`)

### Skill 2: `/citecheck-deep` (Deep Verification)

Orchestrated by `skills/citecheck-deep/SKILL.md`. Runs after `/citecheck` for flagged citations:

1. Select candidates below score threshold or with title mismatches → `arxiv_queue.json` + `nlm_queue.json` (via `select_candidates.py`)
2. Fetch full arXiv PDFs → `.citecache/pdfs/`
3. Dispatch parallel `citecheck-deep-scorer` subagents (Sonnet) to read PDFs → `deep_verdicts.json`
4. Escalate inconclusive to NotebookLM (must run **serially** — one NLM call at a time)
5. Merge verdicts into updated `.citecheck/<basename>.md` + `.json` (via `collate_deep_report.py`)

### Subagents

- `agents/citecheck-scorer.md` — Haiku agent, Read+Write only, scores a batch of citations against abstracts
- `agents/citecheck-deep-scorer.md` — Sonnet agent, Read-only, reads arXiv PDFs and returns structured verdicts; explicitly injection-guarded

### Caching

Three cache layers (all gitignored):
- `.citecache/abstracts/` — InspireHEP/arXiv abstracts, keyed by bibkey; persists across runs
- `.citecache/pdfs/` — arXiv full PDFs, keyed by arxiv_id
- `.citecache/deep_verdicts/` — Sonnet + NLM verdicts, keyed by `SHA256(bibkey || paragraph)`

Cache is reused unless `--refresh` or `--refresh-missing` flags are passed.

### Data Flow

```
.tex + .bib
  → parse_bib.py → bib_index.json
  → extract_citations.py → citations.json
  → fetch_abstracts.py → .citecache/abstracts/
  → build_batches.py → batch_N_input.json
  → citecheck-scorer (Haiku, parallel) → batch_N_output.json
  → collate_report.py → .citecheck/<basename>.{md,json}
  → [deep] select_candidates.py → arxiv_queue.json / nlm_queue.json
  → [deep] citecheck-deep-scorer (Sonnet, parallel) → deep_verdicts.json
  → [deep] NotebookLM (serial) → deep_verdicts.json
  → [deep] collate_deep_report.py → updated .citecheck/<basename>.{md,json}
```

### Score Rubric

| Score | Meaning |
|-------|---------|
| 9–10 | Paper directly supports the claim |
| 7–8 | Same sub-topic, plausibly relevant |
| 5–6 | Same broad area, background reference |
| 3–4 | Adjacent field, tenuous connection |
| 1–2 | Off-topic; likely hallucinated |

### Key Implementation Constraints

- **NotebookLM calls must be serial** — never dispatch concurrent NLM queries; the user's account allows only one at a time
- Scripts detect `$CLAUDE_PLUGIN_ROOT` to resolve paths when running as a plugin vs. local checkout
- `tests/conftest.py` adds skill script directories to `sys.path` so test imports work without installation
- The tool never modifies `.tex` or `.bib` files; it only writes to `.citecheck/` and `.citecache/`
- Batch failures are retried once; the pipeline reports errors downstream rather than halting
