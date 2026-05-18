from collate_deep_report import merge_verdicts, render_deep_section, collate_deep

_ROWS = [
    # no_abstract — lives only in all_rows, not needing_review
    {"id": "c0", "bibkey": "BookA", "bib_title": "Book A", "line": 10,
     "paragraph": "p1", "section_heading": "S1",
     "score": None, "reason": "no_abstract", "source": "not_found"},
    {"id": "c1", "bibkey": "PaperB", "bib_title": "Paper B", "line": 20,
     "paragraph": "p2", "section_heading": "S1",
     "score": 3, "reason": "off-topic", "source": "inspire_arxiv"},
    {"id": "c2", "bibkey": "PaperC", "bib_title": "Paper C", "line": 30,
     "paragraph": "p3", "section_heading": "S1",
     "score": 5, "reason": "borderline", "source": "inspire_arxiv"},
    {"id": "c3", "bibkey": "PaperE", "bib_title": "Paper E", "line": 50,
     "paragraph": "p5", "section_heading": "S2",
     "score": 9, "reason": "perfect", "source": "inspire_arxiv"},
]

REPORT = {
    "tex_file": "sample.tex",
    "total_citations": 4,
    "average_score": 4.5,
    "scored_low": 2, "scored_borderline": 1, "scored_ok": 1,
    "unscored": {"no_abstract": 1, "title_mismatch": 0,
                 "missing_bib_entry": 0, "no_bib_metadata": 0,
                 "fetch_error": 0, "scoring_failed": 0},
    "title_match_issues": [],
    "all_rows": _ROWS,
    "needing_review": [r for r in _ROWS if r["id"] in ("c1", "c2")],
    "ok": [r for r in _ROWS if r["id"] == "c3"],
}

VERDICTS = [
    {"id": "c0", "deep_score": 9, "deep_verdict": "confirmed",
     "deep_reason": "Section 4.2 explicitly covers the claim.",
     "deep_source": "notebooklm",
     "deep_nlm_evidence": "Chapter 4: The energy loss rate is..."},
    {"id": "c1", "deep_score": 2, "deep_verdict": "mismatch",
     "deep_reason": "Paper addresses cross-sections, not decay kinematics.",
     "deep_source": "arxiv_pdf",
     "deep_nlm_evidence": None},
    {"id": "c2", "deep_score": 7, "deep_verdict": "confirmed",
     "deep_reason": "Section 2 covers this specific regime.",
     "deep_source": "arxiv_pdf",
     "deep_nlm_evidence": None},
]


def test_merge_adds_deep_fields_to_matching_entry():
    result = merge_verdicts(REPORT, VERDICTS)
    row = next(r for r in result["all_rows"] if r["id"] == "c1")
    assert row["deep_verdict"] == "mismatch"
    assert row["deep_score"] == 2
    assert row["deep_source"] == "arxiv_pdf"
    assert row["deep_nlm_evidence"] is None


def test_merge_nlm_evidence_populated():
    # c0 is a no_abstract entry: lives in all_rows but not needing_review
    result = merge_verdicts(REPORT, VERDICTS)
    row = next(r for r in result["all_rows"] if r["id"] == "c0")
    assert row["deep_verdict"] == "confirmed"
    assert row["deep_nlm_evidence"] == "Chapter 4: The energy loss rate is..."


def test_merge_unmatched_entry_gets_skipped():
    result = merge_verdicts(REPORT, VERDICTS)
    row = next(r for r in result["all_rows"] if r["id"] == "c3")
    assert row["deep_verdict"] == "skipped"
    assert row.get("deep_score") is None


def test_render_deep_section_has_all_subsections():
    augmented = merge_verdicts(REPORT, VERDICTS)
    md = render_deep_section(augmented)
    assert "## Deep-check verdicts" in md
    assert "### Mismatches" in md
    assert "### Confirmed" in md


def test_render_deep_section_summary_line():
    augmented = merge_verdicts(REPORT, VERDICTS)
    md = render_deep_section(augmented)
    assert "mismatch" in md.lower()
    assert "confirmed" in md.lower()


def test_render_mismatch_entry_listed():
    augmented = merge_verdicts(REPORT, VERDICTS)
    md = render_deep_section(augmented)
    assert "PaperB" in md
    assert "cross-sections" in md


def test_render_skipped_not_listed():
    augmented = merge_verdicts(REPORT, VERDICTS)
    md = render_deep_section(augmented)
    assert "PaperE" not in md


def test_render_nlm_evidence_shown():
    augmented = merge_verdicts(REPORT, VERDICTS)
    md = render_deep_section(augmented)
    assert "Chapter 4: The energy loss rate is" in md


def test_collate_deep_roundtrip(tmp_path):
    import json
    report_path = tmp_path / "report.json"
    verdicts_path = tmp_path / "verdicts.json"
    md_path = tmp_path / "report.md"
    md_path.write_text("# Existing report\n\nOriginal content.\n", encoding="utf-8")

    report_path.write_text(json.dumps(REPORT), encoding="utf-8")
    verdicts_path.write_text(json.dumps(VERDICTS), encoding="utf-8")

    collate_deep(str(report_path), str(verdicts_path), str(md_path))

    augmented = json.loads(report_path.read_text())
    row = next(r for r in augmented["needing_review"] if r["id"] == "c1")
    assert row["deep_verdict"] == "mismatch"

    md_content = md_path.read_text()
    assert "Original content." in md_content
    assert "## Deep-check verdicts" in md_content
