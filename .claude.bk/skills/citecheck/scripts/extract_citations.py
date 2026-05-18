"""Extract \\cite references from a LaTeX file with paragraph + section context.

Only handles the bare \\cite{...} command (incl. tilde-prefixed ~\\cite{...} and
multi-key \\cite{a,b,c}). Comments are stripped before scanning.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Match an unescaped '%' (not preceded by a backslash) and drop to EOL.
COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")

CITE_RE = re.compile(r"\\cite\s*\{([^}]+)\}")


def strip_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def find_citations(text: str) -> list[dict]:
    """Return [{bibkey, line}, ...] for every \\cite key in text.

    Comments (unescaped %...) are removed before scanning, but line numbers are
    preserved (newlines are kept).
    """
    text = strip_comments(text)
    out: list[dict] = []
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def line_of(pos: int) -> int:
        import bisect
        return bisect.bisect_right(line_starts, pos)

    for m in CITE_RE.finditer(text):
        line = line_of(m.start())
        for raw_key in m.group(1).split(","):
            key = raw_key.strip()
            if key:
                out.append({"bibkey": key, "line": line})
    return out


SECTION_RE = re.compile(r"\\(section|subsection|subsubsection|paragraph)\s*\{([^}]+)\}")
PARAGRAPH_CAP = 600


def find_paragraph(text: str, line: int) -> str:
    """Return the enclosing non-blank block around `line`, capped at PARAGRAPH_CAP.

    A paragraph boundary is a blank line or a sectioning command.
    """
    lines = text.splitlines()
    idx = line - 1  # 0-indexed
    # Walk up to the start of the paragraph.
    start = idx
    while start > 0:
        prev = lines[start - 1].strip()
        if prev == "" or SECTION_RE.match(prev):
            break
        start -= 1
    # Walk down to the end.
    end = idx
    while end < len(lines) - 1:
        nxt = lines[end + 1].strip()
        if nxt == "" or SECTION_RE.match(nxt):
            break
        end += 1
    para = " ".join(line.strip() for line in lines[start : end + 1] if line.strip())
    if len(para) > PARAGRAPH_CAP:
        para = para[:PARAGRAPH_CAP] + "..."
    return para


def find_section_heading(text: str, line: int) -> str:
    """Return the nearest preceding sectioning command's title, or ''.

    Deepest (\\subsubsection) preferred when multiple precede the line.
    """
    lines = text.splitlines()[: line]
    best = ""
    for ln in lines:
        m = SECTION_RE.match(ln.strip())
        if m:
            best = m.group(2).strip()
    return best


def extract(tex_path: Path) -> list[dict]:
    """Full pipeline: read .tex, return list of citation records."""
    tex_path = Path(tex_path)
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    raw = find_citations(text)
    out: list[dict] = []
    for entry in raw:
        out.append(
            {
                "bibkey": entry["bibkey"],
                "line": entry["line"],
                "tex_file": str(tex_path),
                "paragraph": find_paragraph(text, entry["line"]),
                "section_heading": find_section_heading(text, entry["line"]),
            }
        )
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: extract_citations.py <tex_path> <output_json>", file=sys.stderr)
        sys.exit(2)
    items = extract(Path(sys.argv[1]))
    Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
    Path(sys.argv[2]).write_text(json.dumps(items, indent=2), encoding="utf-8")
