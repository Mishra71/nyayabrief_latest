"""Provider-agnostic LLM layer (LiteLLM). Switching Gemini <-> Groq <-> Claude = change LLM_CHAIN in .env.

Handles: throttling, ordered fallback chain, malformed-JSON repair retry, quota detection.
"""
from __future__ import annotations

import json
import logging
import re
import time

import litellm
from pydantic import BaseModel, ValidationError

from .config import get_settings

log = logging.getLogger(__name__)
litellm.suppress_debug_info = True


class QuotaExhausted(RuntimeError):
    """Every provider in the chain is rate-limited -> stop, resume later (state is in DB)."""


class LLMFailure(RuntimeError):
    """Providers failed for a non-quota reason (bad output, outage)."""


_last_call: dict[str, float] = {}


def _throttle(model: str) -> None:
    wait = _last_call.get(model, 0.0) + get_settings().llm_min_interval_sec - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call[model] = time.monotonic()


def _models(chain: str | None) -> list[str]:
    return [m.strip() for m in (chain or get_settings().llm_chain).split(",") if m.strip()]


def _run(messages: list[dict], chain: str | None, json_mode: bool) -> tuple[str, str]:
    models = _models(chain)
    quota_hits, last_err = 0, None
    for model in models:
        try:
            _throttle(model)
            kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
            r = litellm.completion(model=model, messages=messages, temperature=0, timeout=90, num_retries=0, **kwargs)
            return r.choices[0].message.content or "", model
        except litellm.RateLimitError as e:
            quota_hits += 1
            last_err = e
            log.warning("rate-limited on %s -> next provider", model)
        except Exception as e:  # outage, timeout, bad request... try the next provider
            last_err = e
            log.warning("%s failed (%s: %s) -> next provider", model, type(e).__name__, str(e)[:200])
    if quota_hits == len(models):
        raise QuotaExhausted(f"all providers rate-limited: {last_err}")
    raise LLMFailure(f"all providers failed: {last_err}")


def _parse_json(text: str):
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def call_structured(system: str, user: str, schema: type[BaseModel], chain: str | None = None) -> tuple[BaseModel, str]:
    """LLM -> JSON -> Pydantic. On invalid output: ONE repair retry that shows the model its own error."""
    hint = json.dumps(schema.model_json_schema())
    messages = [
        {"role": "system", "content": f"{system}\n\nReturn ONLY valid JSON matching this JSON Schema (no prose, no markdown):\n{hint}"},
        {"role": "user", "content": user},
    ]
    last_err: Exception | None = None
    for _ in range(2):
        text, model = _run(messages, chain, json_mode=True)
        try:
            return schema.model_validate(_parse_json(text)), model
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"Your JSON was invalid: {str(e)[:600]}\nReturn the corrected JSON only."},
            ]
    raise LLMFailure(f"invalid structured output after retry: {last_err}")


def call_text(system: str, user: str, chain: str | None = None) -> str:
    text, _ = _run([{"role": "system", "content": system}, {"role": "user", "content": user}], chain, json_mode=False)
    return text


def embed(texts: list[str]) -> list[list[float]] | None:
    """Returns None on any failure -> app falls back to keyword search. Never blocks the pipeline."""
    s = get_settings()
    if not s.embeddings_enabled or not texts:
        return None
    try:
        r = litellm.embedding(model=s.embed_model, input=texts, dimensions=s.embed_dim)
        vecs = [d["embedding"] for d in r.data]
        return vecs if all(len(v) == s.embed_dim for v in vecs) else None
    except Exception as e:
        log.warning("embedding failed: %s: %s", type(e).__name__, str(e)[:200])
        return None
