"""Azure OpenAI wrapper: cached, validated JSON calls, embeddings, retry, semaphore, run log."""
import asyncio
import hashlib
import json
import os
import re
import threading
import time
import weakref
from collections import defaultdict
from functools import lru_cache
from typing import Optional, Type, TypeVar

import openai
from openai import AsyncAzureOpenAI, AsyncOpenAI, AzureOpenAI, OpenAI
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from . import config as C

T = TypeVar("T", bound=BaseModel)
_log_lock = threading.Lock()
_dropped: dict[str, set] = defaultdict(set)   # params a deployment rejected: temperature, response_format


class DemoModeCacheMiss(RuntimeError):
    pass


# ---------- clients ----------
def _client_args() -> tuple[type, type, dict]:
    if not C.ENDPOINT or not C.API_KEY:
        raise RuntimeError("Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY in .env")
    common = dict(api_key=C.API_KEY, max_retries=0, timeout=120)   # tenacity does the retrying
    if "/openai/v1" in C.ENDPOINT:
        return OpenAI, AsyncOpenAI, dict(base_url=C.ENDPOINT, **common)
    return AzureOpenAI, AsyncAzureOpenAI, dict(azure_endpoint=C.ENDPOINT, api_version=C.API_VERSION, **common)


@lru_cache(maxsize=1)
def get_client():
    sync_cls, _, kw = _client_args()
    return sync_cls(**kw)


# async client and semaphore are per event loop, so asyncio.run() called twice (e.g. Streamlit) still works
_aclients: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_sems: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def get_aclient():
    loop = asyncio.get_running_loop()
    if loop not in _aclients:
        _, async_cls, kw = _client_args()
        _aclients[loop] = async_cls(**kw)
    return _aclients[loop]


def _sem() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _sems:
        _sems[loop] = asyncio.Semaphore(C.MAX_CONCURRENCY)
    return _sems[loop]


# ---------- retry, params ----------
def _transient(e: BaseException) -> bool:
    if isinstance(e, (openai.RateLimitError, openai.APIConnectionError)):   # includes timeouts
        return True
    return isinstance(e, openai.APIStatusError) and e.status_code >= 500


_retry = retry(retry=retry_if_exception(_transient), stop=stop_after_attempt(4),
               wait=wait_exponential(multiplier=2, min=2, max=30), reraise=True)


def _bad_param(e: BaseException, model: str) -> bool:
    """True if the API rejected temperature or response_format; we remember it and retry without."""
    if not isinstance(e, openai.BadRequestError):
        return False
    msg = str(e).lower()
    for p, hints in (("temperature", ("temperature",)), ("response_format", ("response_format", "json_object"))):
        if p not in _dropped[model] and any(h in msg for h in hints):
            _dropped[model].add(p)
            return True
    return False


def _kwargs(model: str, system: str, user: str, max_tokens: int) -> dict:
    reasoning = model in C.REASONING_MODELS
    json_mode = "response_format" not in _dropped[model]
    if not json_mode:
        system += "\nReturn ONLY a JSON object. No code fences, no commentary."
    kw = dict(model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
              max_completion_tokens=max(max_tokens, 8000) if reasoning else max_tokens)   # reasoning eats tokens
    if not reasoning and "temperature" not in _dropped[model]:
        kw["temperature"] = 0
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    return kw


@_retry
def _create(kw: dict):
    return get_client().chat.completions.create(**kw)


@_retry
async def _acreate(kw: dict):
    return await get_aclient().chat.completions.create(**kw)


def _unpack(resp) -> tuple[str, int, int]:
    u = resp.usage
    return (resp.choices[0].message.content or "", getattr(u, "prompt_tokens", 0) or 0,
            getattr(u, "completion_tokens", 0) or 0)


def _check_model(agent: str) -> str:
    model = C.MODELS[agent]
    if not model:
        raise RuntimeError(f"No deployment set for agent '{agent}'. Check DEPLOY_* in .env")
    return model


def _models_to_try(model: str) -> list[str]:
    backup = C.MODELS["backup"]
    return [model] + ([backup] if backup and backup != model else [])


def _complete(agent: str, system: str, user: str, max_tokens: int, ticker: Optional[str]) -> str:
    model, t0 = _check_model(agent), time.time()
    for m in _models_to_try(model):         # backup only after the primary has failed 4 times
        try:
            for _ in range(3):              # extra loops only to drop rejected params
                try:
                    text, pt, ct = _unpack(_create(_kwargs(m, system, user, max_tokens)))
                    _log(agent, ticker, m, pt, ct, time.time() - t0, False, fallback=m != model)
                    return text
                except Exception as e:
                    if not _bad_param(e, m):
                        raise
            raise RuntimeError(f"{m} rejected request parameters")
        except Exception as e:
            if m != model or not _transient(e):
                raise
    raise RuntimeError("unreachable")


async def _acomplete(agent: str, system: str, user: str, max_tokens: int, ticker: Optional[str]) -> str:
    model, t0 = _check_model(agent), time.time()
    async with _sem():
        for m in _models_to_try(model):
            try:
                for _ in range(3):
                    try:
                        text, pt, ct = _unpack(await _acreate(_kwargs(m, system, user, max_tokens)))
                        _log(agent, ticker, m, pt, ct, time.time() - t0, False, fallback=m != model)
                        return text
                    except Exception as e:
                        if not _bad_param(e, m):
                            raise
                raise RuntimeError(f"{m} rejected request parameters")
            except Exception as e:
                if m != model or not _transient(e):
                    raise
    raise RuntimeError("unreachable")


