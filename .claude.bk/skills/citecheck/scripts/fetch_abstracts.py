"""Fetch paper abstracts from InspireHEP (preferred) and arXiv (fallback).

Resolution chain per bibkey:
  1. Inspire by arXiv ID
  2. Inspire by DOI
  3. Inspire by title (similarity >= 0.90)
  4. arXiv by arXiv ID
  5. arXiv by title (similarity >= 0.90)
First hit wins. Title validation runs on every successful fetch.
"""
from __future__ import annotations

import argparse
import re
import difflib
import json
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import urlopen, Request


class FetchError(Exception):
    """Raised when an HTTP/parse failure should be distinguished from 'not found'."""

_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\{?")
_BRACES_RE = re.compile(r"[{}]")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_title(s: str) -> str:
    s = s or ""
    s = _LATEX_CMD_RE.sub("", s)
    s = _BRACES_RE.sub("", s)
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip().lower()
    return s


def title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


INSPIRE_BASE = "https://inspirehep.net/api/literature"
INSPIRE_FIELDS = "titles,authors,abstracts,arxiv_eprints,dois"
USER_AGENT = "citecheck/0.1.0 (+https://github.com/aureamerio/citecheck)"


def _http_get_json(url: str, timeout: float = 15.0) -> dict:
    _polite_sleep(urlparse(url).netloc)
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise FetchError(str(e)) from e


def _normalize_inspire_hit(hit: dict) -> dict | None:
    md = hit.get("metadata", {})
    titles = md.get("titles") or []
    abstracts = md.get("abstracts") or []
    if not titles:
        return None
    arxiv = (md.get("arxiv_eprints") or [{}])[0].get("value")
    doi = (md.get("dois") or [{}])[0].get("value")
    authors = md.get("authors") or []
    return {
        "title": titles[0].get("title", "").strip(),
        "abstract": (abstracts[0].get("value") if abstracts else None),
        "arxiv_id": arxiv,
        "doi": doi,
        "inspire_id": hit.get("id"),
        "authors_short": _authors_short(authors),
    }


def _authors_short(authors: list[dict]) -> str | None:
    if not authors:
        return None
    first = authors[0].get("full_name", "").split(",")[0].strip()
    if len(authors) == 1:
        return first
    return f"{first} et al."


def query_inspire_arxiv(arxiv_id: str) -> dict | None:
    """Returns the hit dict, None if not found. Raises FetchError on network failure."""
    url = f"{INSPIRE_BASE}?q=arxiv:{quote_plus(arxiv_id)}&fields={INSPIRE_FIELDS}&size=1"
    data = _http_get_json(url)
    hits = (data.get("hits") or {}).get("hits") or []
    if not hits:
        return None
    return _normalize_inspire_hit(hits[0])


TITLE_MATCH_OK = 0.90


def query_inspire_doi(doi: str) -> dict | None:
    url = f"{INSPIRE_BASE}?q=doi:{quote_plus(doi)}&fields={INSPIRE_FIELDS}&size=1"
    data = _http_get_json(url)
    hits = (data.get("hits") or {}).get("hits") or []
    return _normalize_inspire_hit(hits[0]) if hits else None


def query_inspire_title(query_title: str, bib_title: str) -> dict | None:
    url = f"{INSPIRE_BASE}?q=title:{quote_plus(query_title)}&fields={INSPIRE_FIELDS}&size=1"
    data = _http_get_json(url)
    hits = (data.get("hits") or {}).get("hits") or []
    if not hits:
        return None
    hit = _normalize_inspire_hit(hits[0])
    if hit is None:
        return None
    if title_similarity(hit["title"], bib_title) < TITLE_MATCH_OK:
        return None
    return hit


ARXIV_BASE = "https://export.arxiv.org/api/query"
ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}


def _http_get_bytes(url: str, timeout: float = 15.0) -> bytes:
    _polite_sleep(urlparse(url).netloc)
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except OSError as e:
        raise FetchError(str(e)) from e


