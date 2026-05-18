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
