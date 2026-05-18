"""Print a one-line deep-check summary from a collated citecheck report JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize(report_path: str, md_path: str) -> None:
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    rows = data.get("all_rows", [])
    deep = [r for r in rows if r.get("deep_verdict") not in (None, "skipped")]

    n_arxiv = sum(1 for r in deep if r.get("deep_source") == "arxiv_pdf")
    n_nlm = sum(1 for r in deep if r.get("deep_source") == "notebooklm")
    n_confirmed = sum(1 for r in deep if r.get("deep_verdict") == "confirmed")
    n_mismatch = sum(1 for r in deep if r.get("deep_verdict") == "mismatch")
    n_inconclusive = sum(1 for r in deep if r.get("deep_verdict") == "inconclusive")

    print(
        f"Deep-check complete: {n_arxiv} arXiv-PDF · {n_nlm} NotebookLM · "
        f"{n_confirmed} confirmed · {n_mismatch} mismatch · {n_inconclusive} inconclusive · "
        f"report at {md_path}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", required=True)
    ap.add_argument("--md", required=True)
    args = ap.parse_args()
    summarize(args.report, args.md)


if __name__ == "__main__":
    main()
