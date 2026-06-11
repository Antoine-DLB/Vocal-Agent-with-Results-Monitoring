# CLAUDE.md — AI Career Coach Voice Assistant with LLM-as-Judge

## Project overview

A voice assistant specialized in AI career strategy, built to demonstrate
production-grade LLM evaluation patterns. The user speaks a question,
the assistant responds vocally, and every interaction is automatically
scored by a second LLM judge and logged to a minimal web dashboard.

**Target audience for demo:** Mistral AI and ElevenLabs recruiters/engineers.

**Core value proposition:**
- Voice pipeline: ElevenLabs STT → Mistral LLM → ElevenLabs TTS
- Evaluation pipeline: Mistral judge scores every response (relevance, concision, tone)
- Observability dashboard: HTML/JS page showing interaction history and quality scores

---

## Stack

- **Python 3.11+**
- **ElevenLabs SDK v2+** — STT (speech-to-text) and TTS (text-to-speech streaming)
- **Mistral AI SDK** — main LLM (mistral-large-latest) + judge LLM (mistral-small-latest)
- **sounddevice + numpy** — microphone capture
- **FastAPI** — serves the dashboard and logs API
- **python-dotenv** — environment variables
- **JSON** — local log storage (logs/interactions.json)

---

## Project structure

```
ai-career-voice-coach/
├── CLAUDE.md
├── .env                          # API keys (never commit)
├── .env.example                  # Template with key names only
├── .gitignore
├── requirements.txt
├── main.py                       # Entry point: starts voice loop + dashboard
├── services/
│   ├── stt_service.py            # ElevenLabs STT: mic capture → transcript
│   ├── llm_service.py            # Mistral main LLM: transcript → response
│   ├── tts_service.py            # ElevenLabs TTS: response → audio stream
│   ├── judge_service.py          # Mistral judge: scores the response
│   └── logger_service.py         # Writes interaction logs to JSON
├── dashboard/
│   ├── index.html                # Minimal dashboard UI
│   └── app.js                    # Fetches logs from FastAPI, renders table + charts
├── logs/
│   └── interactions.json         # Persisted interaction log
└── prompts/
    ├── system_prompt.txt         # System prompt for the main assistant
    └── judge_prompt.txt          # System prompt for the LLM judge
```

---

## Environment variables

```
# .env.example
ELEVENLABS_API_KEY=your_key_here
MISTRAL_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here   # Choose a voice in ElevenLabs dashboard
DASHBOARD_PORT=8000
```

---

## Development stages

Work through these stages sequentially. Do not start a stage until the
previous one passes its acceptance criteria.

---

### Stage 1 — Project scaffold and dependencies

**Goal:** Clean repo structure, dependencies installed, env vars loading correctly.

**Tasks:**
- Create all files and folders listed in the project structure above
- Write requirements.txt with pinned versions
- Write .env.example (no real keys)
- Write .gitignore (exclude .env, logs/, __pycache__, *.pyc)
- In main.py, load .env with python-dotenv and print a startup confirmation message

**Acceptance criteria:**
- `pip install -r requirements.txt` runs without errors
- `python main.py` prints: "Environment loaded. Keys present: ELEVENLABS_API_KEY, MISTRAL_API_KEY"
- .env is not tracked by git

---

### Stage 2 — STT service (microphone → transcript)

**Goal:** Capture audio from microphone and return a text transcript via ElevenLabs STT.

**Tasks:**
- In `services/stt_service.py`, implement `record_and_transcribe() -> str`
- Record audio for a fixed duration (5 seconds) using sounddevice
- Send audio buffer to ElevenLabs STT API
- Return the transcript string
- Handle errors: no microphone detected, empty transcript, API error

**Acceptance criteria:**
- `record_and_transcribe()` returns a non-empty string when called
- Prints transcript to console: `[STT] Transcript: "..."`
- If ElevenLabs returns an error, prints a clear error message and returns None

---

### Stage 3 — Main LLM service (transcript → response)

**Goal:** Send the transcript to Mistral and get a response focused on AI career strategy.

**Tasks:**
- In `services/llm_service.py`, implement `get_response(transcript: str) -> str`
- Load system prompt from `prompts/system_prompt.txt`
- System prompt must instruct the model to act as an AI career coach,
  keep responses under 100 words, be direct and actionable
- Use `mistral-large-latest`
- Return the response string

**System prompt content for prompts/system_prompt.txt:**
```
You are an expert AI career coach. You help professionals transition into
AI roles (ML Engineer, AI Product Manager, Solutions Engineer, AI Consultant).
Your answers are direct, actionable, and under 100 words.
You focus on practical advice: portfolio building, interview preparation,
skill gaps, and positioning strategy.
```

**Acceptance criteria:**
- `get_response("How do I get a job at Mistral AI?")` returns a non-empty string
- Response is under 150 words
- Prints to console: `[LLM] Response: "..."`

---

### Stage 4 — TTS service (response → audio)

**Goal:** Convert the LLM response to speech and play it via speakers using ElevenLabs TTS streaming.

**Tasks:**
- In `services/tts_service.py`, implement `speak(text: str) -> None`
- Use ElevenLabs TTS with streaming to minimize latency
- Use the ELEVENLABS_VOICE_ID from env
- Play audio directly via sounddevice as it streams
- Print latency from first byte received to audio start

