from pathlib import Path
from collate_report import collate, render_markdown


def test_collate_merges_citations_scores_abstracts():
    citations = [
        {"bibkey": "OK", "line": 10, "tex_file": "x.tex",
         "paragraph": "p", "section_heading": "S"},
        {"bibkey": "MISMATCH", "line": 20, "tex_file": "x.tex",
         "paragraph": "p", "section_heading": "S"},
        {"bibkey": "NOABS", "line": 30, "tex_file": "x.tex",
         "paragraph": "p", "section_heading": "S"},
    ]
    abstracts = {
        "OK": {"title_match": "ok", "title": "T-OK", "bib_title": "T-OK", "title_similarity": 1.0},
        "MISMATCH": {"title_match": "mismatch", "title": "wrong", "bib_title": "right", "title_similarity": 0.1},
        "NOABS": {"source": "not_found", "title_match": "not_found"},
    }
    scores = [
        {"id": "c0", "bibkey": "OK", "score": 9, "reason": "matches"},
        {"id": "c1", "bibkey": "MISMATCH", "score": None, "reason": "title_mismatch"},
        {"id": "c2", "bibkey": "NOABS", "score": None, "reason": "no_abstract"},
    ]
    report = collate(citations, scores, abstracts, tex_path="x.tex")
    assert report["total_citations"] == 3
    assert report["scored_low"] == 0
    assert report["unscored"]["no_abstract"] == 1
    assert report["unscored"]["title_mismatch"] == 1
    assert len(report["title_match_issues"]) == 1


def test_render_markdown_has_three_sections():
    report = {
        "tex_file": "x.tex",
        "total_citations": 2,
        "average_score": 5.0,
        "scored_low": 1, "scored_borderline": 0, "scored_ok": 1,
        "unscored": {"no_abstract": 0, "title_mismatch": 0, "missing_bib_entry": 0,
                     "no_bib_metadata": 0, "fetch_error": 0, "scoring_failed": 0},
        "title_match_issues": [],
        "needing_review": [
            {"line": 10, "score": 2, "bibkey": "K", "section_heading": "S",
             "paragraph": "p", "abstract_title": "wrong", "reason": "off-topic"}
        ],
        "ok": [
            {"line": 20, "score": 9, "bibkey": "OK", "abstract_title": "right"}
        ],
        "all_rows": [],
    }
    md = render_markdown(report)
    assert "Citation review" in md
    assert "Citations needing review" in md
    assert "Citations OK" in md
    assert "score 2" in md


def test_collate_accepts_integer_ids():
    """Scorer agents sometimes echo integer ids; collate should still match them."""
    citations = [
        {"bibkey": "OK", "line": 1, "tex_file": "x.tex",
         "paragraph": "p", "section_heading": "S"},
        {"bibkey": "BAD", "line": 2, "tex_file": "x.tex",
         "paragraph": "p", "section_heading": "S"},
    ]
    abstracts = {"OK": {"title_match": "ok"}, "BAD": {"title_match": "ok"}}
    scores = [
        {"id": 0, "bibkey": "OK", "score": 9, "reason": "matches"},
        {"id": "1", "bibkey": "BAD", "score": 3, "reason": "off-topic"},
    ]
    report = collate(citations, scores, abstracts, tex_path="x.tex")
    assert report["scored_ok"] == 1
    assert report["scored_low"] == 1
    assert sum(report["unscored"].values()) == 0


def test_collate_falls_back_to_pipeline_status_for_unscored():
    """When the scorer wrote a free-text reason for a not_found row,
    the unscored tally should still classify it as no_abstract."""
    citations = [
        {"bibkey": "NF", "line": 1, "tex_file": "x.tex",
         "paragraph": "p", "section_heading": "S"},
    ]
    abstracts = {"NF": {"source": "not_found", "title_match": "not_found"}}
    scores = [
        {"id": "c0", "bibkey": "NF", "score": None,
         "reason": "Abstract not found for this reference."},
    ]
    report = collate(citations, scores, abstracts, tex_path="x.tex")
    assert report["unscored"]["no_abstract"] == 1
    assert report["unscored"]["scoring_failed"] == 0
