<h1 align="center">
  🎬 CaptionForge
</h1>

<h4 align="center">AI-powered subtitle generation — upload a video, get perfectly timed subtitles in seconds.</h4>

<p align="center">
  <a href="#key-features">Key Features</a> •
  <a href="#processing-pipeline">Pipeline</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#project-structure">Structure</a> •
  <a href="#installation">Installation</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#license">License</a>
</p>

---

## Overview

CaptionForge is a full-stack web application that generates professional-quality subtitle files (`.srt`) from video uploads. It combines local machine learning for speech recognition with large language model intelligence for grammatical refinement — producing studio-quality subtitles at zero cost.

## Key Features

- 🌍 **Multi-Language Support** — Automatic language detection across English, Russian, Japanese, German, and French.
- 🧠 **Dual-AI Pipeline** — Local ASR via Faster-Whisper + cloud LLM refinement via Gemma 3:12B.
- ✨ **Smart Subtitle Enhancement** — Fixes spelling, grammar, punctuation, named entities, and ASR hallucinations while preserving speaker intent.
- 📦 **Large File Handling** — Streams uploads up to 100MB using chunked transfer to avoid memory spikes.
- 🎯 **Real-time Progress** — Live progress tracker with step-by-step pipeline visibility in the UI.
- 📥 **One-Click Download** — Preview subtitles in-browser, copy to clipboard, or download the `.srt` file directly.

---

## Processing Pipeline

This is the core AI pipeline that powers CaptionForge:

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────────┐     ┌────────────────┐     ┌──────────────┐
│  Video File  │────▶│  Audio Extractor  │────▶│  Speech Recognition │────▶│ LLM Refinement │────▶│  SRT Output  │
│  (Upload)    │     │  (FFmpeg)         │     │  (Faster-Whisper)   │     │ (Gemma 3:12B)  │     │  (Download)  │
└──────────────┘     └──────────────────┘     └─────────────────────┘     └────────────────┘     └──────────────┘
```

### Pipeline Stages

| Stage | Tool | What It Does |
|-------|------|-------------|
| **1. Upload** | FastAPI | Validates file type/size, saves to disk with unique task ID |
| **2. Audio Extraction** | FFmpeg | Strips audio track from video container → lossless `.wav` |
| **3. Speech Recognition** | Faster-Whisper | Runs CTC-based ASR on audio, detects language, outputs timestamped segments |
| **4. Transcript Enhancement** | Gemma 3:12B (OpenRouter) | Corrects grammar, spelling, punctuation, named entities using strict subtitle editor rules |
| **5. SRT Compilation** | Python | Converts enhanced JSON segments into standard SubRip (`.srt`) format |

### LLM Enhancement Rules

The Gemma model follows a strict system prompt that enforces:
- ✅ Fix spelling, grammar, capitalization, punctuation
- ✅ Correct named entities (people, places, organizations)
- ✅ Remove hallucinated/nonsensical ASR words (high confidence only)
- ❌ Never summarize, paraphrase, translate, or censor
- ❌ Never change timestamps, merge/split blocks, or reorder subtitles
- ❌ If unsure about a correction → keep original text

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19, Vite, Vanilla CSS, Lucide Icons |
| **Backend API** | Python 3.12, FastAPI, Uvicorn |
| **Audio Processing** | FFmpeg |
| **Speech Recognition** | Faster-Whisper (CTranslate2) |
| **LLM Enhancement** | Gemma 3:12B via OpenRouter API |

---

## Project Structure

```
CaptionForge/
├── frontend/                    # React + Vite frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── Header.jsx       # App title & tagline
│   │   │   ├── InfoBox.jsx      # Language badges & constraints
│   │   │   ├── UploadZone.jsx   # Drag-and-drop file upload
│   │   │   ├── ProgressTracker.jsx  # Real-time pipeline progress
│   │   │   └── ResultsPanel.jsx # SRT preview, copy & download
│   │   ├── App.jsx              # Main application layout
│   │   └── index.css            # Complete design system
│   ├── package.json
│   └── vite.config.js
│
├── backend/                     # FastAPI backend
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes.py        # API endpoints (upload, status, download)
│   │   │   └── schemas.py       # Pydantic request/response models
│   │   ├── core/
│   │   │   ├── config.py        # Application settings & env vars
│   │   │   └── logging.py       # Structured logging configuration
│   │   ├── services/
│   │   │   ├── audio_extractor.py   # FFmpeg audio extraction
│   │   │   ├── whisper_service.py   # Faster-Whisper ASR
│   │   │   ├── gemma_service.py     # Gemma LLM transcript enhancement
│   │   │   └── subtitle_service.py  # SRT file compilation
│   │   └── utils/
│   │       └── file_utils.py    # File validation & cleanup
│   ├── main.py                  # FastAPI application entry point
│   ├── requirements.txt         # Python dependencies
│   └── .env.example             # Environment variable template
│
├── run.bat                      # One-click startup (frontend + backend)
├── .gitignore
└── README.md
```

---

## Installation

### Prerequisites

| Requirement | Version |
|------------|---------|
| Python | 3.12+ |
| Node.js | 18+ |
| FFmpeg | Any recent version, must be in system `PATH` |

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/CaptionForge.git
cd CaptionForge
```

### 2. Backend Setup
```bash
# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\activate        # Windows
source .venv/bin/activate      # Mac/Linux

# Install dependencies
pip install -r backend/requirements.txt
```

### 3. Configure Environment
Create a `.env` file inside the `backend/` directory:
```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
```
> Get a free API key at [openrouter.ai](https://openrouter.ai)

### 4. Frontend Setup
```bash
cd frontend
npm install
cd ..
```

### 5. Run the Application
```bash
# Windows — starts both servers with one command:
.\run.bat
```

| Service | URL |
|---------|-----|
| Frontend | `http://localhost:5173` |
| Backend API Docs | `http://localhost:8000/docs` |

---

## Deployment

CaptionForge is deployed using two free-tier services:

| Component | Platform | Why |
|-----------|----------|-----|
| **Frontend** | GitHub Pages | Free static site hosting, perfect for React builds |
| **Backend** | Hugging Face Spaces | Free Docker hosting with 16GB RAM — ideal for ML workloads like Faster-Whisper |

### Frontend → GitHub Pages
The React app is built into static files and served via GitHub Pages at no cost.

### Backend → Hugging Face Spaces
The FastAPI backend is containerized with Docker (including FFmpeg and Faster-Whisper) and deployed to a Hugging Face Docker Space, which provides the compute resources needed for real-time speech recognition.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/subtitles/upload` | Upload a video file to start processing |
| `GET` | `/api/v1/subtitles/status/{task_id}` | Poll the current processing status |
| `GET` | `/api/v1/subtitles/download/{task_id}` | Download the generated `.srt` file |

---

## License

MIT
