"""Mistral main LLM service: transcript -> AI-career-coach response."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from mistralai import Mistral

load_dotenv()

MODEL = "mistral-large-latest"
SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"


@dataclass
class LLMResult:
    """Full result of an LLM call, used by the logger and the voice loop."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


def _load_system_prompt() -> str:
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        # Fallback keeps the assistant usable even if the prompt file is missing.
        return (
            "You are an expert AI career coach. Your answers are direct, "
            "actionable, and under 100 words."
        )


def _build_client() -> Mistral:
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set in the environment")
    return Mistral(api_key=api_key)


def get_response_detailed(transcript: str) -> LLMResult:
    """Call Mistral and return the response text plus token usage and latency."""
    client = _build_client()
    system_prompt = _load_system_prompt()

    started = time.perf_counter()
    response = client.chat.complete(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    text = (response.choices[0].message.content or "").strip()
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0

    print(f'[LLM] Response: "{text}"')
    return LLMResult(
        text=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )


def get_response(transcript: str) -> str:
    """Return the assistant response for a transcript (see CLAUDE.md Stage 3)."""
    try:
        return get_response_detailed(transcript).text
    except Exception as exc:
        print(f"[LLM] Mistral error: {exc}")
        return ""


if __name__ == "__main__":
    print(get_response("How do I get a job at Mistral AI?"))
