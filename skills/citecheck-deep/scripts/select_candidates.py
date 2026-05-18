"""Select deep-check candidates from a citecheck report JSON.

Routing rules (applied in priority order):
  reason == "no_abstract"                              → nlm_queue
  reason in skip set                                   → skipped
  (score <= threshold OR title fuzzy/mismatch) AND has arxiv_id → arxiv_queue
  (score <= threshold OR title fuzzy/mismatch) AND no arxiv_id  → nlm_queue
  otherwise                                            → skipped
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_SKIP_REASONS = {"missing_bib_entry", "no_bib_metadata", "fetch_error"}
_TITLE_ISSUES = {"fuzzy", "mismatch"}


def _all_rows(report: dict) -> list[dict]:
    # all_rows is the authoritative superset (includes no_abstract entries
    # which do not appear in needing_review or ok).
    return report.get("all_rows", [])


def select(report: dict, bib_index: dict, threshold: int) -> dict:
    arxiv_queue: list[dict] = []
    nlm_queue: list[dict] = []
    skipped: list[dict] = []

    for row in _all_rows(report):
        bibkey = row["bibkey"]
        bib = bib_index.get(bibkey, {})

        entry = {
            "id": row.get("id", bibkey),
            "bibkey": bibkey,
            "bib_title": row.get("bib_title") or bib.get("title"),
            "first_author": bib.get("first_author"),
            "year": bib.get("year"),
            "arxiv_id": bib.get("arxiv_id"),
            "paragraph": row.get("paragraph", ""),
            "section_heading": row.get("section_heading", ""),
            "line": row.get("line"),
            "score": row.get("score"),
            "source": row.get("source"),
        }

        reason = row.get("reason")
        score = row.get("score")
        title_match = row.get("title_match")
        arxiv_id = bib.get("arxiv_id")

        if reason == "no_abstract":
            nlm_queue.append(entry)
            continue

        if reason in _SKIP_REASONS:
            entry["skip_reason"] = reason
            skipped.append(entry)
            continue

        needs_deep = (score is not None and score <= threshold) or (title_match in _TITLE_ISSUES)
        if not needs_deep:
            entry["skip_reason"] = "score_ok"
            skipped.append(entry)
            continue

        if arxiv_id:
            arxiv_queue.append(entry)
        else:
            nlm_queue.append(entry)

    return {"arxiv_queue": arxiv_queue, "nlm_queue": nlm_queue, "skipped": skipped}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", required=True, help="Path to .citecheck/<basename>.json")
    ap.add_argument("--bib-index", required=True, help="Path to bib_index.json")
    ap.add_argument("--threshold", type=int, default=6)
    ap.add_argument("--out-arxiv", required=True)
    ap.add_argument("--out-nlm", required=True)
    args = ap.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    bib_index = json.loads(Path(args.bib_index).read_text(encoding="utf-8"))
    result = select(report, bib_index, args.threshold)

    Path(args.out_arxiv).write_text(json.dumps(result["arxiv_queue"], indent=2), encoding="utf-8")
    Path(args.out_nlm).write_text(json.dumps(result["nlm_queue"], indent=2), encoding="utf-8")
    print(
        f"arxiv_queue: {len(result['arxiv_queue'])} · "
        f"nlm_queue: {len(result['nlm_queue'])} · "
        f"skipped: {len(result['skipped'])}"
    )


if __name__ == "__main__":
    main()
