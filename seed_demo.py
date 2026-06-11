"""Seed the interaction log with demo data so the dashboard can be explored
without a microphone, API keys, or any external service.

Usage:
    python seed_demo.py          # add demo interactions to logs/interactions.json
    python seed_demo.py --reset  # clear the log first, then add demo interactions
    python main.py               # then open http://localhost:8000
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone

from services.logger_service import LOG_PATH, log_interaction

# A few realistic AI-career-coaching interactions with varied scores and flags
# so every part of the dashboard (chart, stats, flags) has something to show.
DEMO_INTERACTIONS = [
    {
        "transcript": "How do I get a job at Mistral AI as an ML engineer?",
        "response": (
            "Master transformers and PyTorch, then ship a public project that "
            "fine-tunes an open model. Contribute to a Mistral repo, write up the "
            "results, and reference it directly in your application."
        ),
        "scores": {
            "relevance": 5, "concision": 4, "tone": 5, "overall": 5,
            "flags": [],
            "justification": "Directly answers with concrete, actionable steps.",
        },
        "latency": {"stt_ms": 5120, "llm_ms": 870, "tts_first_byte_ms": 240},
        "tokens": {"prompt_tokens": 95, "completion_tokens": 48},
    },
    {
        "transcript": "What skills do I need to become an AI product manager?",
        "response": (
            "Learn LLM capabilities and limits, basic prompt design, and how to "
            "scope an eval. Pair that with classic PM skills: discovery, "
            "prioritization, and metrics. Build one AI feature end to end to prove it."
        ),
        "scores": {
            "relevance": 5, "concision": 4, "tone": 4, "overall": 4,
            "flags": [],
            "justification": "Relevant and structured, slightly long.",
        },
        "latency": {"stt_ms": 5080, "llm_ms": 940, "tts_first_byte_ms": 210},
        "tokens": {"prompt_tokens": 88, "completion_tokens": 52},
    },
    {
        "transcript": "Should I learn AI?",
        "response": (
            "It depends on your goals, but generally yes, AI literacy helps in most "
            "roles. There are many resources available online to get started today."
        ),
        "scores": {
            "relevance": 3, "concision": 4, "tone": 3, "overall": 3,
            "flags": ["too_vague"],
            "justification": "Generic advice; lacks specific, actionable steps.",
        },
        "latency": {"stt_ms": 5030, "llm_ms": 610, "tts_first_byte_ms": 260},
        "tokens": {"prompt_tokens": 70, "completion_tokens": 34},
    },
    {
        "transcript": "How do I prepare for an AI solutions engineer interview?",
        "response": (
            "Practice explaining RAG, tool use, and latency trade-offs out loud. "
            "Build a small demo that calls an LLM API and handle one failure mode "
            "gracefully. Be ready to whiteboard an integration for a customer."
        ),
        "scores": {
            "relevance": 5, "concision": 5, "tone": 5, "overall": 5,
            "flags": [],
            "justification": "Precise, concise, and tailored to the role.",
        },
        "latency": {"stt_ms": 5150, "llm_ms": 820, "tts_first_byte_ms": 230},
        "tokens": {"prompt_tokens": 92, "completion_tokens": 46},
    },
    {
        "transcript": "Tell me everything about the entire history of artificial intelligence.",
        "response": (
            "AI began in the 1950s with symbolic reasoning, went through several "
            "winters, saw machine learning rise in the 2000s, then deep learning "
            "in the 2010s, and large language models in the 2020s. Each wave "
            "expanded what machines could perceive, generate, and automate across "
            "industries, research, and everyday consumer products worldwide."
        ),
        "scores": {
            "relevance": 4, "concision": 2, "tone": 4, "overall": 3,
            "flags": ["too_long"],
            "justification": "Accurate but exceeds the concision target.",
        },
        "latency": {"stt_ms": 5210, "llm_ms": 1180, "tts_first_byte_ms": 250},
        "tokens": {"prompt_tokens": 80, "completion_tokens": 88},
    },
]


def seed(reset: bool = False) -> None:
    if reset and LOG_PATH.exists():
        LOG_PATH.unlink()
        print(f"Cleared {LOG_PATH}")

    base_time = datetime.now(timezone.utc) - timedelta(minutes=len(DEMO_INTERACTIONS) * 3)
    for index, item in enumerate(DEMO_INTERACTIONS):
        entry = {
            "id": str(uuid.uuid4()),
            # space the timestamps a few minutes apart so the chart has a trend
            "timestamp": (base_time + timedelta(minutes=index * 3)).isoformat(),
            **item,
        }
        log_interaction(entry)

    print(f"Seeded {len(DEMO_INTERACTIONS)} demo interactions into {LOG_PATH}")
    print("Now run:  python main.py   then open http://localhost:8000")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
