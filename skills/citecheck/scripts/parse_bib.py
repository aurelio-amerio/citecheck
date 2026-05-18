"""Parse a BibTeX file into a bibkey → metadata dict.

Only extracts the fields citecheck needs: title, eprint (arXiv), doi, year,
first author. Uses regex; no external dependencies.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
FIELD_RE = re.compile(
    r"(\w+)\s*=\s*(?:"
    r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}|'  # {value with possible nested braces}
    r'"([^"]*)"'                             # or "quoted value"
    r"|([0-9]+)"                             # or bare number
    r")",
    re.IGNORECASE
)


def _split_entries(text: str) -> list[tuple[str, str]]:
    """Return [(bibkey, body), ...] by scanning balanced braces from @TYPE{key,..}."""
    out: list[tuple[str, str]] = []
    i = 0
    while True:
        m = ENTRY_RE.search(text, i)
        if not m:
            break
        bibkey = m.group(1)
        depth = 1
        j = text.find("{", m.start())
        k = j + 1
        while k < len(text) and depth > 0:
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
            k += 1
        out.append((bibkey, text[j + 1 : k - 1]))
        i = k
    return out


def _strip_braces(s: str) -> str:
    return re.sub(r"[{}]", "", s).strip()


def _first_author(raw: str) -> str | None:
    raw = _strip_braces(raw).strip()
    if not raw:
        return None
    return raw.split(" and ")[0].strip()


def parse_bib(bib_path: Path) -> dict[str, dict]:
    text = Path(bib_path).read_text(encoding="utf-8", errors="replace")
    index: dict[str, dict] = {}
    for bibkey, body in _split_entries(text):
        # Process matches: (key, braced_value, quoted_value, bare_number)
        fields = {}
        for match in FIELD_RE.finditer(body):
            key = match.group(1).lower()
            value = match.group(2) or match.group(3) or match.group(4) or ""
            fields[key] = value
        index[bibkey] = {
            "title": _strip_braces(fields.get("title", "")),
            "arxiv_id": _strip_braces(fields.get("eprint", "")) or None,
            "doi": _strip_braces(fields.get("doi", "")) or None,
            "year": _strip_braces(fields.get("year", "")) or None,
            "first_author": _first_author(fields.get("author", "")) or None,
        }
    return index


def load_or_build_index(bib_path: Path, cache_path: Path) -> dict[str, dict]:
    bib_path = Path(bib_path)
    cache_path = Path(cache_path)
    if cache_path.exists() and cache_path.stat().st_mtime >= bib_path.stat().st_mtime:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    index = parse_bib(bib_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: parse_bib.py <bib_path> <cache_path>", file=sys.stderr)
        sys.exit(2)
    load_or_build_index(Path(sys.argv[1]), Path(sys.argv[2]))
