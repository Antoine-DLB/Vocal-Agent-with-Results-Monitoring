# AI Career Coach — Voice Assistant with LLM-as-Judge

A voice assistant specialized in AI career strategy that demonstrates
production-grade LLM evaluation patterns. You speak a question, the assistant
answers vocally, and **every** response is automatically scored by a second LLM
judge and logged to a live monitoring dashboard.

```
🎙  ElevenLabs STT  →  🧠 Mistral large  →  🔊 ElevenLabs TTS (streaming)
                              │
                              └─►  ⚖️ Mistral small (judge)  →  📊 Dashboard
```

## Features

- **Voice pipeline** — microphone capture → ElevenLabs Scribe STT → Mistral
  `mistral-large-latest` → ElevenLabs streaming TTS played through your speakers.
- **LLM-as-judge** — every answer is scored 1–5 on *relevance, concision, tone*
  and *overall* by `mistral-small-latest`, using strict JSON structured output.
- **Observability** — FastAPI backend + zero-build HTML/JS dashboard (Chart.js)
  showing interaction history, score trends, latency and quality flags.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in your keys
python main.py              # starts the voice loop + dashboard
```

Then open the dashboard at <http://localhost:8000>. Press **Enter** in the
terminal to record a question (5 s), and watch the interaction appear on the
dashboard with its judge scores.

## Configuration

| Variable | Purpose |
| --- | --- |
| `ELEVENLABS_API_KEY` | ElevenLabs STT + TTS |
| `MISTRAL_API_KEY` | Main LLM + judge LLM |
| `ELEVENLABS_VOICE_ID` | Voice used for TTS (pick one in the ElevenLabs dashboard) |
| `DASHBOARD_PORT` | Dashboard port (default `8000`) |

## Project layout

```
main.py                 # Entry point: dashboard server + voice loop
services/
  stt_service.py        # mic capture → transcript
  llm_service.py        # transcript → coach response
  tts_service.py        # response → streamed speech
  judge_service.py      # response → quality scores (JSON)
  logger_service.py     # interaction log + dashboard stats
dashboard/              # index.html + app.js (no build step)
prompts/                # system + judge prompts
logs/interactions.json  # persisted interactions (gitignored)
```

See [`CLAUDE.md`](./CLAUDE.md) for the full specification and acceptance criteria.

## Notes

- The voice loop requires a working microphone and PortAudio (`sounddevice`).
- API keys in `.env` and the `logs/` directory are never committed.
