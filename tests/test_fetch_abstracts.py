import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from fetch_abstracts import normalize_title, title_similarity

FIXT = Path(__file__).parent / "fixtures"


def _mock_urlopen(return_bytes: bytes):
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = return_bytes
    cm.__exit__.return_value = False
    return cm


def test_normalize_strips_latex_and_punctuation():
    assert normalize_title("{\\textit{Foo}} bar: baz!") == "foo bar baz"


def test_similarity_high_for_close_titles():
    a = "CosmiXs: cosmic messenger spectra for indirect dark matter searches"
    b = "CosmiXs cosmic messenger spectra for indirect dark matter searches."
    assert title_similarity(a, b) >= 0.9


def test_similarity_low_for_different_titles():
    assert title_similarity("Quantum gravity in 11 dimensions",
                            "Bayesian inference for dark matter") < 0.5


def test_query_inspire_arxiv_returns_normalized_hit():
    from fetch_abstracts import query_inspire_arxiv
    payload = (FIXT / "inspire_arxiv.json").read_bytes()
    with patch("fetch_abstracts.urlopen", return_value=_mock_urlopen(payload)):
        hit = query_inspire_arxiv("2312.01153")
    assert hit is not None
    assert hit["title"].startswith("CosmiXs")
    assert hit["abstract"].startswith("We present")
    assert hit["arxiv_id"] == "2312.01153"
    assert hit["inspire_id"] == "2729450"


def test_query_inspire_doi():
    from fetch_abstracts import query_inspire_doi
    payload = (FIXT / "inspire_arxiv.json").read_bytes()
    with patch("fetch_abstracts.urlopen", return_value=_mock_urlopen(payload)):
        hit = query_inspire_doi("10.1088/1475-7516/2024/03/035")
    assert hit is not None
    assert hit["doi"] == "10.1088/1475-7516/2024/03/035"


def test_query_inspire_title_requires_high_similarity():
    from fetch_abstracts import query_inspire_title
    payload = (FIXT / "inspire_arxiv.json").read_bytes()
    bib_title = "CosmiXs cosmic messenger spectra for indirect dark matter searches"
    with patch("fetch_abstracts.urlopen", return_value=_mock_urlopen(payload)):
        ok = query_inspire_title(bib_title, bib_title)
    assert ok is not None

    with patch("fetch_abstracts.urlopen", return_value=_mock_urlopen(payload)):
        bad = query_inspire_title("Wholly different topic", "Wholly different topic")
    assert bad is None


def test_query_arxiv_id():
    from fetch_abstracts import query_arxiv_id
    payload = (FIXT / "arxiv_response.xml").read_bytes()
    with patch("fetch_abstracts.urlopen", return_value=_mock_urlopen(payload)):
        hit = query_arxiv_id("2312.01153")
    assert hit is not None
    assert hit["title"].startswith("CosmiXs")
    assert hit["abstract"].startswith("We present")
    assert hit["arxiv_id"] == "2312.01153"


def test_query_arxiv_title_requires_similarity():
    from fetch_abstracts import query_arxiv_title
    payload = (FIXT / "arxiv_response.xml").read_bytes()
    bib_title = "CosmiXs cosmic messenger spectra for indirect dark matter searches"
    with patch("fetch_abstracts.urlopen", return_value=_mock_urlopen(payload)):
        ok = query_arxiv_title(bib_title, bib_title)
    assert ok is not None
    with patch("fetch_abstracts.urlopen", return_value=_mock_urlopen(payload)):
        bad = query_arxiv_title("Totally unrelated paper", "Totally unrelated paper")
    assert bad is None


def test_resolve_uses_inspire_arxiv_first(monkeypatch):
    from fetch_abstracts import resolve
    inspire_payload = (FIXT / "inspire_arxiv.json").read_bytes()

    calls = []
    def fake_urlopen(req, timeout=15.0):
        calls.append(req.full_url)
        return _mock_urlopen(inspire_payload)

    with patch("fetch_abstracts.urlopen", side_effect=fake_urlopen):
        rec = resolve(
            "2024JCAP...03..035A",
            {
                "title": "CosmiXs: cosmic messenger spectra for indirect dark matter searches",
                "arxiv_id": "2312.01153",
                "doi": None,
            },
        )

    assert rec["source"] == "inspire_arxiv"
    assert rec["title_match"] == "ok"
    assert rec["abstract"].startswith("We present")
    assert "inspirehep.net" in calls[0]


def test_resolve_marks_mismatch_when_titles_differ():
    from fetch_abstracts import resolve
    inspire_payload = (FIXT / "inspire_arxiv.json").read_bytes()
    with patch("fetch_abstracts.urlopen", return_value=_mock_urlopen(inspire_payload)):
        rec = resolve(
            "Bogus2020",
            {"title": "An unrelated paper", "arxiv_id": "2312.01153", "doi": None},
        )
    assert rec["source"] == "inspire_arxiv"
    assert rec["title_match"] == "mismatch"
    assert rec["title_similarity"] < 0.7


