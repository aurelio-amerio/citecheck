# citecheck

Pertinence review for `\cite` references in LaTeX research documents. Scores each
citation 1-10 against the cited paper's abstract (InspireHEP, with arXiv fallback)
to flag mistakenly inserted or hallucinated references.

## Install

Add this marketplace and install the plugin:

```bash
# from inside Claude Code
/plugin marketplace add <path-to-citecheck-plugin>
/plugin install citecheck
```

## Use

```
/citecheck path/to/section.tex
```

The report is written to `.citecheck/<basename>.md` and `.citecheck/<basename>.json`.

See `docs/superpowers/specs/` for the full design.
