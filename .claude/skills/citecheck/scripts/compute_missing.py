"""Compute the list of bibkeys whose abstracts must be (re-)fetched.

Reads citations + bib index + the abstract cache, and writes a JSON list of
``{bibkey, title, arxiv_id, doi}`` entries that still need to be resolved.

Skip rules mirror SKILL.md step 4 exactly:
  - bibkey not in bib index           → skip (will be marked missing_bib_entry later)
  - bib entry has no title/arxiv/doi  → skip (will be marked no_bib_metadata)
  - cache hit with usable source      → skip
      * source == "fetch_error"       → always re-fetch
      * source == "not_found"         → re-fetch only with --refresh-missing
      * any other source              → re-fetch only with --refresh
  - cache miss                        → fetch
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cache_hit_usable(cached: dict, *, refresh: bool, refresh_missing: bool) -> bool:
    """True iff the cached record should be reused (no re-fetch needed)."""
    src = cached.get("source")
    if src == "fetch_error":
        return False
    if src == "not_found":
        return not refresh_missing
    return not refresh


def compute_missing(
    citations: list[dict],
    bib_index: dict,
    cache_dir: Path,
    *,
    refresh: bool = False,
    refresh_missing: bool = False,
) -> list[dict]:
    cache_dir = Path(cache_dir)
    seen: set[str] = set()
    missing: list[dict] = []

    for cit in citations:
        bibkey = cit.get("bibkey")
        if not bibkey or bibkey in seen:
            continue
        seen.add(bibkey)

        entry = bib_index.get(bibkey)
        if entry is None:
            continue
        title = entry.get("title")
        arxiv_id = entry.get("arxiv_id")
        doi = entry.get("doi")
        if not (title or arxiv_id or doi):
            continue

        safe = bibkey.replace("/", "_") + ".json"
        cache_path = cache_dir / safe
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cached = None
            if cached and _cache_hit_usable(
                cached, refresh=refresh, refresh_missing=refresh_missing
            ):
                continue

        missing.append(
            {"bibkey": bibkey, "title": title, "arxiv_id": arxiv_id, "doi": doi}
        )

    return missing


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--citations", required=True)
    p.add_argument("--bib-index", required=True)
    p.add_argument("--cache-dir", required=True)
    p.add_argument("--out", required=True, help="output JSON path for missing_keys list")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--refresh-missing", action="store_true")
    args = p.parse_args()

    citations = json.loads(Path(args.citations).read_text(encoding="utf-8"))
    bib_index = json.loads(Path(args.bib_index).read_text(encoding="utf-8"))
    missing = compute_missing(
        citations,
        bib_index,
        Path(args.cache_dir),
        refresh=args.refresh,
        refresh_missing=args.refresh_missing,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(missing, indent=2), encoding="utf-8")
    # Counts for the calling skill (no need to re-scan).
    print(f"unique_keys={len(set(c['bibkey'] for c in citations))} missing={len(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
