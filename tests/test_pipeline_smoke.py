"""End-to-end pipeline smoke test (no model in the loop)."""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "skills" / "citecheck" / "scripts"
FIXT = Path(__file__).parent / "fixtures"


def _mock_urlopen(b):
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = b
    cm.__exit__.return_value = False
    return cm


def test_full_pipeline_without_model(tmp_path, monkeypatch):
    # Stage fixture inputs.
    bib = tmp_path / "bibliography.bib"
    bib.write_text((FIXT / "sample.bib").read_text())
    tex = tmp_path / "sec.tex"
    tex.write_text((FIXT / "sample.tex").read_text())
    cache_dir = tmp_path / ".citecache" / "abstracts"
    tmp_dir = tmp_path / ".citecheck" / ".tmp"
    tmp_dir.mkdir(parents=True)

    # Step 1: parse_bib.
    subprocess.run(
        [sys.executable, str(SCRIPTS / "parse_bib.py"),
         str(bib), str(tmp_dir / "bib_index.json")],
        check=True,
    )

    # Step 2: extract_citations.
    subprocess.run(
        [sys.executable, str(SCRIPTS / "extract_citations.py"),
         str(tex), str(tmp_dir / "citations.json")],
        check=True,
    )

    # Step 3: build missing keys list (mirrors what SKILL.md does inline).
    bib_index = json.loads((tmp_dir / "bib_index.json").read_text())
    citations = json.loads((tmp_dir / "citations.json").read_text())
    missing = []
    seen = set()
    for c in citations:
        k = c["bibkey"]
        if k in seen:
            continue
        seen.add(k)
        meta = bib_index.get(k)
        if not meta:
            continue
        if not (meta.get("title") or meta.get("arxiv_id") or meta.get("doi")):
            continue
        missing.append({"bibkey": k, "title": meta.get("title"),
                        "arxiv_id": meta.get("arxiv_id"), "doi": meta.get("doi")})
    (tmp_dir / "missing.json").write_text(json.dumps(missing))

    # Step 4: fetch_abstracts (HTTP mocked).
    sys.path.insert(0, str(SCRIPTS))
    import fetch_abstracts as fa
    inspire = (FIXT / "inspire_arxiv.json").read_bytes()
    with patch.object(fa, "urlopen", side_effect=lambda *a, **k: _mock_urlopen(inspire)):
        fa.fetch_missing(missing, cache_dir, parallel=2)

    assert (cache_dir / "2024JCAP...03..035A.json").exists()

    # Step 5: stub scorer outputs.
    scores = [{"id": f"c{i}", "bibkey": c["bibkey"], "score": 8, "reason": "ok"}
              for i, c in enumerate(citations)]
    (tmp_dir / "batch_0_output.json").write_text(json.dumps(scores))

    # Step 6: collate.
    out_md = tmp_path / ".citecheck" / "sec.md"
    out_json = tmp_path / ".citecheck" / "sec.json"
    subprocess.run(
        [sys.executable, str(SCRIPTS / "collate_report.py"),
         "--citations", str(tmp_dir / "citations.json"),
         "--scores-dir", str(tmp_dir),
         "--abstracts-dir", str(cache_dir),
         "--tex-path", str(tex),
         "--output-md", str(out_md),
         "--output-json", str(out_json)],
        check=True,
    )
    assert out_md.exists()
    assert "Citation review" in out_md.read_text()
    assert out_json.exists()
