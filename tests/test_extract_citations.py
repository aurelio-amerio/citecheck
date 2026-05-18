from pathlib import Path
from extract_citations import find_citations

FIXTURE = Path(__file__).parent / "fixtures" / "sample.tex"


def test_finds_single_key_citations():
    text = FIXTURE.read_text(encoding="utf-8")
    cites = find_citations(text)
    bibkeys = [c["bibkey"] for c in cites]
    assert "2024JCAP...03..035A" in bibkeys
    assert "NoArxiv2020" in bibkeys
    # Single-key citations get one entry each.
    assert bibkeys.count("2024JCAP...03..035A") == 1


def test_multi_key_cite_expands_to_one_entry_per_key():
    text = FIXTURE.read_text(encoding="utf-8")
    cites = find_citations(text)
    bibkeys = [c["bibkey"] for c in cites]
    assert "StubKey" in bibkeys
    assert "OtherKey" in bibkeys
    # Both keys share the same line.
    line_stub = next(c["line"] for c in cites if c["bibkey"] == "StubKey")
    line_other = next(c["line"] for c in cites if c["bibkey"] == "OtherKey")
    assert line_stub == line_other


def test_commented_citations_are_ignored():
    text = FIXTURE.read_text(encoding="utf-8")
    cites = find_citations(text)
    bibkeys = [c["bibkey"] for c in cites]
    assert "ShouldBeIgnored" not in bibkeys


from extract_citations import find_paragraph, find_section_heading, extract


def test_find_paragraph_returns_enclosing_block():
    text = FIXTURE.read_text(encoding="utf-8")
    # Locate the line containing "2024JCAP".
    line = next(i for i, ln in enumerate(text.splitlines(), start=1)
                if "2024JCAP" in ln)
    para = find_paragraph(text, line)
    assert "likelihood function" in para
    assert "Some other paragraph" not in para
    assert len(para) <= 600


def test_find_section_heading_returns_nearest_preceding():
    text = FIXTURE.read_text(encoding="utf-8")
    line = next(i for i, ln in enumerate(text.splitlines(), start=1)
                if "2024JCAP" in ln)
    heading = find_section_heading(text, line)
    assert "Bayesian methods" in heading  # nearest \subsection wins over \section


def test_extract_full_pipeline(tmp_path):
    tex = tmp_path / "s.tex"
    tex.write_text(FIXTURE.read_text())
    items = extract(tex)
    assert all({"bibkey", "line", "tex_file", "paragraph", "section_heading"} <= set(it) for it in items)
    assert items[0]["tex_file"].endswith("s.tex")
