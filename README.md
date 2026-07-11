# Sales Voice Agent 🤖📞

AI-powered outbound sales calling agent that reads leads from Excel, calls them with natural AI voice, conducts intelligent sales conversations, qualifies prospects, books meetings, and writes results back to your CRM — all for **$0/month** using free API tiers.

Built with **Groq (llama-3.3-70b)** for LLM, **ElevenLabs** for voice, **Whisper** for speech-to-text, and **Python**.

## Demo

[Replace with your video link]

## Features

- **Excel CRM** — Add leads to `data/leads.xlsx`, the agent reads and updates automatically
- **Multilingual** — Supports English, Hindi, and Hinglish (Hindi+English mix) per lead
- **Natural Voice** — ElevenLabs "Sarah" voice (cloned or stock) for human-like conversation
- **Smart LLM** — Groq's `llama-3.3-70b-versatile` with custom system prompt, knowledge base, and structured JSON extraction
- **Call Flow** — Greeting → Discovery → Value Prop → Objection Handling → Closing → Meeting Booking
- **Qualification** — Extracts BANT (Budget, Authority, Need, Timeline) from every conversation
- **Interruption Handling** — VAD-based detection, requires 3 consecutive hits to prevent false positives
- **Batch Mode** — Process all pending leads automatically
- **Dry Run** — Test without API calls or voice output
- **Meeting Booking** — Captures date/time and writes to CRM

## Quick Start

```bash
# 1. Setup (creates venv, installs deps)
./setup.sh

# 2. Activate
source venv/bin/activate

# 3. Configure
cp .env.example .env
# Add your ELEVENLABS_API_KEY to .env
# Set GROQ_API_KEY in your shell environment
# Edit config/knowledge_base.yaml with your company info
# Add leads to data/leads.xlsx

# 4. Run
python -m src.main --dry-run            # Test without APIs
python -m src.main --demo               # Interactive demo (text input)
python -m src.main --demo --mic         # Demo with microphone
python -m src.main                      # Call first pending lead
python -m src.main --all                # Process all leads
python -m src.main --max 3             # Process 3 leads
python -m src.main --custom 'John,555-0100,Acme'  # Custom lead
```

## Architecture

```
data/leads.xlsx
      │
      ▼
┌──────────────┐    ┌───────────────────────┐    ┌──────────────┐
│ LeadManager  │───▶│ ConversationEngine    │◀───│ VoiceAgent   │
│ (Excel I/O)  │    │ (Groq llama-3.3-70b) │    │ (Call Flow)  │
└──────┬───────┘    └──────────┬────────────┘    └──────┬───────┘
       │                       │                        │
       ▼                       ▼                        ▼
┌──────────────┐    ┌───────────────────────┐    ┌──────────────┐
│ CRMUpdater   │    │ Knowledge Base        │    │ TTS Engine   │
│ (Excel Sync) │    │ (Company Info, FAQs)  │    │ (ElevenLabs) │
└──────────────┘    └───────────────────────┘    └──────────────┘
                                                 ┌──────────────┐
                                                 │ STT (Whisper)│
                                                 └──────────────┘
```

## Project Structure

```
├── config/
│   ├── settings.yaml           # All configuration (LLM, TTS, call params, Excel columns)
│   ├── prompts.yaml            # System prompt, greeting, qualification, objection, summary
│   └── knowledge_base.yaml     # Company info, products, competitors, FAQs
├── data/
│   └── leads.xlsx              # Excel CRM
├── src/
│   ├── main.py                 # CLI entry point (7 modes)
│   ├── lead_manager.py         # Excel read/write, lead filtering
│   ├── conversation_engine.py  # LLM-powered dialogue + JSON extraction
│   ├── voice_agent.py          # Call flow orchestrator
│   ├── tts_engine.py           # 3 TTS backends (ElevenLabs, Say, Piper)
│   ├── crm_updater.py          # Post-call CRM sync to Excel
│   ├── call_workflow.py        # Batch processing orchestration
│   └── utils.py                # Config/Env loading, LLM client factory
├── recordings/                 # Audio recordings (gitignored)
├── .env.example                # API key template
├── requirements.txt            # Python dependencies
├── setup.sh                    # One-command setup
└── explanation.md              # Full codebase breakdown
```

## Configuration

### `config/settings.yaml`

| Setting | Options | Default |
|---------|---------|---------|
| `llm.provider` | `openai`, `ollama` | `openai` |
| `llm.base_url` | API endpoint | `https://api.groq.com/openai/v1` |
| `llm.model` | Model name | `llama-3.3-70b-versatile` |
| `tts.provider` | `elevenlabs`, `say`, `piper` | `elevenlabs` |
| `tts.voice_id` | ElevenLabs voice ID | `EXAVITQu4vr4xnSDxMaL` (Sarah) |
| `call.max_retries` | Number of retry attempts | `3` |
| `call.retry_delay_days` | Days between retries | `2` |

### `config/knowledge_base.yaml`

Contains your company info: name, description, products (with features & pricing), use cases, competitor analysis, FAQs, and value propositions. The AI references this during calls.

## Excel CRM Schema

| Column | Description | Auto-filled |
|--------|-------------|-------------|
| Name | Prospect name | ❌ (manual) |
| Phone Number | Contact number | ❌ (manual) |
| Company | Company name | ❌ (manual) |
| Call Status | Pending / Meeting Booked / Not Interested / No Answer | ✅ |
| Lead Qualification | Qualified / Maybe / Not Qualified | ✅ |
| Conversation Summary | AI-generated summary | ✅ |
| Customer Requirements | Extracted needs | ✅ |
| Objections Raised | What objections were raised | ✅ |
| Follow-up Date | Next call date | ✅ |
| Meeting Date & Time | Booked meeting | ✅ |
| Last Contacted | Auto-timestamp | ✅ |
| Opted Out | TRUE/FALSE | ❌ (manual) |

## API Keys & Costs

| Service | What it's used for | Cost | Limit |
|---------|-------------------|------|-------|
| [Groq](https://console.groq.com) | LLM (llama-3.3-70b) | Free | 30 req/min |
| [ElevenLabs](https://elevenlabs.io) | Text-to-speech | Free | 10,000 chars/month |
| Whisper (OpenAI) | Speech-to-text | Free | Local (CPU) |

**Total: $0/month** for light use (~50 short calls/month).

## Extending

- **New LLM providers**: Add to `get_llm_client()` in `src/utils.py` (works with OpenAI, Groq, OpenRouter, Ollama)
- **Custom prompts**: Edit `config/prompts.yaml`
- **PSTN calling**: Connect Twilio (env vars described in `.env.example`)
- **Scheduling**: Use cron or n8n to run `python -m src.main --max 10`
- **New data sources**: Subclass `LeadManager` for HubSpot, Salesforce, etc.

## Demo Video Script (3 min)

1. **Intro (30s)**: Show project structure, explain the architecture
2. **Config (30s)**: Show `settings.yaml`, `knowledge_base.yaml`, leads
3. **Demo Call (60s)**: Run `--demo`, simulate a conversation with a lead
4. **CRM Update (30s)**: Show Excel with call results, qualification, meeting
5. **Wrap-up (30s)**: Recap — $0/month, 6 Python files, 3 free APIs

## License

MIT
