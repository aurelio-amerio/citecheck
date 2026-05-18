"""Build scorer-input batches from citations, bib index, and abstract cache.

Codifies the schema that `collate_report.py` and `agents/citecheck-scorer.md`
expect, so the SKILL.md inline logic does not have to reinvent it:

  - IDs are strings of the form ``c<i>`` matching the citation index.
  - Cache files are looked up via ``bibkey.replace("/", "_") + ".json"``
    (same convention as ``fetch_abstracts.py``).
  - ``abstract_status`` is one of: ok, fuzzy, mismatch, not_found,
    fetch_error, missing_bib_entry, no_bib_metadata.

Each batch is written to ``<out-dir>/batch_<n>_input.json`` (1-indexed).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def safe_bibkey(bibkey: str) -> str:
    """Cache-filename sanitization. Must match fetch_abstracts.write_cache()."""
    return bibkey.replace("/", "_")


def _status_from_cache(cached: dict) -> str:
    src = cached.get("source")
    if src == "not_found":
        return "not_found"
    if src == "fetch_error":
        return "fetch_error"
    # ok / fuzzy / mismatch
    return cached.get("title_match") or "ok"


def derive_row(
    idx: int,
    citation: dict,
    bib_index: dict,
    abstracts_dir: Path,
) -> dict:
    bibkey = citation["bibkey"]
    entry = bib_index.get(bibkey)
    if entry is None:
        status, abstract, fetched_title = "missing_bib_entry", None, None
        bib_title = None
    elif not (entry.get("title") or entry.get("arxiv_id") or entry.get("doi")):
        status, abstract, fetched_title = "no_bib_metadata", None, None
        bib_title = entry.get("title")
    else:
        bib_title = entry.get("title")
        cache_path = abstracts_dir / f"{safe_bibkey(bibkey)}.json"
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cached = None
            if cached is None:
                status, abstract, fetched_title = "fetch_error", None, None
            else:
                status = _status_from_cache(cached)
                abstract = cached.get("abstract")
                fetched_title = cached.get("title")
        else:
            status, abstract, fetched_title = "fetch_error", None, None

    return {
        "id": f"c{idx}",
        "bibkey": bibkey,
        "bib_title": bib_title,
        "fetched_title": fetched_title,
        "abstract": abstract,
        "abstract_status": status,
        "paragraph": citation.get("paragraph", ""),
        "section_heading": citation.get("section_heading", ""),
        "line": citation.get("line"),
    }


def build_batches(
    citations: list[dict],
    bib_index: dict,
    abstracts_dir: Path,
    *,
    batch_size: int = 15,
) -> list[list[dict]]:
    rows = [derive_row(i, c, bib_index, abstracts_dir) for i, c in enumerate(citations)]
    return [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--citations", required=True)
    p.add_argument("--bib-index", required=True)
    p.add_argument("--abstracts-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--batch-size", type=int, default=15)
    args = p.parse_args()

    citations = json.loads(Path(args.citations).read_text(encoding="utf-8"))
    bib_index = json.loads(Path(args.bib_index).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    batches = build_batches(
        citations, bib_index, Path(args.abstracts_dir), batch_size=args.batch_size
    )
    for n, batch in enumerate(batches, start=1):
        path = out_dir / f"batch_{n}_input.json"
        path.write_text(json.dumps(batch, indent=2), encoding="utf-8")
    # Print batch count so the calling skill can iterate without re-scanning.
    print(len(batches))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
