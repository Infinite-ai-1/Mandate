"""Chunking, embedding and evidence ranking.

Pipeline for every raw document any ingest/*.py fetcher pulls down (a filing item, a
news article, an EPA/FDA record): register one Source for the whole document, split
its text into ~150-300 word Chunks, embed each chunk, and store both so
rank_evidence() can later find the chunks most relevant to a given rule.

    {"source_id": "...", "ticker": "...", "text": "...", "date": "YYYY-MM-DD"}   # Chunk

Call ingest_document() from a fetcher; nothing else needs to touch chunk storage
directly.

Embeddings: uses llm.embed() (Person 2's module) once it exists. Until then, falls
back to a small deterministic local embedding (hashed bag-of-words + bigrams) so
rank_evidence() is usable end-to-end today; swapping in the real embed() later
requires no change here, since _embed_text() tries the import first.
"""
import hashlib
import json
import math
import os
import re

import sources

HERE = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(HERE, "data", "processed")
CACHE_DIR = os.path.join(HERE, "data", "cache")
CHUNKS_DIR = os.path.join(PROCESSED_DIR, "chunks")
EMBED_CACHE_DIR = os.path.join(CACHE_DIR, "embeddings")

MIN_WORDS = 150
MAX_WORDS = 300
NEAR_DUP_THRESHOLD = 92  # rapidfuzz token_sort_ratio, 0-100; same-story-different-outlet news scores above this
_FALLBACK_DIMS = 256

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "any", "no",
    "not", "is", "are", "was", "were", "be", "been", "by", "that", "this", "it", "its",
    "we", "our", "from", "as", "at", "all", "than", "more", "may", "must", "shall",
    "should", "will", "do", "does", "have", "has", "had", "which", "who", "but", "if",
}


# --------------------------------------------------------------------------- chunking
def _split_paragraphs(text):
    paras = re.split(r"\n\s*\n|\r\n\s*\r\n", text.strip())
    paras = [p.strip() for p in paras if p.strip()]
    if len(paras) <= 1:
        # No blank-line paragraph breaks (common for a plain extracted filing item,
        # or a single-paragraph news story) -- fall back to sentence boundaries.
        paras = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
        paras = [p.strip() for p in paras if p.strip()]
    return paras


