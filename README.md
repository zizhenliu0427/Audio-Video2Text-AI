# Audio-Video2Text-AI

[English](README.md) | [中文](README.zh.md)

A cross-platform audio/video transcription tool with CLI, Web, and Desktop interfaces. Extracts audio from video files, transcribes speech using multiple AI providers, and optionally labels speakers, translates, and generates meeting notes.

## Features

- **Direct video input** — select any video/audio file (mp4, mkv, mov, mp3, wav, etc.), ffmpeg automatically extracts audio
- **Auto segmentation** — splits long audio into short segments (default 180s) to avoid model truncation and hallucination
- **Speaker diarisation** — uses audio understanding models to label different speakers (Speaker 1, Speaker 2, or real names)
- **Repetition detection** — automatically detects and flags ASR hallucination loops
- **Encrypted API key storage** — keys are encrypted with machine-bound Fernet encryption
- **Multi-provider ASR** — MiMo, OpenAI STT, local Whisper
- **Multi-provider LLM** — ChatGPT, Claude, Kimi, MiniMax, MiMo, Ollama
- **Three interfaces** — CLI script, Web app (FastAPI + Next.js), Desktop app (Electron)

## Supported AI Providers

### ASR (Listening)

| Provider | Direct Audio Input | Languages | Status |
|----------|-------------------|-----------|--------|
| Xiaomi MiMo ASR | ✅ | zh, en, auto | ✅ Available |
| OpenAI Speech-to-Text | ✅ | 50+ languages | Planned |
| Local Whisper / faster-whisper | ✅ | 99 languages | Planned |

### LLM (Organising)

| Provider | Audio Input | Text Processing | Status |
|----------|------------|----------------|--------|
| Xiaomi MiMo v2.5 / Omni | ✅ | ✅ | ✅ Available |
| OpenAI / ChatGPT | ✅ | ✅ | Planned |
| Anthropic Claude | ❌ | ✅ | Planned |
| Moonshot Kimi | ❌ | ✅ | Planned |
| MiniMax | ❌ | ✅ | Planned |
| Local LLM (Ollama) | ❌ | ✅ | Planned |

> **Architecture note**: This tool separates "listening" (ASR) from "organising" (LLM post-processing). Not all models can directly process audio — Claude, Kimi, MiniMax, and local LLMs work on the transcribed text for speaker labeling, translation, summarisation, and meeting notes.

## Tech Stack

```
┌─────────────────────────────────────────────────┐
│              Electron Desktop App                │
│  ┌───────────────────────────────────────────┐  │
│  │         Next.js Frontend (React)          │  │
│  │   Pages / Components / Real-time UI       │  │
│  └──────────────────┬────────────────────────┘  │
│                     │ HTTP / WebSocket           │
│  ┌──────────────────▼────────────────────────┐  │
│  │         FastAPI Backend (Python)          │  │
│  │   API Routes / WebSocket / Auth           │  │
│  │   ┌─────────────────────────────────┐     │  │
│  │   │   Core Engine (Python)          │     │  │
│  │   │   ASR / LLM / FFmpeg / Pipeline │     │  │
│  │   └─────────────────────────────────┘     │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

| Layer | Technology | Role |
|-------|-----------|------|
| **Frontend** | Next.js + React + TypeScript | UI, file upload, real-time progress, settings |
| **Backend** | FastAPI (Python) | API routes, WebSocket, auth, config management |
| **Core Engine** | Python | ASR providers, LLM providers, FFmpeg, pipeline |
| **Desktop** | Electron | Cross-platform shell, native file access, system tray |
| **CLI** | Python (argparse) | Direct command-line usage |

## Quick Start (CLI)

### Prerequisites

- Python 3.10+
- ffmpeg installed and in PATH
  - Windows: `winget install Gyan.FFmpeg`
  - Mac: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

### Install

```bash
pip install openai cryptography
```

### Run

```bash
python mimo_choose_file_transcribe.py
```

The script will guide you through:

1. **API Key setup** — enter your MiMo API key (saved encrypted for next time)
2. **Select model** — ASR (pure transcription) / v2.5 / Omni (speaker labeling)
3. **Select language** — Chinese / English / Auto
4. **Select file** — pick any video or audio file via file dialog
5. **Auto process** — extract audio, segment, transcribe, save results

### Command-line options

```bash
python mimo_choose_file_transcribe.py --segment-seconds 180 --bitrate 128k
```

| Option | Default | Description |
|--------|---------|-------------|
| `--segment-seconds` | 180 | Segment length in seconds |
| `--bitrate` | 128k | MP3 bitrate for audio extraction |
| `--prompt` | (built-in) | Custom prompt for speaker diarisation |

### Environment variables

```bash
MIMO_API_KEY=sk-xxxxx        # or tp-xxxxx for Token Plan
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
```

## Output

Results are saved next to the original file:

```
meeting.mp4
meeting.mp3                          # extracted audio (kept)
meeting_mimo_work/                   # working directory
  parts_asr/                         # segmented audio parts
    part_001.mp3
    part_002.mp3
    ...