# ---------- parsing ----------
def _extract(text: str):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if i < 0 or j <= i:
            raise ValueError("no JSON object found in reply")
        return json.loads(t[i:j + 1])


def _validate(text: str, schema: Type[T]) -> T:
    return schema.model_validate(_extract(text))   # pydantic ValidationError is a ValueError


def _repair_prompt(user: str, err: ValueError) -> str:
    return f"{user}\n\nYour previous reply was invalid: {err}\nReturn corrected JSON only."


# ---------- disk cache and log ----------
def _key(model: str, system: str, user: str) -> str:
    return hashlib.sha256(json.dumps([model, system, user]).encode()).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    p = C.LLM_CACHE_DIR / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8"))["text"] if p.exists() else None


def _cache_put(key: str, model: str, text: str) -> None:
    C.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    final = C.LLM_CACHE_DIR / f"{key}.json"
    tmp = final.with_name(f"{key}.{threading.get_ident()}.tmp")     # write then rename: readers never see half a file
    tmp.write_text(json.dumps({"model": model, "text": text}), encoding="utf-8")
    os.replace(tmp, final)


def _log(agent, ticker, model, prompt_tokens, completion_tokens, seconds, cache_hit, **extra) -> None:
    row = dict(ts=time.time(), agent=agent, ticker=ticker, model=model, prompt_tokens=prompt_tokens,
               completion_tokens=completion_tokens, seconds=round(seconds, 3), cache_hit=cache_hit, **extra)
    C.LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _log_lock, C.LLM_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _lookup(agent: str, system: str, user: str, schema: Type[T], ticker, allow_live: bool):
    """Return (key, cached object or None). Raises in DEMO_MODE on a miss."""
    model = _check_model(agent)
    key = _key(model, system, user)
    text = _cache_get(key)
    if text is not None:
        try:
            obj = _validate(text, schema)
            _log(agent, ticker, model, 0, 0, 0, True)
            return key, obj
        except ValueError:
            pass    # cache entry no longer fits the schema: treat as a miss
    if C.DEMO_MODE and not allow_live:
        who = f"agent '{agent}'" + (f", ticker {ticker}" if ticker else "")
        raise DemoModeCacheMiss(f"DEMO_MODE=1 and no cached reply for {who} (key {key[:10]}). "
                                "Run once with DEMO_MODE=0 to fill cache/llm/.")
    return key, None


# ---------- public API ----------
def chat_json(agent: str, system: str, user: str, schema: Type[T], ticker: Optional[str] = None,
              max_tokens: int = 2000, allow_live: bool = False) -> T:
    """One JSON call for `agent`, returned as a validated `schema` object. One repair retry."""
    key, obj = _lookup(agent, system, user, schema, ticker, allow_live)
    if obj is not None:
        return obj
    text = _complete(agent, system, user, max_tokens, ticker)
    try:
        obj = _validate(text, schema)
    except ValueError as err:
        text = _complete(agent, system, _repair_prompt(user, err), max_tokens, ticker)
        obj = _validate(text, schema)
    _cache_put(key, C.MODELS[agent], text)
    return obj


async def achat_json(agent: str, system: str, user: str, schema: Type[T], ticker: Optional[str] = None,
                     max_tokens: int = 2000, allow_live: bool = False) -> T:
    """Async chat_json. At most MAX_CONCURRENCY calls in flight; use with asyncio.gather."""
    key, obj = _lookup(agent, system, user, schema, ticker, allow_live)
    if obj is not None:
        return obj
    text = await _acomplete(agent, system, user, max_tokens, ticker)
    try:
        obj = _validate(text, schema)
    except ValueError as err:
        text = await _acomplete(agent, system, _repair_prompt(user, err), max_tokens, ticker)
        obj = _validate(text, schema)
    _cache_put(key, C.MODELS[agent], text)
    return obj


@_retry
def _embed_batch(model: str, batch: list[str]):
    return get_client().embeddings.create(model=model, input=batch)


@_retry
async def _aembed_batch(model: str, batch: list[str]):
    return await get_aclient().embeddings.create(model=model, input=batch)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed with the embedding deployment in batches of 64. Callers cache the vectors."""
    model, out = _check_model("embed"), []
    for i in range(0, len(texts), C.EMBED_BATCH):
        t0 = time.time()
        resp = _embed_batch(model, texts[i:i + C.EMBED_BATCH])
        out += [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
        _log("embed", None, model, resp.usage.prompt_tokens, 0, time.time() - t0, False)
    return out


async def aembed(texts: list[str]) -> list[list[float]]:
    """Async embed: batches of 64 run concurrently under the shared semaphore."""
    model = _check_model("embed")

    async def one(batch: list[str]) -> list[list[float]]:
        async with _sem():
            t0 = time.time()
            resp = await _aembed_batch(model, batch)
            _log("embed", None, model, resp.usage.prompt_tokens, 0, time.time() - t0, False)
            return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    parts = await asyncio.gather(*(one(texts[i:i + C.EMBED_BATCH]) for i in range(0, len(texts), C.EMBED_BATCH)))
    return [v for p in parts for v in p]
