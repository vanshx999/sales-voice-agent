# Sales Voice Agent — Codebase Explanation

## Architecture Overview

The system is a modular AI-powered outbound sales calling agent. It reads leads from an
Excel file, calls them using AI voice, conducts natural sales conversations, and writes
results back to the Excel file. It runs entirely on your laptop with free APIs.

## File-by-File Breakdown

### 1. `config/settings.yaml` — Configuration Hub

All tunable parameters live here:

- **excel** — file path, sheet name, column mappings for the CRM
- **call** — max retries (3), retry delay (2 days), max duration (600s), pause timing (400ms between sentences), VAD threshold (0.03)
- **llm** — LLM provider (OpenAI-compatible via Groq), model (llama-3.3-70b-versatile), temperature, max tokens
- **tts** — TTS provider (elevenlabs), voice ID (Sarah), model (eleven_flash_v2_5)
- **stt** — speech-to-text (whisper)
- **conversation** — greeting delay, silence timeout, confidence

### 2. `config/prompts.yaml` — LLM Prompt Templates

Five templates that control the AI's behavior:

- **system_prompt** — Full sales persona: "You are an AI SDR..." with call structure (Intro → Discovery → Value Prop → Objection Handling → Closing → Wrap-up) and 8 guidelines
- **greeting_prompt** — Generates first sentence (under 20 words)
- **qualification_prompt** — Asks LLM to output structured JSON: qualified, budget, authority, need, timeline, requirements, pain_points
- **objection_response_prompt** — Handles objections naturally with company context
- **summary_prompt** — Produces structured JSON call summary: outcome, summary, requirements, objections, next_steps, follow_up, meeting_date

### 3. `config/knowledge_base.yaml` — Company Info

Contains all data the AI uses to answer questions:

- Company name, agent name, description
- Products (Workflow Automator, DataSync Pro) with features and pricing
- Use cases (invoice processing, CRM sync, lead assignment, etc.)
- Competitor analysis (vs Zapier, Make, UiPath)
- FAQ (implementation time, free trial, security, cancellation)
- Value propositions (80% reduction in data entry, 300% ROI, 15 hrs/week saved)

### 4. `src/lead_manager.py` — Excel CRM Reader/Writer

**`Lead` class** — Wraps a row from Excel:
- Properties: `is_pending` (status == "Pending"), `is_opted_out`, `should_call` (pending + not opted out)
- Stores all CRM columns as attributes

**`LeadManager` class** — CRUD for the Excel file:
- `load_leads()` — Reads Excel via pandas, filters out empty cells, assigns row indices
- `get_pending_leads()` — Returns only leads where both `is_pending` and `should_call` are true
- `update_lead(lead)` — Writes 8 fields back: status, qualification, summary, requirements, objections, follow-up, meeting_date, last_contacted timestamp
- `_save()` — Uses `pd.ExcelWriter` to overwrite the sheet

### 5. `src/conversation_engine.py` — LLM Brain

**`ConversationEngine` class** — Manages all AI dialogue:

- `__init__` — Loads settings, prompts, knowledge base; creates LLM client via `get_llm_client()`
- `start_call(lead)` — Resets conversation history, stores lead info
- `_build_system_prompt()` — Fills the `{company_name}`, `{agent_name}`, `{company_description}` placeholders
- `_build_context()` — Serializes products, use cases, FAQ, value props into text
- `generate_greeting()` — Calls LLM with greeting prompt, strips quotes
- `_llm_call(messages, max_tokens, retries=3)` — Core LLM wrapper:
  - Sends messages to Groq API
  - Catches `APITimeoutError`, `APIConnectionError`, `RateLimitError`, `APIError`
  - Retries 3 times with exponential backoff (3s, 6s, 9s)
  - Falls back to a varied response from `_fallback_response()` if all retries fail
- `process_input(user_input)` — Appends user message, builds full message array (system + context + history), calls LLM, appends and returns reply
- `qualify_lead()` — Extracts structured qualification JSON from full conversation
- `handle_objection(objection)` — Generates a natural 2-sentence response
- `generate_summary()` — Summarizes last 20 turns into structured JSON
- `_extract_json(text)` — Finds `{...}` in LLM output for reliable JSON parsing

### 6. `src/voice_agent.py` — Call Orchestrator

**`VoiceAgent` class** — Manages the full call lifecycle:

- `__init__` — Creates TTS engine, sets up mic mode flag, VAD threshold
- `make_call(phone, lead)` — Entry point: emits events, generates greeting, runs conversation loop, builds result
- `_run_conversation_loop(lead)` — Core loop (max 30 turns):
  1. Listen for input
  2. If no input on turn 1 → outcome = "no_answer"
  3. Check for end-call signal (goodbye/bye/hang up)
  4. Detect objections → route to `handle_objection()` or `process_input()`
  5. Speak the reply
  6. Check for not-interested → outcome = "not_interested"
  7. Check for meeting interest (explicit phrases: "book a meeting", "schedule a call", etc.) → book meeting
