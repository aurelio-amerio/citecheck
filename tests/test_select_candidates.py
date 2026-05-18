import json
from select_candidates import select

_ALL = [
    # no_abstract → nlm (book, not found online)
    {"id": "c0", "bibkey": "BookA", "bib_title": "Book A", "line": 10,
     "paragraph": "p1", "section_heading": "S1",
     "score": None, "reason": "no_abstract", "title_match": None, "source": "not_found"},
    # score=3, has arxiv → arxiv
    {"id": "c1", "bibkey": "PaperB", "bib_title": "Paper B", "line": 20,
     "paragraph": "p2", "section_heading": "S1",
     "score": 3, "reason": "off-topic", "title_match": "ok", "source": "inspire_arxiv"},
    # score=3, no arxiv → nlm
    {"id": "c2", "bibkey": "PaperC", "bib_title": "Paper C", "line": 30,
     "paragraph": "p3", "section_heading": "S1",
     "score": 3, "reason": "off-topic", "title_match": "ok", "source": "inspire_doi"},
    # score=5 + fuzzy title, has arxiv → arxiv
    {"id": "c3", "bibkey": "PaperD", "bib_title": "Paper D", "line": 40,
     "paragraph": "p4", "section_heading": "S1",
     "score": 5, "reason": "borderline", "title_match": "fuzzy", "source": "inspire_arxiv"},
    # score=9, ok title → skipped
    {"id": "c4", "bibkey": "PaperE", "bib_title": "Paper E", "line": 50,
     "paragraph": "p5", "section_heading": "S2",
     "score": 9, "reason": "perfect match", "title_match": "ok", "source": "inspire_arxiv"},
    # missing_bib_entry → skipped
    {"id": "c5", "bibkey": "PaperF", "bib_title": "Paper F", "line": 60,
     "paragraph": "p6", "section_heading": "S2",
     "score": None, "reason": "missing_bib_entry", "title_match": None, "source": None},
]

REPORT = {
    # no_abstract entries (c0) live only in all_rows, not in needing_review/ok
    "all_rows": _ALL,
    "needing_review": [r for r in _ALL if r["id"] in ("c1", "c2", "c3")],
    "ok": [r for r in _ALL if r["id"] in ("c4",)],
}

BIB_INDEX = {
    "BookA":  {"title": "Book A",  "arxiv_id": None,         "first_author": "Smith", "year": "2020", "doi": None},
    "PaperB": {"title": "Paper B", "arxiv_id": "2301.00001", "first_author": "Jones", "year": "2023", "doi": None},
    "PaperC": {"title": "Paper C", "arxiv_id": None,         "first_author": "Lee",   "year": "2022", "doi": None},
    "PaperD": {"title": "Paper D", "arxiv_id": "2301.00002", "first_author": "Kim",   "year": "2021", "doi": None},
    "PaperE": {"title": "Paper E", "arxiv_id": "2301.00003", "first_author": "Wang",  "year": "2019", "doi": None},
    "PaperF": {"title": "Paper F", "arxiv_id": None,         "first_author": None,    "year": None,   "doi": None},
}


def test_no_abstract_routes_to_nlm():
    result = select(REPORT, BIB_INDEX, threshold=6)
    nlm_ids = [e["id"] for e in result["nlm_queue"]]
    assert "c0" in nlm_ids


def test_low_score_with_arxiv_routes_to_arxiv():
    result = select(REPORT, BIB_INDEX, threshold=6)
    arxiv_ids = [e["id"] for e in result["arxiv_queue"]]
    assert "c1" in arxiv_ids


def test_low_score_without_arxiv_routes_to_nlm():
    result = select(REPORT, BIB_INDEX, threshold=6)
    nlm_ids = [e["id"] for e in result["nlm_queue"]]
    assert "c2" in nlm_ids


def test_fuzzy_title_with_arxiv_routes_to_arxiv():
    result = select(REPORT, BIB_INDEX, threshold=6)
    arxiv_ids = [e["id"] for e in result["arxiv_queue"]]
    assert "c3" in arxiv_ids


def test_ok_entry_is_skipped():
    result = select(REPORT, BIB_INDEX, threshold=6)
    skipped_ids = [e["id"] for e in result["skipped"]]
    assert "c4" in skipped_ids
    arxiv_ids = [e["id"] for e in result["arxiv_queue"]]
    nlm_ids = [e["id"] for e in result["nlm_queue"]]
    assert "c4" not in arxiv_ids
    assert "c4" not in nlm_ids


def test_missing_bib_entry_is_skipped():
    result = select(REPORT, BIB_INDEX, threshold=6)
    skipped_ids = [e["id"] for e in result["skipped"]]
    assert "c5" in skipped_ids


def test_bib_metadata_enriched_in_queue_entries():
    result = select(REPORT, BIB_INDEX, threshold=6)
    arxiv_entry = next(e for e in result["arxiv_queue"] if e["id"] == "c1")
    assert arxiv_entry["arxiv_id"] == "2301.00001"
    assert arxiv_entry["first_author"] == "Jones"
    assert arxiv_entry["year"] == "2023"


def test_configurable_threshold():
    result = select(REPORT, BIB_INDEX, threshold=4)
    # c1 score=3 ≤ 4 → arxiv; c3 score=5 > 4 but fuzzy → still arxiv
    arxiv_ids = [e["id"] for e in result["arxiv_queue"]]
    assert "c1" in arxiv_ids
    # c3: score=5 > 4 but fuzzy title+has arxiv → still arxiv
    assert "c3" in arxiv_ids


def test_threshold_excludes_borderline_score():
    # With threshold=4, score=5 > 4 and no title issue → skipped.
    row = {"id": "c0", "bibkey": "PaperB", "bib_title": "Paper B", "line": 5,
           "paragraph": "p", "section_heading": "S",
           "score": 5, "reason": "borderline", "title_match": "ok", "source": "inspire_arxiv"}
    report = {"all_rows": [row], "needing_review": [row], "ok": []}
    result = select(report, BIB_INDEX, threshold=4)
    assert len(result["arxiv_queue"]) == 0
    skipped_ids = [e["id"] for e in result["skipped"]]
    assert "c0" in skipped_ids