meeting.omni.speaker_transcript.txt  # final transcript
```

## Roadmap

### v0.1 — CLI MVP ✅
- [x] MiMo ASR / v2.5 / Omni transcription
- [x] Auto segmentation with repetition detection
- [x] Encrypted API key persistence
- [x] Speaker diarisation via prompt
- [x] Chinese + English language support

### v0.2 — Multi-Provider
- [ ] Multi-provider ASR: OpenAI STT, local Whisper (faster-whisper)
- [ ] Multi-provider LLM: ChatGPT, Claude, Kimi, MiniMax, Ollama
- [ ] ASR + LLM pipeline architecture (ASR for listening, LLM for organising)
- [ ] Output formats: SRT subtitles, VTT, JSON with timestamps
- [ ] Batch processing (entire folder)
- [ ] YAML config file support

### v0.3 — Advanced Features
- [ ] pyannote / WhisperX for professional diarisation
- [ ] Auto chapter detection
- [ ] Bilingual subtitles
- [ ] Meeting notes / summary generation
- [ ] Fully offline mode (local Whisper + Ollama)
- [ ] pip-installable package (`pip install audio-video2text`)

### v0.4 — Web App (FastAPI + Next.js)
- [ ] FastAPI backend with REST API + WebSocket
- [ ] Next.js frontend with React + TypeScript
- [ ] Browser-based file upload and transcription
- [ ] Real-time progress display via WebSocket
- [ ] User auth & API key management via web UI
- [ ] Task queue for long-running jobs
- [ ] Docker Compose deployment (optional, for server hosting)

### v0.5 — Electron Desktop App
- [ ] Electron shell wrapping FastAPI + Next.js
- [ ] Bundled Python runtime (PyInstaller / python-embedded)
- [ ] Native file drag-and-drop
- [ ] System tray & desktop notifications
- [ ] Auto-update mechanism (electron-updater)
- [ ] Bundled ffmpeg & Whisper models (fully offline capable)

## Project Structure (planned)

```
Audio-Video2Text-AI/
├── README.md
├── LICENSE
├── .gitignore
│
├── backend/                        # FastAPI + Core Engine
│   ├── requirements.txt
│   ├── main.py                     # FastAPI app entry
│   ├── api/
│   │   ├── routes/
│   │   │   ├── transcribe.py       # POST /api/transcribe
│   │   │   ├── providers.py        # GET /api/providers
│   │   │   └── tasks.py            # GET /api/tasks/{id}
│   │   └── websocket.py            # WebSocket progress
│   ├── core/
│   │   ├── config.py               # Encrypted config
│   │   ├── pipeline.py             # ASR → LLM pipeline
│   │   └── task_queue.py           # Background task management
│   ├── providers/
│   │   ├── asr/
│   │   │   ├── base.py
│   │   │   ├── mimo_asr.py
│   │   │   ├── openai_asr.py
│   │   │   └── local_whisper.py
│   │   └── llm/
│   │       ├── base.py
│   │       ├── openai_chat.py      # ChatGPT / Kimi / MiniMax
│   │       ├── claude.py
│   │       ├── mimo_chat.py
│   │       └── ollama.py
│   ├── media/
│   │   ├── ffmpeg.py               # Audio extraction & segmentation
│   │   └── picker.py               # File picker (CLI only)
│   ├── prompts/
│   │   ├── speaker_zh.txt
│   │   └── speaker_en.txt
│   └── output/
│       └── writers.py              # txt / srt / vtt / json
│
├── frontend/                       # Next.js
│   ├── package.json
│   ├── next.config.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # Home / upload
│   │   │   ├── transcribe/
│   │   │   │   └── page.tsx        # Transcription progress
│   │   │   ├── history/
│   │   │   │   └── page.tsx        # Past transcriptions
│   │   │   └── settings/
│   │   │       └── page.tsx        # API keys & providers
│   │   ├── components/
│   │   │   ├── FileDropzone.tsx
│   │   │   ├── ProviderSelect.tsx
│   │   │   ├── ProgressStream.tsx
│   │   │   └── TranscriptViewer.tsx
│   │   └── lib/
│   │       └── api.ts              # API client
│   └── public/
│
├── electron/                       # Electron shell
│   ├── package.json
│   ├── main.ts                     # Electron main process
│   ├── preload.ts                  # Bridge main ↔ renderer
│   └── builder.yml                 # electron-builder config
│
├── cli/                            # CLI entry (current script)
│   └── mimo_choose_file_transcribe.py
│
└── examples/
    └── config.example.yaml
```

## Development

### CLI (current)

```bash
python mimo_choose_file_transcribe.py
```

### Web App (planned)

```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

### Electron (planned)

```bash
cd electron && npm install
npm run dev        # development
npm run build      # packaged app
```

## Licence

MIT