- `_speak(text)` — Splits text into sentences, feeds each to TTS engine, adds natural pauses (questions get longer pauses, short sentences shorter)
- `_vad_monitor()` — Background thread during speech: captures 250ms audio chunks, requires 3 consecutive above-threshold detections before triggering interruption
- `_listen()` — Uses mic (if `--mic` flag + tty + no prior failure) or falls back to text `input()`
- `_listen_mic()` — Records up to 30s, checks energy level, sends to Whisper for transcription
- `_text_input_fallback()` — Simple `input("[You] ")`
- `_transcribe()` — Loads Whisper "base" model, transcribes audio to text
- `_detect_objection()` — Keyword matching (12 objection patterns)
- `_detect_meeting_interest()` — Phrase matching (11 booking phrases)
- `_detect_not_interested()` — Phrase matching (8 rejection phrases)
- `_book_meeting()` — Asks for date/time, stores it
- `_build_call_result()` — Calls `generate_summary()` + `qualify_lead()` and packs into result dict

### 7. `src/tts_engine.py` — Text-to-Speech Module

Three backends, auto-selected via `settings.yaml`:

**`SayTTS`** — macOS built-in:
- Picks best available voice (Samantha → Karen → Moira → ...)
- Runs `say -v VoiceName -r rate` as subprocess

**`ElevenLabsTTS`** — Cloud (best quality):
- Uses `elevenlabs` SDK with `text_to_speech.convert()`
- Voice ID configurable (default: "Sarah" - EXAVITQu4vr4xnSDxMaL)
- Model: `eleven_flash_v2_5` (fast, good quality)
- Streams audio to temp WAV file, plays via `afplay`
- Falls back to SayTTS on error
- `clone_voice()` method for voice cloning from audio samples

**`PiperTTS`** — Local neural (open source):
- Runs ONNX models locally via `piper` binary
- Downloads model from HuggingFace if missing
- Falls back to SayTTS if model unavailable

### 8. `src/crm_updater.py` — Post-Call CRM Sync

**`CRMUpdater`** class:

- `update_after_call(lead, call_result)` — Maps outcomes to statuses:
  - meeting_booked → "Meeting Booked"
  - interested → "Interested"
  - not_interested → "Not Interested"
  - no_answer/timeout → "No Answer"
  - Maps qualification (yes→Qualified, maybe→Maybe, no→Not Qualified)
  - Sets summary, requirements, objections, follow_up, meeting_date
  - No-answer calls get a note: "No answer on last attempt"
  - Calls `lead_manager.update_lead()` to persist

### 9. `src/call_workflow.py` — Batch Processor

**`CallWorkflow`** class:

- `run_all(max_calls=0)` — Loads all pending leads, processes each sequentially with 5s delay between calls, prints summary at end
- `process_lead(lead)` — Calls `voice_agent.make_call()` then `crm_updater.update_after_call()`
- `_print_summary()` — Tabulates outcomes, prints per-lead results

### 10. `src/main.py` — Entry Point

CLI argument parser with 6 modes:

| Flag | Description |
|------|-------------|
| (none) | Interactive: call first pending lead |
| `--demo` | Demo mode with first pending lead |
| `--custom` | Demo with custom lead info (prompts or inline: `--custom 'Name,Phone,Company'`) |
| `--all` | Process all pending leads in batch |
| `--max N` | Process N pending leads |
| `--dry-run` | Simulate without LLM/voice |
| `--mic` | Enable microphone input + Whisper STT |

### 11. `src/utils.py` — Shared Utilities

- `_load_yaml()` — YAML file reader
- `load_settings()` / `load_prompts()` / `load_knowledge_base()` — Convenience wrappers
- `load_env()` — Loads `.env` file (API keys)
- `get_llm_client()` — Factory:
  - If `provider == "ollama"` → local OpenAI-compatible endpoint
  - Else → reads `base_url`, `api_key_env_var`, `model` from settings
  - Supports Groq, OpenRouter, NVIDIA, OpenAI

### 12. `data/leads.xlsx` — The CRM

Excel file with 15 columns:

| Column | Auto-populated |
|--------|----------------|
| Call Status | ✅ After every call |
| Lead Qualification | ✅ After every call |
| Conversation Summary | ✅ After every call |
| Customer Requirements | ✅ After every call |
| Objections Raised | ✅ After every call |
| Follow-up Date | ✅ If applicable |
| Meeting Date & Time | ✅ If booked |
| Last Contacted Timestamp | ✅ After every call |
| Opted Out | ❌ Manual (skipped by system) |

### 13. `requirements.txt` — Dependencies

| Package | Purpose |
|---------|---------|
| openpyxl | Excel read/write |
| pandas | DataFrame for CRM |
| pyyaml | Config file parsing |
| python-dotenv | .env file loading |
| openai | LLM API client |
| sounddevice | Audio recording |
| numpy | Audio processing |
| openai-whisper | Speech-to-text |
| elevenlabs | Text-to-speech |

## Data Flow

```
Excel File ──→ LeadManager ──→ Lead object ──→ VoiceAgent
                                                    │
                                          ┌─────────┴──────────┐
                                          ▼                    ▼
                                   ConversationEngine     TTS Engine
                                   (LLM via Groq)      (ElevenLabs)
                                          │                    │
                                          ▼                    ▼
                                     Sales Dialogue      Audio Output
                                          │
                                    ┌─────┴─────┐
                                    ▼           ▼
                              qualify_lead  generate_summary
                                    │           │
                                    ▼           ▼
                              CRMUpdater ──→ Excel File (updated)
```

## Cost Breakdown

| Service | Cost | Limits |
|---------|------|--------|
| Groq API | Free | 30 req/min on llama-3.3-70b |
| ElevenLabs | Free | 10,000 chars/month |
| Whisper | Local | Free (CPU) |
| Everything else | Local | Free (open source) |

**Total: $0/month** for light usage (up to ~50 short calls/month on free tiers).