def _split_long_paragraph(paragraph, max_words):
    """A paragraph over max_words is split at sentence boundaries into pieces each
    under max_words, rather than cut mid-sentence."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces, current, count = [], [], 0
    for sentence in sentences:
        n = len(sentence.split())
        if current and count + n > max_words:
            pieces.append(" ".join(current))
            current, count = [], 0
        current.append(sentence)
        count += n
    if current:
        pieces.append(" ".join(current))
    return pieces or [paragraph]


def chunk_text(text, min_words=MIN_WORDS, max_words=MAX_WORDS):
    """Splits `text` into ~min_words-max_words pieces, merging short paragraphs
    forward and splitting long ones at sentence boundaries.

    A document shorter than min_words (a short news item) is returned as a single
    chunk rather than padded or dropped.
    """
    if not text or not text.strip():
        return []

    paragraphs = []
    for para in _split_paragraphs(text):
        if len(para.split()) > max_words * 1.3:
            paragraphs.extend(_split_long_paragraph(para, max_words))
        else:
            paragraphs.append(para)

    chunks, buffer, buffer_words = [], [], 0
    for para in paragraphs:
        n = len(para.split())
        if buffer and buffer_words + n > max_words:
            chunks.append(" ".join(buffer))
            buffer, buffer_words = [], 0
        buffer.append(para)
        buffer_words += n
        if buffer_words >= min_words:
            chunks.append(" ".join(buffer))
            buffer, buffer_words = [], 0
    if buffer:
        if chunks and buffer_words < min_words // 2:
            chunks[-1] = chunks[-1] + " " + " ".join(buffer)  # tiny tail, fold into previous
        else:
            chunks.append(" ".join(buffer))
    return chunks


# ------------------------------------------------------------------------ chunk store
def _chunks_path(ticker):
    return os.path.join(CHUNKS_DIR, f"{ticker.upper()}.json")


def load_chunks(ticker):
    """-> list[Chunk] for one ticker, [] if none stored yet."""
    path = _chunks_path(ticker)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _save_chunks(ticker, chunks):
    os.makedirs(CHUNKS_DIR, exist_ok=True)
    with open(_chunks_path(ticker), "w") as f:
        json.dump(chunks, f, indent=2)
        f.write("\n")


def _text_sim(a, b):
    try:
        from rapidfuzz import fuzz
        return fuzz.token_sort_ratio(a, b)
    except ImportError:
        return 100.0 if a.strip() == b.strip() else 0.0


def _is_near_duplicate(candidate_text, existing_chunks):
    """True if candidate_text is a near-identical restatement of a chunk already
    stored for this ticker (same wire story picked up by a different outlet)."""
    for chunk in existing_chunks:
        if _text_sim(candidate_text, chunk["text"]) >= NEAR_DUP_THRESHOLD:
            return True
    return False


def ingest_document(ticker, source, text):
    """Registers one Source for a whole document, chunks its text, deduplicates
    near-identical chunks against what's already stored, and upserts the result
    into data/processed/chunks/{ticker}.json.

    `source` is the dict sources.register() expects, minus "ticker" (kind, origin,
    title, date, url, section). Returns the list of newly added Chunks (may be
    empty if the whole document deduplicated away).
    """
    pieces = chunk_text(text)
    if not pieces:
        return []

    source_id = sources.register({**source, "ticker": ticker})
    existing = load_chunks(ticker)
    existing_keys = {(c["source_id"], c["text"]) for c in existing}

    new_chunks = []
    for piece in pieces:
        key = (source_id, piece)
        if key in existing_keys:
            continue  # exact re-ingest (e.g. refresh() re-running on unchanged text)
        if source.get("kind") == "news" and _is_near_duplicate(piece, existing):
            continue
        chunk = {"source_id": source_id, "ticker": ticker, "text": piece, "date": source.get("date")}
        new_chunks.append(chunk)
        existing.append(chunk)

    if new_chunks:
        _save_chunks(ticker, existing)
    return new_chunks


def replace_document_chunks(ticker, source, text):
    """Like ingest_document(), but first drops any chunks already stored for this
    exact source (same kind/origin/title/date/url/section) before re-adding --
    used by refresh() and search_new_topic(), which intentionally bypass the cache
    and want the new text to supersede the old, not just append alongside it.
    """
    source_id = sources.register({**source, "ticker": ticker})
    existing = [c for c in load_chunks(ticker) if c["source_id"] != source_id]
    _save_chunks(ticker, existing)
    return ingest_document(ticker, source, text)


# -------------------------------------------------------------------------- embedding
def _fallback_embed(text):
    """Deterministic hashed bag-of-words-and-bigrams embedding. Not semantically
    rich, but stable, dependency-free, and good enough for rank_evidence() to work
    end-to-end before llm.embed() exists.
    """
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS]
    vec = [0.0] * _FALLBACK_DIMS
    tokens = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    for tok in tokens:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % _FALLBACK_DIMS] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _embed_text(text):
    """Tries llm.embed() (Person 2's module) first; falls back to the local
    deterministic embedding if llm.py doesn't exist yet or raises."""
    try:
        import llm
        return llm.embed(text)
    except Exception:
        return _fallback_embed(text)


def _embed_cache_path(ticker):
    return os.path.join(EMBED_CACHE_DIR, f"{ticker.upper()}.json")


def _load_embed_cache(ticker):
    path = _embed_cache_path(ticker)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _save_embed_cache(ticker, cache):
    os.makedirs(EMBED_CACHE_DIR, exist_ok=True)
    with open(_embed_cache_path(ticker), "w") as f:
        json.dump(cache, f)


def embed_cached(ticker, text):
    """-> embedding vector for `text`, cached on disk per ticker keyed by a hash of
    the text so repeated runs don't re-embed unchanged chunks."""
    cache = _load_embed_cache(ticker)
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if key in cache:
        return cache[key]
    vec = _embed_text(text)
    cache[key] = vec
    _save_embed_cache(ticker, cache)
    return vec


def _cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a)) or 1.0
    db = math.sqrt(sum(y * y for y in b)) or 1.0
    return num / (da * db)


# ----------------------------------------------------------------------- evidence rank
def rank_evidence(rules, ticker, k=8):
    """-> {rule_id: [Chunk]}, the k chunks most relevant to each rule's text +
    keywords, by cosine similarity of their embeddings. Ties are broken in favour
    of filings over news (filings are the primary source for ethics verdicts; news
    corroborates).

    `rules` is the "rules" list from a Rules object: each needs at least "id" and
    "text", plus optionally "keywords".
    """
    chunks = load_chunks(ticker)
    if not chunks:
        return {rule["id"]: [] for rule in rules}

    chunk_vecs = [embed_cached(ticker, c["text"]) for c in chunks]
    src = sources.load_all()
    is_filing = [src.get(c["source_id"], {}).get("kind") == "filing" for c in chunks]

    out = {}
    for rule in rules:
        query = rule.get("text", "") + " " + " ".join(rule.get("keywords") or [])
        qvec = embed_cached(f"__rule__{ticker}", query) if query.strip() else None
        if qvec is None:
            out[rule["id"]] = []
            continue
        scored = [
            (_cosine(qvec, chunk_vecs[i]), is_filing[i], chunks[i]["date"], chunks[i])
            for i in range(len(chunks))
        ]
        scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        out[rule["id"]] = [row[3] for row in scored[:k]]
    return out
