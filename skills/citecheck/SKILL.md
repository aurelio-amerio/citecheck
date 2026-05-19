---
name: citecheck
description: Score \cite pertinence in a LaTeX file. Use when the user runs /citecheck on a .tex file or asks to verify references against InspireHEP/arXiv abstracts.
---

# citecheck

Score every `\cite{...}` in one or more LaTeX files against the cited paper's
abstract (InspireHEP preferred, arXiv as fallback), surface low-scoring or
title-mismatched citations for manual review.

## Inputs

- `tex_files` — one or more absolute paths to `.tex` files passed by the user.
- Optional flags (parsed from the user message):
  `--bib <path>`, `--refresh`, `--refresh-missing`,
  `--no-arxiv-fallback`, `--cross-check`,
  `--batch-size <n>` (default 15), `--parallel <n>` (default 8).

All outputs are written under `.citecheck/` and `.citecache/` rooted at the
current working directory.

## Steps

**Repeat steps 1–11 for each `tex_file` in order, one at a time.** Do not
start the next file until the current one completes. Print
`[1/N] Processing <tex_file> …` before each file's step 1.

1. **Resolve bib.** If `--bib` was given, use it. Otherwise walk up from
   `tex_file` until a `bibliography.bib` is found. Fail fast with a clear
   message if none.

2. **Build bib index.** Clear any intermediates from a prior aborted run
   first — `.citecache/` (the abstract cache) is intentionally preserved.

   ```bash
   rm -rf .citecheck/.tmp
   mkdir -p .citecheck/.tmp
   citecheck-parse-bib \
       <bib_path> .citecheck/.tmp/bib_index.json
   ```

3. **Extract citations.**

   ```bash
   citecheck-extract-citations \
       <tex_file> .citecheck/.tmp/citations.json
   ```

   If the citations file is empty, print
   `No \cite references found in <tex_file>.` and skip to the next file.

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
   citecheck-compute-missing \
       --citations .citecheck/.tmp/citations.json \
       --bib-index .citecheck/.tmp/bib_index.json \
       --cache-dir .citecache/abstracts \
       --out .citecheck/.tmp/missing_keys.json \
       [--refresh] [--refresh-missing]
   ```

5. **Fetch missing abstracts.**

   ```bash
   citecheck-fetch-abstracts \
       --missing .citecheck/.tmp/missing_keys.json \
       --cache-dir .citecache/abstracts \
       --parallel <parallel> \
       [--cross-check] [--no-arxiv-fallback]
   ```

6. **Build batches.**

   ```bash
   citecheck-build-batches \
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
   citecheck-collate-report \
       --citations .citecheck/.tmp/citations.json \
       --scores-dir .citecheck/.tmp/ \
       --abstracts-dir .citecache/abstracts \
       --tex-path <tex_file> \
       --output-md .citecheck/<basename>.md \
       --output-json .citecheck/<basename>.json
   ```

10. **Clean tmp.** Remove `.citecheck/.tmp/`.

11. **Print per-file summary.** Read the report JSON (a dict, not a list) and print one line:

    ```bash
    citecheck-print-summary .citecheck/<basename>.json
    ```

12. **Combined summary (multi-file only).** After all files are processed,
    if more than one file was given, print a single totals line:

    ```
    Done. <total_citations> citations across <N> files · <total_needing> needing review · <total_title_issues> title-match issues
    ```

## Invariants

- Never modify the `.tex` file or `bibliography.bib`.
- Subagents must only call `Read` and `Write`. Reject any other tool surface.
- Abstract cache persists across runs; scoring is always recomputed.
- If a step fails for one file, report the error and continue with the next file rather than aborting the whole run.
