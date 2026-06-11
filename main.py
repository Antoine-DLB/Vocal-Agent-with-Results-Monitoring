"""AI Career Coach voice assistant — entry point.

Runs a FastAPI app that serves both:
- the web chat UI (talk to the agent from the browser via POST /api/chat), and
- the monitoring dashboard (logs, stats, charts).

By default the terminal push-to-talk voice loop also runs alongside the server.
Pass `--no-voice` to run the web server only (handy on machines without a mic).
"""

from __future__ import annotations

import base64
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
EXPECTED_KEYS = ("ELEVENLABS_API_KEY", "MISTRAL_API_KEY")


def _build_entry(transcript: str, response: str, scores: dict,
                 stt_ms: int, llm_ms: int, tts_ms: int,
                 prompt_tokens: int, completion_tokens: int) -> dict:
    """Assemble a log entry in the schema defined in CLAUDE.md (Stage 6)."""
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transcript": transcript,
        "response": response,
        "scores": scores,
        "latency": {"stt_ms": stt_ms, "llm_ms": llm_ms, "tts_first_byte_ms": tts_ms},
        "tokens": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


# --------------------------------------------------------------------------- #
# FastAPI app                                                                 #
# --------------------------------------------------------------------------- #
def create_app() -> FastAPI:
    # Imported lazily so the API can start even if the audio stack is missing.
    from services.logger_service import compute_stats, load_logs

    app = FastAPI(title="AI Career Coach — Voice Chat & Monitoring")

    @app.get("/api/logs")
    def get_logs() -> list[dict]:
        return load_logs()

    @app.get("/api/stats")
    def get_stats() -> dict:
        return compute_stats()

    @app.post("/api/chat")
    def chat(audio: UploadFile = File(...)):
        """Full voice turn from the browser: audio -> transcript -> answer.

        Runs STT -> LLM -> TTS -> judge, logs the interaction, and returns the
        transcript, the answer text, the judge scores and the answer audio
        (base64 MP3) so the page can display and play the response.
        """
        from services.judge_service import evaluate
        from services.llm_service import get_response_detailed
        from services.logger_service import log_interaction
        from services.stt_service import transcribe_audio
        from services.tts_service import synthesize

        # 1. STT
        stt = transcribe_audio(audio.file.read(), audio.filename or "audio.webm")
        if not stt:
            return JSONResponse(status_code=422, content={"error": "Could not transcribe the audio."})

        # 2. LLM
        try:
            llm = get_response_detailed(stt.text)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(status_code=502, content={"error": f"LLM error: {exc}"})
        if not llm.text:
            return JSONResponse(status_code=502, content={"error": "Empty LLM response."})

        # 3. TTS (full MP3 for browser playback)
        tts = synthesize(llm.text)
        tts_ms = tts.first_byte_ms if tts else 0
        audio_b64 = base64.b64encode(tts.audio).decode("ascii") if tts else ""

        # 4. Judge
        scores = evaluate(stt.text, llm.text)

        # 5. Log
        entry = _build_entry(
            stt.text, llm.text, scores,
            stt.latency_ms, llm.latency_ms, tts_ms,
            llm.prompt_tokens, llm.completion_tokens,
        )
        log_interaction(entry)

        return {
            "transcript": stt.text,
            "response": llm.text,
            "scores": scores,
            "latency": entry["latency"],
            "audio": audio_b64,
            "audio_mime": tts.mime if tts else "",
        }

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
        log_interaction(_build_entry(
            transcript, llm.text, scores,
            stt_ms, llm.latency_ms, tts_first_byte_ms,
            llm.prompt_tokens, llm.completion_tokens,
        ))

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

    if "--no-voice" in sys.argv:
        # Web-only mode: serve the chat UI + dashboard in the foreground.
        print(f"Web chat + dashboard at http://localhost:{port} (terminal voice loop off)")
        _run_dashboard(port)
        return

    dashboard_thread = threading.Thread(target=_run_dashboard, args=(port,), daemon=True)
    dashboard_thread.start()
    print(f"Web chat + dashboard at http://localhost:{port}")

    run_voice_loop()


if __name__ == "__main__":
    main()
