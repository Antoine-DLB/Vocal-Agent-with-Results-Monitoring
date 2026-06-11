"""Interaction logger: persist every voice interaction to logs/interactions.json."""

from __future__ import annotations

import json
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "interactions.json"


def _read_all() -> list[dict]:
    """Return every logged entry, tolerating a missing or corrupt file."""
    if not LOG_PATH.exists():
        return []
    try:
        with LOG_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def log_interaction(entry: dict) -> None:
    """Append a single interaction entry to the JSON log (creating it if needed)."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = _read_all()
    entries.append(entry)
    with LOG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)


def load_logs() -> list[dict]:
    """Public read accessor used by the FastAPI /api/logs endpoint."""
    return _read_all()


def compute_stats() -> dict:
    """Aggregate stats for the dashboard /api/stats endpoint."""
    entries = _read_all()
    total = len(entries)

    overall_scores: list[int] = []
    llm_latencies: list[int] = []
    flag_counts: dict[str, int] = {}
    score_over_time: list[dict] = []

    for entry in entries:
        scores = entry.get("scores") or {}
        overall = scores.get("overall")
        if isinstance(overall, (int, float)):
            overall_scores.append(overall)
            score_over_time.append(
                {"timestamp": entry.get("timestamp"), "overall": overall}
            )

        latency = (entry.get("latency") or {}).get("llm_ms")
        if isinstance(latency, (int, float)):
            llm_latencies.append(latency)

        for flag in scores.get("flags") or []:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    def _avg(values: list) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    return {
        "total_interactions": total,
        "avg_overall_score": _avg(overall_scores),
        "avg_latency_llm_ms": _avg(llm_latencies),
        "flag_counts": flag_counts,
        "score_over_time": score_over_time,
    }
