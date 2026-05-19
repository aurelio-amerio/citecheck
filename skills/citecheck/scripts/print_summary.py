from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def summarize(report_path: Path) -> str:
    try:
        d = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise SystemExit(f"print_summary: cannot read report: {e}") from None
    needing = d.get("scored_low", 0) + d.get("scored_borderline", 0)
    title_issues = len(d.get("title_match_issues") or [])
    md_path = Path(report_path).with_suffix(".md")
    return (
        f"{d.get('total_citations', 0)} citations · {needing} needing review · "
        f"{title_issues} title-match issues · report at {md_path}"
    )


def _cli() -> int:
    p = argparse.ArgumentParser(description="Print one-line citecheck summary.")
    p.add_argument("report", help="Path to .citecheck/<basename>.json")
    args = p.parse_args()
    print(summarize(args.report))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
