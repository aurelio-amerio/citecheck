"""Merge citations, abstract cache, and batch scoring outputs into a report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def collate(
    citations: list[dict],
    scores: list[dict],
    abstracts: dict[str, dict],
    *,
    tex_path: str,
) -> dict:
    score_by_id = {s["id"]: s for s in scores}
    rows = []
    for i, cit in enumerate(citations):
        cid = f"c{i}"
        s = score_by_id.get(cid, {"score": None, "reason": "scoring_failed"})
        a = abstracts.get(cit["bibkey"], {})
        rows.append(
            {
                "id": cid,
                "bibkey": cit["bibkey"],
                "line": cit["line"],
                "section_heading": cit.get("section_heading", ""),
                "paragraph": cit.get("paragraph", ""),
                "tex_file": cit.get("tex_file", tex_path),
                "score": s.get("score"),
                "reason": s.get("reason"),
                "flag": s.get("flag"),
                "abstract_title": a.get("title"),
                "bib_title": a.get("bib_title"),
                "title_match": a.get("title_match"),
                "title_similarity": a.get("title_similarity"),
                "source": a.get("source"),
            }
        )

    scored = [r for r in rows if isinstance(r["score"], int)]
    scored_low = [r for r in scored if r["score"] <= 4]
    scored_borderline = [r for r in scored if 5 <= r["score"] <= 6]
    scored_ok = [r for r in scored if r["score"] >= 7]
    title_issues = [r for r in rows if r["title_match"] == "mismatch"]

    unscored_counts = {"no_abstract": 0, "title_mismatch": 0, "missing_bib_entry": 0,
                       "no_bib_metadata": 0, "fetch_error": 0, "scoring_failed": 0}
    for r in rows:
        if r["score"] is None and r["reason"] in unscored_counts:
            unscored_counts[r["reason"]] += 1

    avg = (sum(r["score"] for r in scored) / len(scored)) if scored else None

    return {
        "tex_file": tex_path,
        "total_citations": len(rows),
        "average_score": round(avg, 2) if avg is not None else None,
        "scored_low": len(scored_low),
        "scored_borderline": len(scored_borderline),
        "scored_ok": len(scored_ok),
        "unscored": unscored_counts,
        "title_match_issues": title_issues,
        "needing_review": sorted(scored_low + scored_borderline, key=lambda r: r["score"]),
        "ok": sorted(scored_ok, key=lambda r: -r["score"]),
        "all_rows": rows,
    }


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    a = lines.append
    a(f"# Citation review: `{report['tex_file']}`\n")
    a(f"**Total citations:** {report['total_citations']}  ")
    a(f"**Average score:** {report['average_score']}  ")
    a(f"**Scored 1-4 (review):** {report['scored_low']}  ")
    a(f"**Scored 5-6 (borderline):** {report['scored_borderline']}  ")
    unscored = report["unscored"]
    total_unscored = sum(unscored.values())
    a(f"**Unscored:** {total_unscored} " +
      "(" + ", ".join(f"{k}: {v}" for k, v in unscored.items() if v) + ")")
    a("\n---\n")

    issues = report.get("title_match_issues") or []
    if issues:
        a("## Title-match issues (manual check)\n")
        a("| line | bibkey | bib title | fetched title | similarity |")
        a("|------|--------|-----------|---------------|------------|")
        for r in issues:
            a(f"| {r['line']} | `{r['bibkey']}` | {(r.get('bib_title') or '')[:60]} | "
              f"{(r.get('abstract_title') or '')[:60]} | {r.get('title_similarity')} |")
        a("")

    needing = report.get("needing_review") or []
    a("## Citations needing review (score ≤ 6, worst first)\n")
    if not needing:
        a("_None._\n")
    for r in needing:
        a(f"### line {r['line']} — score {r['score']} — bibkey `{r['bibkey']}`\n")
        a(f"**Section:** {r.get('section_heading') or ''}  ")
        a(f"**Paragraph:** {(r.get('paragraph') or '')[:400]}  ")
        a(f"**Cited title:** *{r.get('abstract_title') or ''}*  ")
        a(f"**Reason:** {r.get('reason') or ''}\n")

    a("## Citations OK (score ≥ 7)\n")
    a("| line | score | bibkey | title |")
    a("|------|-------|--------|-------|")
    for r in (report.get("ok") or []):
        a(f"| {r['line']} | {r['score']} | `{r['bibkey']}` | {(r.get('abstract_title') or '')[:80]} |")

    return "\n".join(lines) + "\n"


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--citations", required=True)
    p.add_argument("--scores-dir", required=True, help="dir containing batch_*_output.json")
    p.add_argument("--abstracts-dir", required=True)
    p.add_argument("--tex-path", required=True)
    p.add_argument("--output-md", required=True)
    p.add_argument("--output-json", required=True)
    args = p.parse_args()

    citations = json.loads(Path(args.citations).read_text(encoding="utf-8"))
    scores: list[dict] = []
    for f in sorted(Path(args.scores_dir).glob("batch_*_output.json")):
        scores.extend(json.loads(f.read_text(encoding="utf-8")))
    abstracts: dict[str, dict] = {}
    for f in Path(args.abstracts_dir).glob("*.json"):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            abstracts[rec["bibkey"]] = rec
        except Exception:
            continue

    report = collate(citations, scores, abstracts, tex_path=args.tex_path)
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_md).write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
