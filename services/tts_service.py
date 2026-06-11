"""ElevenLabs Text-to-Speech service: response text -> streamed speaker audio."""

from __future__ import annotations

import os
import time

import sounddevice as sd
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

# pcm_24000 -> raw signed 16-bit mono PCM at 24 kHz, ideal for direct playback.
SAMPLE_RATE = 24_000
OUTPUT_FORMAT = "pcm_24000"
TTS_MODEL_ID = "eleven_flash_v2_5"  # lowest-latency multilingual model


def _build_client() -> ElevenLabs:
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set in the environment")
    return ElevenLabs(api_key=api_key)


def speak(text: str) -> int:
    """Stream `text` to speech and play it as it arrives.

    Returns the first-byte latency in milliseconds (0 if playback failed),
    so the caller can log `tts_first_byte_ms`.
    """
    if not text:
        return 0

    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not voice_id:
        print("[TTS] ELEVENLABS_VOICE_ID is not set; cannot synthesize speech.")
        return 0

    try:
        client = _build_client()
        started = time.perf_counter()
        audio_stream = client.text_to_speech.stream(
            voice_id,
            text=text,
            model_id=TTS_MODEL_ID,
            output_format=OUTPUT_FORMAT,
        )

        first_byte_ms = 0
        leftover = b""  # carry an odd trailing byte between chunks (int16 alignment)
        with sd.RawOutputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16"
        ) as stream:
            for chunk in audio_stream:
                if not chunk:
                    continue
                if first_byte_ms == 0:
                    first_byte_ms = int((time.perf_counter() - started) * 1000)
                    print(f"[TTS] Streaming started. First byte latency: {first_byte_ms}ms")

                data = leftover + chunk
                aligned = len(data) - (len(data) % 2)
                if aligned:
                    stream.write(data[:aligned])
                leftover = data[aligned:]

        return first_byte_ms
    except Exception as exc:
        print(f"[TTS] ElevenLabs TTS error: {exc}")
        return 0


if __name__ == "__main__":
    speak("Hello, I am your AI career coach.")