def test_resolve_falls_back_to_arxiv_when_inspire_empty():
    from fetch_abstracts import resolve
    empty_inspire = b'{"hits": {"hits": [], "total": 0}}'
    arxiv_payload = (FIXT / "arxiv_response.xml").read_bytes()
    responses = [_mock_urlopen(empty_inspire), _mock_urlopen(empty_inspire),
                 _mock_urlopen(arxiv_payload)]
    with patch("fetch_abstracts.urlopen", side_effect=lambda *a, **k: responses.pop(0)):
        rec = resolve(
            "ML2020",
            {"title": "CosmiXs cosmic messenger spectra for indirect dark matter searches",
             "arxiv_id": "2312.01153", "doi": None},
        )
    assert rec["source"] == "arxiv_id"
    assert rec["abstract"].startswith("We present")


def test_resolve_returns_not_found_when_all_paths_fail():
    from fetch_abstracts import resolve
    empty_inspire = b'{"hits": {"hits": [], "total": 0}}'
    empty_arxiv = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    responses = [_mock_urlopen(empty_inspire)] * 3 + [_mock_urlopen(empty_arxiv)] * 2
    with patch("fetch_abstracts.urlopen", side_effect=lambda *a, **k: responses.pop(0)):
        rec = resolve("Missing", {"title": "Whatever", "arxiv_id": "0000.00000", "doi": None})
    assert rec["source"] == "not_found"
    assert rec["abstract"] is None


def test_cross_check_replaces_inspire_mismatch_with_arxiv():
    from fetch_abstracts import resolve

    inspire_payload = (FIXT / "inspire_arxiv.json").read_bytes()
    arxiv_payload = (FIXT / "arxiv_response.xml").read_bytes()
    seq = [_mock_urlopen(inspire_payload), _mock_urlopen(arxiv_payload)]

    with patch("fetch_abstracts.urlopen", side_effect=lambda *a, **k: seq.pop(0)):
        rec = resolve(
            "MaybeMismatched",
            {
                "title": "CosmiXs cosmic messenger spectra for indirect dark matter searches",
                "arxiv_id": "2312.01153",
                "doi": None,
            },
            cross_check=True,
        )
    assert rec["source"] in ("inspire_arxiv", "arxiv_xref")


def test_cross_check_promotes_arxiv_on_mismatch():
    """Force an Inspire mismatch, verify arxiv_xref is used."""
    from fetch_abstracts import resolve
    inspire_payload = (FIXT / "inspire_arxiv.json").read_bytes()
    arxiv_payload = (FIXT / "arxiv_response.xml").read_bytes()
    seq = [_mock_urlopen(inspire_payload), _mock_urlopen(arxiv_payload)]

    with patch("fetch_abstracts.urlopen", side_effect=lambda *a, **k: seq.pop(0)):
        rec = resolve(
            "MismatchKey",
            {
                "title": "Completely unrelated bib title here",
                "arxiv_id": "2312.01153",
                "doi": None,
            },
            cross_check=True,
        )
    assert rec["source"] == "inspire_arxiv"
    assert rec["title_match"] == "mismatch"
    assert "cross_check_note" in rec


def test_cache_round_trip(tmp_path):
    from fetch_abstracts import write_cache, read_cache
    rec = {"bibkey": "K", "title": "t", "abstract": "a", "source": "inspire_arxiv",
           "title_match": "ok", "title_similarity": 1.0}
    write_cache(tmp_path, rec)
    assert (tmp_path / "K.json").exists()
    assert read_cache(tmp_path, "K")["title"] == "t"
    assert read_cache(tmp_path, "Missing") is None


def test_fetch_missing_writes_one_file_per_key(tmp_path):
    from fetch_abstracts import fetch_missing
    inspire_payload = (FIXT / "inspire_arxiv.json").read_bytes()
    missing = [
        {"bibkey": "K1", "title": "CosmiXs: cosmic messenger spectra for indirect dark matter searches",
         "arxiv_id": "2312.01153", "doi": None},
        {"bibkey": "K2", "title": "CosmiXs: cosmic messenger spectra for indirect dark matter searches",
         "arxiv_id": "2312.01153", "doi": None},
    ]
    with patch("fetch_abstracts.urlopen", side_effect=lambda *a, **k: _mock_urlopen(inspire_payload)):
        fetch_missing(missing, tmp_path, parallel=2)
    assert (tmp_path / "K1.json").exists()
    assert (tmp_path / "K2.json").exists()
