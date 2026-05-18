"""Tests for build_batches.py — schema, ID format, status derivation."""
import json
from pathlib import Path

from build_batches import build_batches, derive_row, safe_bibkey


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_safe_bibkey_only_replaces_slash():
    assert safe_bibkey("Hooper:2024") == "Hooper:2024"
    assert safe_bibkey("Foo/Bar:2020") == "Foo_Bar:2020"


def test_derive_row_marks_missing_bib_entry(tmp_path):
    row = derive_row(0, {"bibkey": "Unknown", "paragraph": "p", "section_heading": "s", "line": 1},
                    bib_index={}, abstracts_dir=tmp_path)
    assert row["id"] == "c0"
    assert row["abstract_status"] == "missing_bib_entry"
    assert row["abstract"] is None


def test_derive_row_marks_no_bib_metadata(tmp_path):
    row = derive_row(1, {"bibkey": "Stub", "paragraph": "p", "section_heading": "s", "line": 2},
                    bib_index={"Stub": {}}, abstracts_dir=tmp_path)
    assert row["abstract_status"] == "no_bib_metadata"


def test_derive_row_uses_cache_ok(tmp_path):
    bib = {"K": {"title": "T", "arxiv_id": "1234.5678"}}
    cache = tmp_path / "K.json"
    _write(cache, {"bibkey": "K", "title": "T", "abstract": "An abstract",
                   "title_match": "ok", "source": "inspire_arxiv"})
    row = derive_row(0, {"bibkey": "K", "paragraph": "p", "section_heading": "s", "line": 1},
                    bib_index=bib, abstracts_dir=tmp_path)
    assert row["abstract_status"] == "ok"
    assert row["abstract"] == "An abstract"
    assert row["fetched_title"] == "T"


def test_derive_row_handles_not_found(tmp_path):
    bib = {"K": {"title": "T"}}
    _write(tmp_path / "K.json", {"bibkey": "K", "title": None, "abstract": None,
                                  "title_match": "not_found", "source": "not_found"})
    row = derive_row(0, {"bibkey": "K", "paragraph": "p", "section_heading": "s", "line": 1},
                    bib_index=bib, abstracts_dir=tmp_path)
    assert row["abstract_status"] == "not_found"


def test_derive_row_missing_cache_is_fetch_error(tmp_path):
    bib = {"K": {"title": "T"}}
    row = derive_row(0, {"bibkey": "K", "paragraph": "p", "section_heading": "s", "line": 1},
                    bib_index=bib, abstracts_dir=tmp_path)
    assert row["abstract_status"] == "fetch_error"


def test_build_batches_partitions_by_batch_size(tmp_path):
    citations = [{"bibkey": "K", "paragraph": "p", "section_heading": "s", "line": i}
                 for i in range(25)]
    bib = {"K": {"title": "T", "arxiv_id": "1"}}
    _write(tmp_path / "K.json", {"bibkey": "K", "title": "T", "abstract": "A",
                                  "title_match": "ok", "source": "inspire_arxiv"})
    batches = build_batches(citations, bib, tmp_path, batch_size=10)
    assert [len(b) for b in batches] == [10, 10, 5]
    # IDs are c-prefixed and globally indexed across batches
    flat_ids = [r["id"] for b in batches for r in b]
    assert flat_ids == [f"c{i}" for i in range(25)]