def _parse_arxiv_entry(xml_bytes: bytes) -> dict | None:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    entry = root.find("a:entry", ARXIV_NS)
    if entry is None:
        return None
    title_el = entry.find("a:title", ARXIV_NS)
    summary_el = entry.find("a:summary", ARXIV_NS)
    id_el = entry.find("a:id", ARXIV_NS)
    authors = entry.findall("a:author/a:name", ARXIV_NS)
    arxiv_id = None
    if id_el is not None and id_el.text:
        m = re.search(r"abs/([^v\s]+)(?:v\d+)?", id_el.text)
        if m:
            arxiv_id = m.group(1)
    return {
        "title": (title_el.text or "").strip() if title_el is not None else "",
        "abstract": (summary_el.text or "").strip() if summary_el is not None else None,
        "arxiv_id": arxiv_id,
        "doi": None,
        "inspire_id": None,
        "authors_short": _authors_short_plain([a.text for a in authors if a.text]),
    }


def _authors_short_plain(names: list[str]) -> str | None:
    if not names:
        return None
    first = names[0].split(",")[0].strip().split()[-1] if "," not in names[0] else names[0].split(",")[0].strip()
    if len(names) == 1:
        return first
    return f"{first} et al."


def query_arxiv_id(arxiv_id: str) -> dict | None:
    url = f"{ARXIV_BASE}?id_list={quote_plus(arxiv_id)}"
    data = _http_get_bytes(url)
    return _parse_arxiv_entry(data)


def query_arxiv_title(query_title: str, bib_title: str) -> dict | None:
    url = f"{ARXIV_BASE}?search_query=ti:{quote_plus(query_title)}&max_results=1"
    data = _http_get_bytes(url)
    hit = _parse_arxiv_entry(data)
    if hit is None:
        return None
    if title_similarity(hit["title"], bib_title) < TITLE_MATCH_OK:
        return None
    return hit


import datetime

TITLE_MATCH_FUZZY = 0.70


def _classify_title_match(sim: float) -> str:
    if sim >= TITLE_MATCH_OK:
        return "ok"
    if sim >= TITLE_MATCH_FUZZY:
        return "fuzzy"
    return "mismatch"


