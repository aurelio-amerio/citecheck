---
name: citecheck
description: Score \cite pertinence in a LaTeX file. Use when the user runs /citecheck on a .tex file or asks to verify references against InspireHEP/arXiv abstracts.
---

# citecheck

Score every `\cite{...}` in a single LaTeX file against the cited paper's
abstract (InspireHEP preferred, arXiv as fallback), surface low-scoring or
title-mismatched citations for manual review.

## Inputs

- `tex_file` — absolute path to the `.tex` file passed by the user.
- Optional flags (parsed from the user message):
  `--bib <path>`, `--refresh`, `--refresh-missing`,
  `--no-arxiv-fallback`, `--cross-check`,
  `--batch-size <n>` (default 15), `--parallel <n>` (default 8).

All scripts live under the plugin's `skills/citecheck/scripts/` directory.
At the start of every bash block, set the `SCRIPTS` variable so the commands
work whether the skill was loaded from a plugin or from the local
`.claude/skills/citecheck/` checkout:

```bash
SCRIPTS="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/citecheck/scripts}"
SCRIPTS="${SCRIPTS:-.claude/skills/citecheck/scripts}"
```

All outputs are written under `.citecheck/` and `.citecache/` rooted at the
current working directory.

## Steps

1. **Resolve bib.** If `--bib` was given, use it. Otherwise walk up from
   `tex_file` until a `bibliography.bib` is found. Fail fast with a clear
   message if none.

2. **Build bib index.** Clear any intermediates from a prior aborted run
   first — `.citecache/` (the abstract cache) is intentionally preserved.

   ```bash
   rm -rf .citecheck/.tmp
   mkdir -p .citecheck/.tmp
   python3 ${SCRIPTS}/parse_bib.py \
       <bib_path> .citecheck/.tmp/bib_index.json
   ```

3. **Extract citations.**

   ```bash
   python3 ${SCRIPTS}/extract_citations.py \
       <tex_file> .citecheck/.tmp/citations.json
   ```

   If the citations file is empty, print
   `No \cite references found in <tex_file>.` and stop.

4. **Compute missing keys.** Decides which bibkeys need a fresh fetch given
   the bib index, citations, and current cache. Skip rules:
   - bibkey not in `bib_index.json` → skip (will be marked
     `abstract_status: "missing_bib_entry"` in step 6).
   - bib entry has no `title` AND no `arxiv_id` AND no `doi` → skip
     (will be marked `abstract_status: "no_bib_metadata"`).
   - cache hit with `source == "fetch_error"` → always re-fetch.
   - cache hit with `source == "not_found"` → re-fetch only when
     `--refresh-missing` is passed.
   - cache hit with any other source → re-fetch only when `--refresh` is passed.

   ```bash
   python3 ${SCRIPTS}/compute_missing.py \
       --citations .citecheck/.tmp/citations.json \
       --bib-index .citecheck/.tmp/bib_index.json \
       --cache-dir .citecache/abstracts \
       --out .citecheck/.tmp/missing_keys.json \
       [--refresh] [--refresh-missing]
   ```

5. **Fetch missing abstracts.**

   ```bash
   python3 ${SCRIPTS}/fetch_abstracts.py \
       --missing .citecheck/.tmp/missing_keys.json \
       --cache-dir .citecache/abstracts \
       --parallel <parallel> \
       [--cross-check] [--no-arxiv-fallback]
   ```

6. **Build batches.**

   ```bash
   python3 ${SCRIPTS}/build_batches.py \
       --citations .citecheck/.tmp/citations.json \
       --bib-index .citecheck/.tmp/bib_index.json \
       --abstracts-dir .citecache/abstracts \
       --out-dir .citecheck/.tmp/ \
       --batch-size <batch_size>
   ```

   Writes `.citecheck/.tmp/batch_<n>_input.json` (1-indexed). Each entry has
   `{id: "c<i>", bibkey, bib_title, fetched_title, abstract, abstract_status,
   paragraph, section_heading, line}`. `abstract_status` is one of
   `ok`, `fuzzy`, `mismatch`, `not_found`, `fetch_error`,
   `missing_bib_entry`, `no_bib_metadata`. The script prints the batch count
   on stdout.

7. **Dispatch scorers.** In a single message, issue one `Agent` call per
   batch with:
   - `subagent_type: "citecheck-scorer"`
   - `description: "Score batch <n>"`
   - `prompt: "input_path: .citecheck/.tmp/batch_<n>_input.json\noutput_path: .citecheck/.tmp/batch_<n>_output.json"`

   Concurrency budget: at most 8 parallel `Agent` calls per wave. For more
   than 8 batches, dispatch in waves of 8.

8. **Validate outputs.** For each batch, check that
   `.citecheck/.tmp/batch_<n>_output.json` exists and parses as a JSON list
   whose entries have `{id, bibkey, score, reason}`. On malformed/missing
   output, retry that batch's `Agent` call once. If the retry also fails,
   leave that batch's citations with `score: null, reason: "scoring_failed"`
   and continue.

9. **Collate report.**

   ```bash
   python3 ${SCRIPTS}/collate_report.py \
       --citations .citecheck/.tmp/citations.json \
       --scores-dir .citecheck/.tmp/ \
       --abstracts-dir .citecache/abstracts \
       --tex-path <tex_file> \
       --output-md .citecheck/<basename>.md \
       --output-json .citecheck/<basename>.json
   ```

10. **Clean tmp.** Remove `.citecheck/.tmp/`.

11. **Print summary.** Read the report JSON (a dict, not a list) and print one line:

   ```bash
   python3 -c "
   import json, sys
   d = json.load(open('.citecheck/<basename>.json'))
   needing = d['scored_low'] + d['scored_borderline']
   title_issues = len(d['title_match_issues'])
   print(f\"{d['total_citations']} citations · {needing} needing review · {title_issues} title-match issues · report at .citecheck/<basename>.md\")
   "
   ```

## Invariants

- Never modify the `.tex` file or `bibliography.bib`.
- Subagents must only call `Read` and `Write`. Reject any other tool surface.
- Abstract cache persists across runs; scoring is always recomputed.
- If a step fails, stop and report the failing step rather than continuing
  with partial state.
