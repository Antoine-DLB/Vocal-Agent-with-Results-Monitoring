"""ElevenLabs Speech-to-Text service: microphone capture -> transcript.

Recording is push-to-talk style: it starts immediately and runs until the user
presses Enter, so the user can speak for as long as they need (no fixed window).
"""

from __future__ import annotations

import io
import os
import time
import wave
from dataclasses import dataclass

import numpy as np

# sounddevice imports PortAudio at import time. It is only needed for the
# (audio-dependent) capture step, so the import lives here at module scope on
# purpose: a machine running the voice loop is expected to have PortAudio.
import sounddevice as sd
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

# Recording configuration. ElevenLabs STT (scribe_v1) accepts standard WAV.
SAMPLE_RATE = 16_000          # 16 kHz mono is plenty for speech recognition
STT_MODEL_ID = "scribe_v1"


@dataclass
class STTResult:
    """Transcript plus the time spent in the STT API call (not the talk time)."""

    text: str
    latency_ms: int


def _build_client() -> ElevenLabs:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set in the environment")
    return ElevenLabs(api_key=api_key)


def _record_until_enter() -> np.ndarray | None:
    """Record mono audio until the user presses Enter; return the samples.

    The PortAudio callback fills `frames` on its own thread while the main
    thread blocks on `input()`, so recording length is bounded only by the user.
    """
    frames: list[np.ndarray] = []

    def callback(indata, _frame_count, _time_info, status):  # noqa: ANN001
        if status:
            # Overflows are non-fatal; keep capturing what we can.
            print(f"[STT] Audio status: {status}", flush=True)
        frames.append(indata.copy())

    print("[STT] Recording... press Enter to stop.")
    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback
    ):
        try:
            input()  # block here until the user presses Enter
        except (EOFError, KeyboardInterrupt):
            pass

    if not frames:
        return None
    return np.concatenate(frames, axis=0)


def _to_wav_bytes(audio: np.ndarray) -> bytes:
    """Wrap int16 mono samples in an in-memory WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)            # int16 -> 2 bytes per sample
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio.tobytes())
    buffer.seek(0)
    return buffer.getvalue()


def record_and_transcribe_detailed() -> STTResult | None:
    """Record until Enter, transcribe, and return transcript + API latency."""
    try:
        audio = _record_until_enter()
    except Exception as exc:  # no microphone, PortAudio failure, etc.
        print(f"[STT] Microphone capture failed: {exc}")
        return None

    if audio is None or len(audio) == 0:
        print("[STT] No audio captured.")
        return None

    try:
        client = _build_client()
        audio_file = io.BytesIO(_to_wav_bytes(audio))
        audio_file.name = "recording.wav"  # the SDK uses the name for the mime type
        started = time.perf_counter()
        result = client.speech_to_text.convert(
            model_id=STT_MODEL_ID,
            file=audio_file,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        transcript = (getattr(result, "text", "") or "").strip()
    except Exception as exc:
        print(f"[STT] ElevenLabs STT error: {exc}")
        return None

    if not transcript:
        print("[STT] Empty transcript (no speech detected).")
        return None

    print(f'[STT] Transcript: "{transcript}"')
    return STTResult(text=transcript, latency_ms=latency_ms)


def record_and_transcribe() -> str | None:
    """Record from the microphone and return the transcript, or None on error."""
    result = record_and_transcribe_detailed()
    return result.text if result else None


if __name__ == "__main__":
    record_and_transcribe()
