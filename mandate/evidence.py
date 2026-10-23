"""Chunking, embeddings, retrieval and source IDs for the evidence the agents may quote."""
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np

from . import config as C
from .llm import embed
from .schemas import Chunk, Rule
from .sources.edgar import EDGAR_DIR
from .sources.news import NEWS_DIR

EMB_DIR = C.CACHE_DIR / "emb"
CHUNK_CHARS, OVERLAP, MAX_FILING_CHUNKS = 1500, 200, 250


def _split(text: str) -> list[str]:
    step = CHUNK_CHARS - OVERLAP
    return [text[i:i + CHUNK_CHARS] for i in range(0, max(len(text) - OVERLAP, 1), step)]


def build_chunks(ticker: str) -> list[Chunk]:
    """Filing chunks (capped at 250, evenly thinned) then one chunk per news item."""
    chunks: list[Chunk] = []
    fpath = EDGAR_DIR / f"{ticker}.json"
    if fpath.exists():
        f = json.loads(fpath.read_text(encoding="utf-8"))
        tag = "10K" if f["form"] == "10-K" else "20F"
        n = 0
        for section, text in f["sections"].items():
            for piece in _split(text):
                chunks.append(Chunk(source_id=f"{ticker}-{tag}-c{n:04d}", ticker=ticker, kind="filing",
                                    section=section, url=f["url"], date=f["filing_date"], text=piece))
                n += 1
        if len(chunks) > MAX_FILING_CHUNKS:     # ids stay stable; thin evenly so every section stays covered
            keep = np.linspace(0, len(chunks) - 1, MAX_FILING_CHUNKS).round().astype(int)
            chunks = [chunks[i] for i in sorted(set(keep))]
    npath = NEWS_DIR / f"{ticker}.json"
    if npath.exists():
        for i, a in enumerate(json.loads(npath.read_text(encoding="utf-8"))):
            day = datetime.fromtimestamp(a.get("datetime") or 0, tz=timezone.utc).date().isoformat()
            text = f"{a.get('headline') or ''}. {a.get('summary') or ''}".strip()
            chunks.append(Chunk(source_id=f"{ticker}-NEWS-{i:03d}", ticker=ticker, kind="news",
                                section="News", url=a.get("url") or "", date=day, text=text))
    # Ingestion branch evidence uses registry IDs. Preserve those IDs and provenance.
    path = C.ROOT / "data" / "processed" / "chunks" / f"{ticker}.json"
    if path.exists():
        import sources
        for item in json.loads(path.read_text(encoding="utf-8")):
            source = sources.get(item["source_id"]) or {}
            chunks.append(Chunk(**{**item, "kind": source.get("kind", "filing"),
                                  "url": source.get("url") or "", "section": source.get("section") or "",
                                  "date": item.get("date") or source.get("date") or ""}))
    return list({c.source_id: c for c in chunks}.values())


def save_chunks(ticker: str) -> list[Chunk]:
    """Write chunk metadata only, so quotes can be verified even without embeddings."""
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    chunks = build_chunks(ticker)
    (EMB_DIR / f"{ticker}.json").write_text(json.dumps([c.model_dump() for c in chunks]), encoding="utf-8")
    _load.cache_clear()
    return chunks


def build_index(ticker: str, force: bool = False) -> int:
    """Chunk, save metadata, embed (batches of 64), save vectors. Returns the chunk count."""
    meta, vec = EMB_DIR / f"{ticker}.json", EMB_DIR / f"{ticker}.npy"
    if vec.exists() and meta.exists() and not force:
        return len(json.loads(meta.read_text(encoding="utf-8")))
    chunks = save_chunks(ticker)
    if chunks:
        np.save(vec, np.array(embed([c.text for c in chunks]), dtype=np.float32))
    _load.cache_clear()
    return len(chunks)


@lru_cache(maxsize=64)
def _load(ticker: str) -> tuple[list[Chunk], np.ndarray | None]:
    meta, vec = EMB_DIR / f"{ticker}.json", EMB_DIR / f"{ticker}.npy"
    if not meta.exists():
        return build_chunks(ticker), None
    chunks = [Chunk(**c) for c in json.loads(meta.read_text(encoding="utf-8"))]
    return chunks, (np.load(vec) if vec.exists() else None)


def get_chunk(source_id: str) -> Chunk | None:
    """Used by verify.py. Source IDs start with the ticker."""
    import sources
    source = sources.get(source_id)
    ticker = source["ticker"] if source else source_id.split("-")[0]
    chunks, _ = _load(ticker)
    return next((c for c in chunks if c.source_id == source_id), None)


_qlock = threading.Lock()   # retrieval runs in worker threads: one writer at a time for the query cache


def _query_vec(query: str) -> np.ndarray:
    """Embed a rule query once; later calls (and DEMO_MODE) read cache/emb/_queries.json."""
    path = EMB_DIR / "_queries.json"
    key = hashlib.sha256(query.encode()).hexdigest()
    with _qlock:
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if key not in cache:
            cache[key] = embed([query])[0]
            EMB_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(cache), encoding="utf-8")
            os.replace(tmp, path)       # readers never see a half-written file
    return np.array(cache[key], dtype=np.float32)


def retrieve_text(ticker: str, query: str, keywords: list[str] | None = None, k: int = C.TOP_K_PER_RULE) -> list[Chunk]:
    """Cosine top-k, plus up to 2 more chunks with keyword hits. Deduplicated."""
    chunks, vecs = _load(ticker)
    if not chunks:
        return []
    picked: list[int] = []
    if vecs is not None:
        q = _query_vec(query)
        sims = vecs @ q / (np.linalg.norm(vecs, axis=1) * np.linalg.norm(q) + 1e-9)
        picked = [int(i) for i in np.argsort(-sims)[:k]]
    kws = [w.lower() for w in (keywords or []) if w]
    hits = sorted(((sum(w in c.text.lower() for w in kws), i) for i, c in enumerate(chunks) if i not in picked),
                  reverse=True)
    picked += [i for score, i in hits if score > 0][:k if vecs is None else 2]
    if not picked:
        picked = list(range(min(k, len(chunks))))
    return [chunks[i] for i in picked]


def retrieve(ticker: str, rule: Rule, k: int = C.TOP_K_PER_RULE) -> list[Chunk]:
    return retrieve_text(ticker, rule.text + " " + " ".join(rule.keywords), rule.keywords, k)


def format_chunks(chunks: list[Chunk]) -> str:
    return "\n".join(f'<chunk id="{c.source_id}">{c.text}</chunk>' for c in chunks) or "(no evidence found)"
