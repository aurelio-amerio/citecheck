import json
from pathlib import Path
import pytest
from print_summary import summarize


def test_summarize_basic(tmp_path):
    report = {
        "total_citations": 10,
        "scored_low": 2,
        "scored_borderline": 1,
        "title_match_issues": ["A", "B"],
    }
    report_path = tmp_path / "out.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    line = summarize(report_path)
    assert "10 citations" in line
    assert "3 needing review" in line
    assert "2 title-match issues" in line
    assert "out.md" in line


def test_summarize_zero_issues(tmp_path):
    report = {
        "total_citations": 5,
        "scored_low": 0,
        "scored_borderline": 0,
        "title_match_issues": [],
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    line = summarize(report_path)
    assert "5 citations" in line
    assert "0 needing review" in line
    assert "0 title-match issues" in line
    assert "report.md" in line
