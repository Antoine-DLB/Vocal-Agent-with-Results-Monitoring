"""Mistral LLM-as-judge service: score an assistant response on quality criteria."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from mistralai import Mistral

load_dotenv()

MODEL = "mistral-small-latest"  # cheaper model is sufficient for evaluation
JUDGE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "judge_prompt.txt"

SCORE_KEYS = ("relevance", "concision", "tone", "overall")
ALLOWED_FLAGS = {"hallucination_risk", "off_topic", "too_vague", "too_long"}


def _load_judge_prompt() -> str:
    try:
        return JUDGE_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (
            "You are a strict evaluator. Score relevance, concision, tone and "
            "overall from 1 to 5 and return ONLY a JSON object."
        )


def _build_client() -> Mistral:
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set in the environment")
    return Mistral(api_key=api_key)


def _clamp_score(value, default: int = 3) -> int:
    """Coerce a model-provided score into a 1-5 integer."""
    try:
        return max(1, min(5, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def _fallback(reason: str) -> dict:
    """Neutral evaluation used when the judge call or parsing fails."""
    return {
        "relevance": 3,
        "concision": 3,
        "tone": 3,
        "overall": 3,
        "flags": [],
        "justification": f"Judge unavailable: {reason}",
    }


def evaluate(question: str, response: str) -> dict:
    """Score `response` to `question` and return the structured judge dict."""
    user_payload = (
        f"QUESTION:\n{question}\n\n"
        f"RESPONSE:\n{response}\n\n"
        "Return a JSON object with keys: relevance, concision, tone, overall "
        "(integers 1-5), flags (array of strings), justification (string)."
    )

    try:
        client = _build_client()
        completion = client.chat.complete(
            model=MODEL,
            messages=[
                {"role": "system", "content": _load_judge_prompt()},
                {"role": "user", "content": user_payload},
            ],
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or "{}"
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[JUDGE] Could not parse judge JSON: {exc}")
        return _fallback("invalid JSON")
    except Exception as exc:
        print(f"[JUDGE] Mistral judge error: {exc}")
        return _fallback(str(exc))

    scores = {key: _clamp_score(data.get(key)) for key in SCORE_KEYS}

    raw_flags = data.get("flags") or []
    if isinstance(raw_flags, str):
        raw_flags = [raw_flags]
    flags = [f for f in raw_flags if f in ALLOWED_FLAGS]

    result = {
        **scores,
        "flags": flags,
        "justification": str(data.get("justification", "")).strip(),
    }

    print(
        "[JUDGE] Scores: "
        f"relevance={result['relevance']} concision={result['concision']} "
        f"tone={result['tone']} overall={result['overall']} flags={result['flags']}"
    )
    return result


if __name__ == "__main__":
    print(evaluate("How do I get a job at Mistral?", "Build a strong portfolio."))
