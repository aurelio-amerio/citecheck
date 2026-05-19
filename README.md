# citecheck

Pertinence review for `\cite` references in LaTeX research documents. Scores each
citation 1–10 against the cited paper's abstract (InspireHEP, with arXiv fallback)
to flag mistakenly inserted or hallucinated references.

## Install

```
/plugin marketplace add https://github.com/aurelio-amerio/citecheck
/plugin install citecheck@citecheck-plugin
```

### Reduce permission prompts

After installing, add this to your project's `.claude/settings.json` to auto-approve all citecheck script invocations:

```json
{
  "permissions": {
    "allow": [
      "Bash(citecheck-* *)"
    ]
  }
}
```

## Use

```
/citecheck path/to/section.tex
```

Optional flags:

| Flag | Description |
|------|-------------|
| `--bib <path>` | Path to `.bib` file (default: walks up from the `.tex` file) |
| `--refresh` | Re-fetch all abstracts, ignoring the cache |
| `--refresh-missing` | Re-fetch only `not_found` entries |
| `--cross-check` | Verify Inspire hits against arXiv when titles mismatch |
| `--no-arxiv-fallback` | Disable arXiv fallback, use InspireHEP only |
| `--batch-size N` | Citations per scorer batch (default: 15) |
| `--parallel N` | Parallel fetch workers (default: 8) |

The report is written to `.citecheck/<basename>.md` and `.citecheck/<basename>.json`.
Abstract metadata is cached in `.citecache/abstracts/` and reused across runs.

## How it works

1. Parses `bibliography.bib` for title, arXiv ID, DOI, and first author.
2. Extracts every `\cite{...}` key from the `.tex` file with its surrounding paragraph and section heading.
3. Fetches each paper's abstract from InspireHEP (arXiv ID → DOI → title) with arXiv as fallback.
4. Dispatches batches of citations to parallel haiku scorer subagents, each scoring 1–10 against the abstract.
5. Collates results into a Markdown report sorted by score (worst first).

## Score rubric

| Score | Meaning |
|-------|---------|
| 9–10 | Abstract directly supports the specific claim |
| 7–8 | Same sub-topic; plausibly relevant |
| 5–6 | Same broad area; background reference |
| 3–4 | Adjacent field; tenuous connection |
| 1–2 | Off-topic; likely a wrong or hallucinated key |
