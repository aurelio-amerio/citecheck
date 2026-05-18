"""Merge deep-check verdicts into a citecheck report and regenerate the markdown."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_DEEP_FIELDS = ("deep_score", "deep_verdict", "deep_reason", "deep_source", "deep_nlm_evidence")
_SKIPPED_DEFAULTS = {
    "deep_score": None,
    "deep_verdict": "skipped",
    "deep_reason": None,
    "deep_source": "skipped",
    "deep_nlm_evidence": None,
}


def merge_verdicts(report: dict, verdicts: list[dict]) -> dict:
    # Later entries override earlier ones for the same id (NLM overrides Sonnet
    # for escalated entries when verdicts list has Sonnet first, NLM second).
    by_id: dict[str, dict] = {}
    for v in verdicts:
        by_id[v["id"]] = v
    # Update all three lists so every view of the report is consistent.
    for section in ("all_rows", "needing_review", "ok"):
        for row in report.get(section, []):
            v = by_id.get(row.get("id"))
            if v:
                for field in _DEEP_FIELDS:
                    row[field] = v.get(field)
            else:
                row.update(_SKIPPED_DEFAULTS)
    return report


def render_deep_section(report: dict) -> str:
    all_rows = report.get("all_rows", [])
    deep_rows = [r for r in all_rows if r.get("deep_verdict") not in (None, "skipped")]

    mismatches = [r for r in deep_rows if r["deep_verdict"] == "mismatch"]
    inconclusive = [r for r in deep_rows if r["deep_verdict"] == "inconclusive"]
    confirmed = [r for r in deep_rows if r["deep_verdict"] == "confirmed"]

    n_arxiv = sum(1 for r in deep_rows if r.get("deep_source") == "arxiv_pdf")
    n_nlm = sum(1 for r in deep_rows if r.get("deep_source") == "notebooklm")

    lines = [
        "## Deep-check verdicts",
        "",
        f"**Summary:** {n_arxiv} arXiv-PDF · {n_nlm} NotebookLM · "
        f"{len(confirmed)} confirmed · {len(mismatches)} mismatch · {len(inconclusive)} inconclusive",
        "",
    ]

    def _entry_block(row: dict) -> list[str]:
        verdict = row["deep_verdict"].upper()
        src = "arXiv PDF" if row.get("deep_source") == "arxiv_pdf" else "NotebookLM"
        block = [
            f"### line {row.get('line', '?')} — **{verdict}** — `{row['bibkey']}`",
            "",
            f"**Title:** *{row.get('bib_title', '')}*  ",
            f"**Source:** {src}  ",
            f"**Reason:** {row.get('deep_reason', '')}",
        ]
        evidence = row.get("deep_nlm_evidence")
        if evidence:
            block += ["", f"> {evidence}"]
        block.append("")
        return block

    if mismatches:
        lines += ["### Mismatches (remove or replace)", ""]
        for r in sorted(mismatches, key=lambda x: x.get("line", 0)):
            lines.extend(_entry_block(r))

    if inconclusive:
        lines += ["### Inconclusive (manual review)", ""]
        for r in sorted(inconclusive, key=lambda x: x.get("line", 0)):
            lines.extend(_entry_block(r))

    if confirmed:
        lines += ["### Confirmed (retain)", ""]
        for r in sorted(confirmed, key=lambda x: x.get("line", 0)):
            lines.extend(_entry_block(r))

    return "\n".join(lines)


def collate_deep(report_path: str, verdicts_path: str, md_path: str) -> None:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    verdicts = json.loads(Path(verdicts_path).read_text(encoding="utf-8"))

    augmented = merge_verdicts(report, verdicts)
    Path(report_path).write_text(json.dumps(augmented, indent=2), encoding="utf-8")

    deep_md = render_deep_section(augmented)

    existing_md = Path(md_path).read_text(encoding="utf-8") if Path(md_path).exists() else ""
    cut = existing_md.find("\n## Deep-check verdicts")
    base_md = existing_md[:cut] if cut != -1 else existing_md
    Path(md_path).write_text(base_md.rstrip() + "\n\n" + deep_md + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", required=True)
    ap.add_argument("--deep-verdicts", required=True)
    ap.add_argument("--output-md", required=True)
    args = ap.parse_args()
    collate_deep(args.report, args.deep_verdicts, args.output_md)
    print(f"Deep report written to {args.output_md}")


if __name__ == "__main__":
    main()
