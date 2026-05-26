"""
shared/llm.py
=============
Single interface for all LLM calls across both tools.
Supports two providers, selected per-call:

  Provider.ANTHROPIC  — Anthropic API (claude-*)
  Provider.LOCAL      — OpenAI-compatible endpoint (llama.cpp, Ollama, LM Studio)

Design goals:
  - Every agent calls llm.complete() — never the SDK directly
  - Model, temperature, max_tokens are all overridable per-call
  - Retries with exponential backoff are handled here, not in agents
  - Token usage is logged here so agents never need to think about it
  - Switching a single agent to local inference = one kwarg change

Configuration (via environment variables):
  ANTHROPIC_API_KEY       required for Provider.ANTHROPIC
  LOCAL_LLM_BASE_URL      base URL for OpenAI-compatible server
                          default: http://localhost:8080/v1  (llama.cpp default)
  LOCAL_LLM_MODEL         model name to send to local server
                          default: local  (llama.cpp ignores this)
  LOCAL_LLM_API_KEY       optional; some servers require a dummy key
                          default: "not-needed"
"""

from __future__ import annotations

import os
import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ── Provider enum ─────────────────────────────────────────────────────────────

class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    LOCAL     = "local"       # any OpenAI-compatible endpoint


# ── Defaults ──────────────────────────────────────────────────────────────────

ANTHROPIC_DEFAULT_MODEL = "claude-haiku-4-5"    # fast + cheap for most agents
ANTHROPIC_SMART_MODEL   = "claude-sonnet-4-6"   # use for logic + security agents

LOCAL_BASE_URL  = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:8080/v1")
LOCAL_MODEL     = os.getenv("LOCAL_LLM_MODEL",    "local")
LOCAL_API_KEY   = os.getenv("LOCAL_LLM_API_KEY",  "not-needed")

MAX_RETRIES     = 3
RETRY_BASE_SECS = 2.0   # doubles each attempt: 2s, 4s, 8s


# ── Response container ────────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    content:        str
    provider:       Provider
    model:          str
    input_tokens:   int  = 0
    output_tokens:  int  = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ── Lazy client cache — instantiated once per provider ───────────────────────

_anthropic_client = None
_openai_client    = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. Run: uv add anthropic"
            )
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


def _get_openai(base_url: str, api_key: str):
    """
    Returns an OpenAI client pointed at the given base_url.
    Works with llama.cpp server, Ollama, LM Studio, vLLM — anything
    that exposes an OpenAI-compatible /v1/chat/completions endpoint.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package not installed. Run: uv add openai"
        )
    return OpenAI(base_url=base_url, api_key=api_key)


# ── Core completion function ──────────────────────────────────────────────────

def complete(
    prompt:       str,
    *,
    system:       str             = "",
    provider:     Provider        = Provider.ANTHROPIC,
    model:        Optional[str]   = None,
    max_tokens:   int             = 1024,
    temperature:  float           = 0.2,       # low by default — agents want determinism
    base_url:     Optional[str]   = None,      # override LOCAL_LLM_BASE_URL per-call
    api_key:      Optional[str]   = None,      # override LOCAL_LLM_API_KEY per-call
) -> LLMResponse:
    """
    Send a prompt to the chosen provider and return an LLMResponse.

    Examples
    --------
    # Anthropic (default)
    resp = complete("Review this diff: ...", system="You are a security reviewer.")

    # Faster/cheaper model for less critical analysis
    resp = complete("Check style: ...", model="claude-haiku-4-5")

    # Local llama.cpp (default port)
    resp = complete("Explain this function", provider=Provider.LOCAL)

    # Local with custom URL (e.g. Ollama)
    resp = complete("...", provider=Provider.LOCAL, base_url="http://localhost:11434/v1")
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if provider == Provider.ANTHROPIC:
                return _call_anthropic(prompt, system, model, max_tokens, temperature)
            else:
                return _call_openai_compatible(
                    prompt, system, model, max_tokens, temperature,
                    base_url or LOCAL_BASE_URL,
                    api_key  or LOCAL_API_KEY,
                )
        except Exception as exc:
            if attempt == MAX_RETRIES:
                log.error("LLM call failed after %d attempts: %s", MAX_RETRIES, exc)
                raise
            wait = RETRY_BASE_SECS * (2 ** (attempt - 1))
            log.warning(
                "LLM call failed (attempt %d/%d), retrying in %.0fs: %s",
                attempt, MAX_RETRIES, wait, exc
            )
            time.sleep(wait)

    raise RuntimeError("unreachable")   # satisfies type checker


def _call_anthropic(
    prompt:      str,
    system:      str,
    model:       Optional[str],
    max_tokens:  int,
    temperature: float,
) -> LLMResponse:
    client  = _get_anthropic()
    model   = model or ANTHROPIC_DEFAULT_MODEL

    kwargs: dict = dict(
        model      = model,
        max_tokens = max_tokens,
        messages   = [{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system

    # temperature not supported on some thinking models; guard it
    if temperature is not None:
        kwargs["temperature"] = temperature

    msg = client.messages.create(**kwargs)

    return LLMResponse(
        content       = msg.content[0].text,
        provider      = Provider.ANTHROPIC,
        model         = model,
        input_tokens  = msg.usage.input_tokens,
        output_tokens = msg.usage.output_tokens,
    )


def _call_openai_compatible(
    prompt:      str,
    system:      str,
    model:       Optional[str],
    max_tokens:  int,
    temperature: float,
    base_url:    str,
    api_key:     str,
) -> LLMResponse:
    client = _get_openai(base_url, api_key)
    model  = model or LOCAL_MODEL

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model       = model,
        messages    = messages,
        max_tokens  = max_tokens,
        temperature = temperature,
    )

    usage = resp.usage
    return LLMResponse(
        content       = resp.choices[0].message.content or "",
        provider      = Provider.LOCAL,
        model         = model,
        input_tokens  = usage.prompt_tokens     if usage else 0,
        output_tokens = usage.completion_tokens if usage else 0,
    )


# ── Convenience: select smart model for a given agent role ───────────────────

def model_for_role(role: str) -> str:
    """
    Return the appropriate Anthropic model for a given agent role.
    Logic and security get the smarter model; others get haiku.

    Override any time by passing model= directly to complete().
    """
    high_stakes = {"logic", "security"}
    if role in high_stakes:
        return ANTHROPIC_SMART_MODEL
    return ANTHROPIC_DEFAULT_MODEL