def _augment(rec: dict, *, bibkey: str, bib_title: str, source: str) -> dict:
    sim = title_similarity(rec.get("title", ""), bib_title) if bib_title else 1.0
    rec.update(
        {
            "bibkey": bibkey,
            "bib_title": bib_title,
            "fetched_title": rec.get("title"),
            "title_match": _classify_title_match(sim),
            "title_similarity": round(sim, 3),
            "source": source,
            "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
    )
    return rec


def _try(fn, *args, errors: list[str]):
    """Call a query helper, capturing FetchError so the caller can still try fallbacks."""
    try:
        return fn(*args)
    except FetchError as e:
        errors.append(f"{fn.__name__}: {e}")
        return None


def _empty_record(
    bibkey: str,
    bib_title: str,
    arxiv_id: str | None,
    doi: str | None,
    *,
    source: str,
    errors: list[str] | None = None,
) -> dict:
    rec = {
        "bibkey": bibkey,
        "title": None,
        "abstract": None,
        "arxiv_id": arxiv_id,
        "doi": doi,
        "inspire_id": None,
        "authors_short": None,
        "bib_title": bib_title,
        "fetched_title": None,
        "title_match": source,  # "not_found" or "fetch_error"
        "title_similarity": 0.0,
        "source": source,
        "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    if errors:
        rec["fetch_errors"] = errors
    return rec


def resolve(
    bibkey: str,
    meta: dict,
    *,
    use_arxiv_fallback: bool = True,
    cross_check: bool = False,
) -> dict:
    """Run the resolution chain. Returns the cache-file-shaped dict.

    Distinguishes ``not_found`` (every backend answered, nothing matched) from
    ``fetch_error`` (at least one backend raised before we could decide).
    """
    bib_title = meta.get("title") or ""
    arxiv_id = meta.get("arxiv_id")
    doi = meta.get("doi")
    errors: list[str] = []

    if arxiv_id:
        hit = _try(query_inspire_arxiv, arxiv_id, errors=errors)
        if hit:
            rec = _augment(hit, bibkey=bibkey, bib_title=bib_title, source="inspire_arxiv")
            if cross_check and rec["title_match"] == "mismatch":
                arxiv_hit = _try(query_arxiv_id, arxiv_id, errors=errors)
                if arxiv_hit and title_similarity(arxiv_hit["title"], bib_title) >= TITLE_MATCH_OK:
                    promoted = _augment(arxiv_hit, bibkey=bibkey, bib_title=bib_title, source="arxiv_xref")
                    promoted["cross_check_note"] = (
                        f"Inspire arxiv:{arxiv_id} returned mismatched title; "
                        f"arXiv API title matched bib title at sim={promoted['title_similarity']}."
                    )
                    return promoted
                rec["cross_check_note"] = "Inspire mismatch confirmed; arXiv did not produce a better match."
            return rec
    if doi:
        hit = _try(query_inspire_doi, doi, errors=errors)
        if hit:
            return _augment(hit, bibkey=bibkey, bib_title=bib_title, source="inspire_doi")
    if bib_title:
        hit = _try(query_inspire_title, bib_title, bib_title, errors=errors)
        if hit:
            return _augment(hit, bibkey=bibkey, bib_title=bib_title, source="inspire_title")

    if use_arxiv_fallback:
        if arxiv_id:
            hit = _try(query_arxiv_id, arxiv_id, errors=errors)
            if hit:
                return _augment(hit, bibkey=bibkey, bib_title=bib_title, source="arxiv_id")
        if bib_title:
            hit = _try(query_arxiv_title, bib_title, bib_title, errors=errors)
            if hit:
                return _augment(hit, bibkey=bibkey, bib_title=bib_title, source="arxiv_title")

    # Everything we tried either errored or returned no hit. If any backend
    # errored, the result is a transient fetch_error (re-fetch on next run);
    # otherwise it's a real not_found (sticky).
    source = "fetch_error" if errors else "not_found"
    return _empty_record(bibkey, bib_title, arxiv_id, doi, source=source, errors=errors)


def write_cache(cache_dir: Path, rec: dict) -> None:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    bibkey = rec["bibkey"]
    safe = bibkey.replace("/", "_")
    (cache_dir / f"{safe}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")


def read_cache(cache_dir: Path, bibkey: str) -> dict | None:
    safe = bibkey.replace("/", "_")
    p = Path(cache_dir) / f"{safe}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# Per-host token bucket so arXiv (≈ 1 req / 3 s) stays polite even when Inspire runs hot.
_HOST_LOCK = threading.Lock()
_HOST_NEXT: dict[str, float] = {}
_HOST_MIN_INTERVAL = {"export.arxiv.org": 3.0, "inspirehep.net": 0.1}


def _polite_sleep(host: str) -> None:
    interval = _HOST_MIN_INTERVAL.get(host, 0.1)
    with _HOST_LOCK:
        now = time.monotonic()
        next_ok = _HOST_NEXT.get(host, 0.0)
        wait = max(0.0, next_ok - now)
        _HOST_NEXT[host] = max(now, next_ok) + interval
    if wait > 0:
        time.sleep(wait)


def fetch_missing(
    missing: list[dict],
    cache_dir: Path,
    *,
    parallel: int = 8,
    use_arxiv_fallback: bool = True,
    cross_check: bool = False,
) -> None:
    """Resolve each missing entry and write its cache file."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    def _one(item: dict) -> None:
        rec = resolve(
            item["bibkey"],
            item,
            use_arxiv_fallback=use_arxiv_fallback,
            cross_check=cross_check,
        )
        write_cache(cache_dir, rec)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        list(pool.map(_one, missing))


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--missing", required=True, help="path to JSON list of {bibkey, title, arxiv_id, doi}")
    p.add_argument("--cache-dir", required=True)
    p.add_argument("--parallel", type=int, default=8)
    p.add_argument("--no-arxiv-fallback", action="store_true")
    p.add_argument("--cross-check", action="store_true")
    args = p.parse_args()
    missing = json.loads(Path(args.missing).read_text(encoding="utf-8"))
    fetch_missing(
        missing,
        Path(args.cache_dir),
        parallel=args.parallel,
        use_arxiv_fallback=not args.no_arxiv_fallback,
        cross_check=args.cross_check,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
