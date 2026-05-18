from pathlib import Path
from parse_bib import parse_bib
import json
import os

FIXTURE = Path(__file__).parent / "fixtures" / "sample.bib"


def test_parse_single_entry():
    index = parse_bib(FIXTURE)
    assert "2024JCAP...03..035A" in index
    entry = index["2024JCAP...03..035A"]
    assert entry["title"] == "CosmiXs: cosmic messenger spectra for indirect dark matter searches"
    assert entry["arxiv_id"] == "2312.01153"
    assert entry["doi"] == "10.1088/1475-7516/2024/03/035"
    assert entry["year"] == "2024"
    assert entry["first_author"] == "Arina, Chiara"


def test_parse_multiple_entries():
    index = parse_bib(FIXTURE)
    assert len(index) == 3
    assert "NoArxiv2020" in index
    assert "StubKey" in index


def test_missing_fields_are_none():
    index = parse_bib(FIXTURE)
    assert index["NoArxiv2020"]["arxiv_id"] is None
    assert index["StubKey"]["doi"] is None
    assert index["StubKey"]["first_author"] is None


def test_load_or_build_index_uses_cache(tmp_path):
    from parse_bib import load_or_build_index
    bib = tmp_path / "test.bib"
    bib.write_text(FIXTURE.read_text())
    cache = tmp_path / "bib_index.json"

    # First call: builds and writes cache.
    idx1 = load_or_build_index(bib, cache)
    assert cache.exists()
    assert "2024JCAP...03..035A" in idx1

    # Corrupt the bib but keep mtime older than cache: cache should be returned.
    cache_mtime = cache.stat().st_mtime
    bib.write_text("@article{NEW, title={x}}")
    os.utime(bib, (cache_mtime - 10, cache_mtime - 10))
    idx2 = load_or_build_index(bib, cache)
    assert "NEW" not in idx2  # served from cache

    # Touch bib forward: cache should rebuild.
    os.utime(bib, (cache_mtime + 10, cache_mtime + 10))
    idx3 = load_or_build_index(bib, cache)
    assert "NEW" in idx3