**Acceptance criteria:**
- `speak("Hello, I am your AI career coach.")` plays audio through speakers
- Streaming: audio starts playing before the full response is generated
- Prints to console: `[TTS] Streaming started. First byte latency: Xms`

---

### Stage 5 — Judge service (response → quality scores)

**Goal:** Automatically score every LLM response on three criteria using a second Mistral call.

**Tasks:**
- In `services/judge_service.py`, implement `evaluate(question: str, response: str) -> dict`
- Load judge prompt from `prompts/judge_prompt.txt`
- Use `mistral-small-latest` (cheaper, sufficient for evaluation)
- Use Mistral structured output (JSON mode) to return a strict schema
- Return a dict with this exact structure:

```python
{
  "relevance": int,        # 1-5: does the response answer the question?
  "concision": int,        # 1-5: is the length appropriate?
  "tone": int,             # 1-5: is the tone professional and helpful?
  "overall": int,          # 1-5: global quality score
  "flags": list[str],      # e.g. ["hallucination_risk", "off_topic", "too_vague"]
  "justification": str     # 1-2 sentence explanation of the scores
}
```

**Judge prompt content for prompts/judge_prompt.txt:**
```
You are a strict evaluator of AI assistant responses.
You receive a question and a response from an AI career coach.
You must evaluate the response on four criteria, each scored 1 to 5:
- relevance: does the response directly answer the question asked?
- concision: is the response appropriately short (under 100 words)?
- tone: is the tone professional, direct, and encouraging?
- overall: global quality considering all criteria

You must also list any flags from this set: hallucination_risk, off_topic, too_vague, too_long.
Return ONLY a valid JSON object. No explanation outside the JSON.
```

**Acceptance criteria:**
- `evaluate("How do I get a job at Mistral?", "some response text")` returns a dict
- Dict contains all keys: relevance, concision, tone, overall, flags, justification
- All score values are integers between 1 and 5
- Prints to console: `[JUDGE] Scores: relevance=X concision=X tone=X overall=X flags=[...]`

---

### Stage 6 — Logger service and full voice loop

**Goal:** Wire all services together into a working voice loop, log every interaction to JSON.

**Tasks:**
- In `services/logger_service.py`, implement `log_interaction(entry: dict) -> None`
- Each log entry must contain:

```python
{
  "id": str,                  # uuid4
  "timestamp": str,           # ISO 8601
  "transcript": str,          # user question
  "response": str,            # LLM response
  "scores": dict,             # judge output
  "latency": {
    "stt_ms": int,
    "llm_ms": int,
    "tts_first_byte_ms": int
  },
  "tokens": {
    "prompt_tokens": int,
    "completion_tokens": int
  }
}
```

- Append to `logs/interactions.json` (create file if not exists)
- In `main.py`, implement the main voice loop:
  1. Press Enter to start recording
  2. STT → transcript
  3. LLM → response
  4. TTS → speak (non-blocking, audio plays while judge runs)
  5. Judge → scores
  6. Logger → save entry
  7. Print summary to console
  8. Loop back to step 1

**Acceptance criteria:**
- Full loop runs end-to-end without errors
- After 2 interactions, `logs/interactions.json` contains 2 valid entries
- Console prints a clean summary after each interaction:
  ```
  [LOOP] Question: "..."
  [LOOP] Response: "..."
  [LOOP] Scores: overall=4 | relevance=5 | concision=3 | tone=4
  [LOOP] Latency: STT=320ms LLM=850ms TTS=210ms
  [LOOP] Logged. Total interactions: 2
  ```

---

### Stage 7 — FastAPI backend and dashboard

**Goal:** Serve a minimal HTML/JS dashboard showing interaction history and quality trends.

**Tasks:**
- In `main.py`, add a FastAPI app running on DASHBOARD_PORT
- Implement two endpoints:
  - `GET /api/logs` — returns all entries from interactions.json
  - `GET /api/stats` — returns aggregated stats:
    ```python
    {
      "total_interactions": int,
      "avg_overall_score": float,
      "avg_latency_llm_ms": float,
      "flag_counts": dict,       # e.g. {"too_vague": 3, "off_topic": 1}
      "score_over_time": list    # list of {timestamp, overall} for charting
    }
    ```
- Run FastAPI and voice loop concurrently (use asyncio or threading)
- In `dashboard/index.html` + `dashboard/app.js`, build a minimal dashboard:
  - Header: "AI Career Coach — Monitoring Dashboard"
  - Stats row: total interactions, average overall score, average LLM latency
  - Line chart: overall score over time (use Chart.js from CDN)
  - Table: last 10 interactions with columns: timestamp, question (truncated),
    overall score, flags, LLM latency

**Acceptance criteria:**
- `python main.py` starts both the voice loop and the dashboard server
- Dashboard is accessible at `http://localhost:8000`
- After 3 interactions, dashboard shows correct stats and populated table
- Line chart renders with at least one data point
- Page auto-refreshes every 10 seconds

---

## Key constraints

- Never commit `.env` or `logs/interactions.json` to git
- All API calls must have try/except with explicit error messages
- TTS must stream (not wait for full audio before playing)
- Judge must use JSON structured output, not free-text parsing
- Dashboard must work without a build step (plain HTML + JS, no npm)

---

## How to run

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill env file
cp .env.example .env

# Run
python main.py

# Open dashboard
# http://localhost:8000
```

---

## Suggested git workflow

```bash
git init
git add .
git commit -m "stage-1: project scaffold"
# One commit per completed stage
```
