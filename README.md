# AI-AAI: AI-Assisted Accident Investigation & Reporting

A multi-agent LLM pipeline for intelligent workplace safety incident reporting and analysis, built for industrial steel manufacturing environments. AI-AAI transforms manual, error-prone incident documentation into a conversational AI experience with automated field extraction, semantic similarity search, and structured analytical output — all running entirely **on-premise**.

Developed at [Purdue University Northwest (CIVS)](https://pnw.edu/civs) in collaboration with Cleveland-Cliffs and the Steel Manufacturing Simulation and Visualization Consortium (SMSVC), funded by the **AIST Foundation Don Daily Grant**.

---

## The Problem

Workplace incident reporting in steel manufacturing is manual, inconsistent, and incomplete. Forms are tedious, near-misses go unreported, and critical early warnings are lost. According to Heinrich's Triangle, most major accidents are preceded by hundreds of minor incidents — but only if they're captured.

AI-AAI replaces static OSHA-style forms with a conversational AI agent that guides workers through reporting, extracts structured data from natural language, and surfaces historical context automatically.

## Key Results

- **46.7% reduction** in report completion time (18.4 → 9.8 minutes)
- **Follow-up requests dropped** from 42% to 12%
- **Completeness score** rose from 71 to 92 out of 100
- **92% entity recognition accuracy** via hybrid LLM + targeted extraction

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                     │
│            (Vite + Tailwind, dark/light)             │
└──────────────────────┬──────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────┐
│                  FastAPI Backend                     │
│  ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌────────┐ │
│  │  Intake   │ │ Extractor │ │Formatter│ │Flagging│ │
│  │  Agent    │ │   Agent   │ │  Agent  │ │ Agent  │ │
│  └──────────┘ └───────────┘ └─────────┘ └────────┘ │
│  ┌──────────┐ ┌───────────┐                         │
│  │Similarity│ │  Smart    │                         │
│  │  Agent   │ │ Report    │                         │
│  └──────────┘ └───────────┘                         │
└───┬──────────┬──────────┬──────────┬────────────────┘
    │          │          │          │
┌───▼───┐ ┌───▼───┐ ┌────▼───┐ ┌───▼────┐
│Postgre│ │Qdrant │ │ MinIO  │ │ Ollama │
│ SQL   │ │Vector │ │ Object │ │  LLM   │
│       │ │Search │ │Storage │ │Inferenc│
└───────┘ └───────┘ └────────┘ └────────┘
```

All services run locally — no cloud dependencies, no data leaves the premises.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python, async) |
| Frontend | React + Vite + Tailwind CSS |
| Database | PostgreSQL 16 |
| LLM Inference | Ollama (qwen3.5:9b) |
| Embeddings | nomic-embed-text (768d, cosine) |
| Vector Search | Qdrant |
| Object Storage | MinIO (S3-compatible) |
| Speech-to-Text | faster-whisper (base, int8, CPU) |
| Auth | JWT (python-jose + passlib/bcrypt) |
| Migrations | Alembic |

---

## Features

### Conversational Incident Intake
Workers describe what happened in natural language. The Intake Agent guides them through reporting with contextual follow-up questions, interactive widgets (date/time pickers, severity selectors, SIF case indicators), and skip handling for unknown fields.

### Three Incident Types
- **Personal Injuries** — accident type/agent, injury type/agent, SIF classification
- **Near Miss** — SIF case, life saving rules
- **Equipment Damage** — damage amount, activity type, incident activity/agent

### Intelligent Field Extraction
The Extractor Agent parses structured fields from conversational text. Question context (`last_question`) is passed to the LLM so short answers like "racks" are correctly mapped when asked about injury agents.

### Incident Type Inference
If a worker skips the type-selection buttons and describes the incident directly, the system infers the type and asks for confirmation before proceeding.

### Testimonial Preservation
The full conversation is stored as an Incident Context Document alongside the structured report — the worker's own words are never discarded.

### Semantic Similarity Search
On submission, reports are matched against historical incidents and previously submitted reports using weighted field scoring (Qdrant vector search pipeline available).

### Historical Data Ingestion
Admins upload existing incident records (XLS/XLSX). The pipeline normalizes column names, sanitizes NaN values for PostgreSQL JSON storage, and deduplicates by filename and source ID.

### Admin Review Workflow
Reports move through a status lifecycle: `submitted → under_review → approved / needs_more_info → closed`. Flagged reports surface prominently with reasons.

### Analytics Dashboard
Real-time breakdowns by incident type, severity, location, and monthly trend.

### Dark / Light Theme
Persisted to localStorage, toggled from any page.

---

## Project Structure

```
safety-chatbot/
├── backend/
│   ├── main.py                 # FastAPI app, lifespan hooks
│   ├── config.py               # pydantic-settings from .env
│   ├── database.py             # SQLAlchemy engine + session
│   ├── models/                 # User, Report, Unfinished, Historical
│   ├── schemas/                # Pydantic request/response models
│   ├── routers/                # auth, chat, reports, uploads, dashboard, historical
│   ├── agents/
│   │   ├── intake.py           # Conversation flow + session state
│   │   ├── extractor.py        # LLM field extraction with question context
│   │   ├── smart_intake.py     # Single-call Smart Report agent
│   │   ├── formatter.py        # Session → structured report + context doc
│   │   ├── flagging.py         # Missing field + severity flag logic
│   │   └── similarity.py       # Weighted scoring similarity search
│   ├── core/                   # Auth, Ollama client, Qdrant client, MinIO client
│   ├── migrations/             # Alembic versions
│   └── scripts/                # SQLite → PostgreSQL migration
└── frontend/
    ├── src/
    │   ├── pages/              # Login, Chat, Dashboard, Report, Admin
    │   ├── components/         # ThemeToggle, widgets
    │   ├── context/            # AuthContext, ThemeContext
    │   └── api/                # Axios client + endpoint modules
    ├── tailwind.config.js
    └── vite.config.js
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 16
- [Ollama](https://ollama.com/) with `qwen3.5:9b` and `nomic-embed-text` pulled
- [Qdrant](https://qdrant.tech/) binary
- [MinIO](https://min.io/) binary

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/ai-aai.git
cd ai-aai
```

### 2. Start Services

```bash
# PostgreSQL (ensure it's running on port 5432)

# Ollama
ollama serve
ollama pull qwen3.5:9b
ollama pull nomic-embed-text

# Qdrant
./qdrant.exe  # or qdrant on Linux/Mac — runs on port 6333

# MinIO
minio.exe server C:\minio\data --console-address :9001
```

### 3. Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file:

```env
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
DATABASE_URL=postgresql://postgres:password@localhost:5432/safety_chatbot_db
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:9b
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=incident_reports
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=safety-chatbot
```

Run migrations and start the server:

```bash
alembic upgrade head
uvicorn main:app --reload --port 8000
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

---

## Services Overview

| Service | Port | Purpose |
|---|---|---|
| PostgreSQL | 5432 | Relational database |
| Qdrant | 6333 | Vector search |
| MinIO | 9000 / 9001 | Object storage / Console |
| Ollama | 11434 | Local LLM inference |
| FastAPI | 8000 | Backend API |
| React (Vite) | 5173 | Frontend |

---

## Modular Agent Design

Each agent is independently packaged. Organizations with existing reporting systems can adopt individual agents without taking on the full platform:

| Agent | File | Purpose |
|---|---|---|
| Intake | `agents/intake.py` | Conversational session management and flow control |
| Extractor | `agents/extractor.py` | LLM-based field extraction with question context |
| Smart Report | `agents/smart_intake.py` | Single-call extraction + acknowledgment |
| Formatter | `agents/formatter.py` | Converts session to structured report + context document |
| Flagging | `agents/flagging.py` | Evaluates report completeness and severity indicators |
| Similarity | `agents/similarity.py` | Finds historically similar incidents via weighted scoring |

---

## Research Roadmap

| Period | Focus |
|---|---|
| Apr – Aug 2026 | Core Analytical Pipeline |
| Apr – Jun 2026 | Voice & Vision Integration |
| Aug – Nov 2026 | Multilingual & Accessibility |
| Sep – Nov 2026 | Predictive Analytics |
| Sep 2026 – Mar 2027 | Partner Deployment |
| Nov 2026 – Mar 2027 | Sensor Integration |

---

## Citation

If you use AI-AAI in your research, please cite:

> Dhwanil Chauhan and Qingyun Pu. "AI-AAI: Leveraging Large Language Models for Workplace Accident Investigations." AIST Foundation / SMSVC, 2025.

---

## Affiliation

**Purdue University Northwest**
Center for Innovation through Visualization and Simulation (CIVS)
Hammond, IN 46323

- Web: [pnw.edu/civs](https://pnw.edu/civs) | [steelconsortium.org](https://steelconsortium.org)
- Contact: civs@pnw.edu | (219) 989-2665
- Industry Partners: Cleveland-Cliffs, SMSVC
- Funding: AIST Foundation Don Daily Grant (2024–2025)

---

## License

This project is developed as part of academic research at Purdue University Northwest. Contact the authors for licensing inquiries.
