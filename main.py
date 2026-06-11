"""AI Career Coach voice assistant — entry point.

Runs the FastAPI monitoring dashboard and the interactive voice loop side by
side. The dashboard server runs in a background daemon thread while the voice
loop owns the main thread (so it can read keyboard input).
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
EXPECTED_KEYS = ("ELEVENLABS_API_KEY", "MISTRAL_API_KEY")


# --------------------------------------------------------------------------- #
# FastAPI app                                                                 #
# --------------------------------------------------------------------------- #
def create_app() -> FastAPI:
    # Imported lazily so the API can start even if the audio stack is missing.
    from services.logger_service import compute_stats, load_logs

    app = FastAPI(title="AI Career Coach — Monitoring Dashboard")

    @app.get("/api/logs")
    def get_logs() -> list[dict]:
        return load_logs()

    @app.get("/api/stats")
    def get_stats() -> dict:
        return compute_stats()

    # Serve the static dashboard at the root (registered last so /api/* wins).
    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

    return app


app = create_app()


def _run_dashboard(port: int) -> None:
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# --------------------------------------------------------------------------- #
# Voice loop                                                                  #
# --------------------------------------------------------------------------- #
class _SpeakWorker:
    """Run TTS in a background thread and capture its first-byte latency."""

    def __init__(self, text: str) -> None:
        self.first_byte_ms = 0
        self._thread = threading.Thread(target=self._run, args=(text,), daemon=True)

    def _run(self, text: str) -> None:
        from services.tts_service import speak

        self.first_byte_ms = speak(text)

    def start(self) -> "_SpeakWorker":
        self._thread.start()
        return self

    def join(self) -> int:
        self._thread.join()
        return self.first_byte_ms


def run_voice_loop() -> None:
    from services.judge_service import evaluate
    from services.llm_service import get_response_detailed
    from services.logger_service import load_logs, log_interaction
    from services.stt_service import record_and_transcribe_detailed

    print("\nVoice loop ready. Press Enter to ask a question (Ctrl+C to quit).")

    while True:
        try:
            input("\n> Press Enter to START speaking (Enter again to STOP)...")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting voice loop.")
            return

        # 1. STT (records until the user presses Enter again)
        stt = record_and_transcribe_detailed()
        if not stt:
            print("[LOOP] No transcript, skipping.")
            continue
        transcript = stt.text
        stt_ms = stt.latency_ms

        # 2. LLM
        try:
            llm = get_response_detailed(transcript)
        except Exception as exc:
            print(f"[LOOP] LLM failed: {exc}")
            continue
        if not llm.text:
            print("[LOOP] Empty response, skipping.")
            continue

        # 3. TTS (non-blocking: audio plays while the judge scores the answer)
        speaker = _SpeakWorker(llm.text).start()

        # 4. Judge (runs concurrently with playback)
        scores = evaluate(transcript, llm.text)

        # Wait for playback to finish and collect its first-byte latency.
        tts_first_byte_ms = speaker.join()

        # 5. Log
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transcript": transcript,
            "response": llm.text,
            "scores": scores,
            "latency": {
                "stt_ms": stt_ms,
                "llm_ms": llm.latency_ms,
                "tts_first_byte_ms": tts_first_byte_ms,
            },
            "tokens": {
                "prompt_tokens": llm.prompt_tokens,
                "completion_tokens": llm.completion_tokens,
            },
        }
        log_interaction(entry)

        # 6. Summary
        total = len(load_logs())
        print(f'\n[LOOP] Question: "{transcript}"')
        print(f'[LOOP] Response: "{llm.text}"')
        print(
            f"[LOOP] Scores: overall={scores['overall']} | "
            f"relevance={scores['relevance']} | "
            f"concision={scores['concision']} | tone={scores['tone']}"
        )
        print(
            f"[LOOP] Latency: STT={stt_ms}ms LLM={llm.latency_ms}ms "
            f"TTS={tts_first_byte_ms}ms"
        )
        print(f"[LOOP] Logged. Total interactions: {total}")


# --------------------------------------------------------------------------- #
# Startup                                                                     #
# --------------------------------------------------------------------------- #
def main() -> None:
    present = [key for key in EXPECTED_KEYS if os.getenv(key)]
    print(f"Environment loaded. Keys present: {', '.join(present) if present else 'none'}")

    port = int(os.getenv("DASHBOARD_PORT", "8000"))
    dashboard_thread = threading.Thread(target=_run_dashboard, args=(port,), daemon=True)
    dashboard_thread.start()
    print(f"Dashboard running at http://localhost:{port}")

    run_voice_loop()


if __name__ == "__main__":
    main()
