"""ElevenLabs Speech-to-Text service: microphone capture -> transcript."""

from __future__ import annotations

import io
import os
import wave

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
RECORD_SECONDS = 5            # fixed capture window (see CLAUDE.md Stage 2)
STT_MODEL_ID = "scribe_v1"


def _build_client() -> ElevenLabs:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set in the environment")
    return ElevenLabs(api_key=api_key)


def _record_wav_bytes(seconds: int = RECORD_SECONDS) -> bytes:
    """Capture `seconds` of mono audio from the default microphone as WAV bytes."""
    print(f"[STT] Recording for {seconds}s... speak now.")
    recording = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()  # block until the recording is finished

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)            # int16 -> 2 bytes per sample
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(recording.tobytes())
    buffer.seek(0)
    return buffer.getvalue()


def record_and_transcribe() -> str | None:
    """Record from the microphone and return the transcript, or None on error."""
    try:
        wav_bytes = _record_wav_bytes()
    except Exception as exc:  # no microphone, PortAudio failure, etc.
        print(f"[STT] Microphone capture failed: {exc}")
        return None

    try:
        client = _build_client()
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "recording.wav"  # the SDK uses the name for the mime type
        result = client.speech_to_text.convert(
            model_id=STT_MODEL_ID,
            file=audio_file,
        )
        transcript = (getattr(result, "text", "") or "").strip()
    except Exception as exc:
        print(f"[STT] ElevenLabs STT error: {exc}")
        return None

    if not transcript:
        print("[STT] Empty transcript (no speech detected).")
        return None

    print(f'[STT] Transcript: "{transcript}"')
    return transcript


if __name__ == "__main__":
    record_and_transcribe()
