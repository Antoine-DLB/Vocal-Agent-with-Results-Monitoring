"""ElevenLabs Speech-to-Text service: audio -> transcript.

Two entry points share the same transcription core:
- `record_and_transcribe_detailed()` captures from the local microphone
  (push-to-talk: records until the user presses Enter).
- `transcribe_audio()` transcribes an already-captured audio blob, e.g. one
  uploaded from the browser by the web chat UI.

`sounddevice`/PortAudio is imported lazily inside the microphone path only, so
the web path works on machines without audio hardware.
"""

from __future__ import annotations

import io
import os
import time
import wave
from dataclasses import dataclass

import numpy as np
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


def _transcribe(file_bytes: bytes, name: str) -> STTResult | None:
    """Send raw audio bytes to ElevenLabs STT and return transcript + latency."""
    try:
        client = _build_client()
        audio_file = io.BytesIO(file_bytes)
        audio_file.name = name  # the SDK derives the mime type from the name
        started = time.perf_counter()
        result = client.speech_to_text.convert(model_id=STT_MODEL_ID, file=audio_file)
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


def transcribe_audio(data: bytes, filename: str = "audio.webm") -> STTResult | None:
    """Transcribe an uploaded audio blob (used by the web /api/chat endpoint)."""
    if not data:
        print("[STT] Empty audio upload.")
        return None
    return _transcribe(data, filename)


# --------------------------------------------------------------------------- #
# Local microphone capture (terminal voice loop)                              #
# --------------------------------------------------------------------------- #
def _record_until_enter() -> np.ndarray | None:
    """Record mono audio until the user presses Enter; return the samples.

    The PortAudio callback fills `frames` on its own thread while the main
    thread blocks on `input()`, so recording length is bounded only by the user.
    """
    import sounddevice as sd  # lazy: PortAudio only needed for local capture

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

    return _transcribe(_to_wav_bytes(audio), "recording.wav")


def record_and_transcribe() -> str | None:
    """Record from the microphone and return the transcript, or None on error."""
    result = record_and_transcribe_detailed()
    return result.text if result else None


if __name__ == "__main__":
    record_and_transcribe()
