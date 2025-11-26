## ClinAI - A fully autonomous healthcare receptionist (voice-enabled)

**Preview:**

![ClinAI Screenshot](screenshots/readmd.png)

## Features Overview

- Voice-based conversation (browser + local)
- faster-whisper STT (large-v3, cuda, float16)
- Edge-TTS for more natural responses
- Patient intent classification (custom DistilBERT model)
- llama 3.1:8b for administrative lookups, reading availabilities and some edge-case interactions
- Appointment scheduling, rescheduling and cancellation logic (covering many edge-cases)
- Prescription refills (with fuzzy matching to compensate for STT handling of complex drug names)
- Fully structured SQL database for patients, calls, appointments, refills and transcripts.
- Database gets updated in real-time.
- State machine for robust conversation flow.
- Real-time web interface
- Configurable appointment availability system

## Architecture

```text
          ┌───────────────────┐
          │   Web Client      │
          │ (ClinAI UI)       │
          └───────┬───────────┘
                  │
                  │ HTTPS (text / audio base64)
                  ▼
        ┌───────────────────────┐
        │   FastAPI Backend     │
        └───────┬───────────────┘
                │
                │
     ┌──────────▼──────────┐
     │  Speech-to-Text     │
     │   (faster-whisper)  │
     └────────┬────────────┘
              │ transcript
              ▼
     ┌──────────────────────┐
     │ Intent Classifier    │
     │ (DistilBERT, rules)  │
     └────────┬─────────────┘
              │ intent + slots
              ▼
     ┌──────────────────────────┐
     │ Conversation State       │
     │  & Appointment Logic     │
     └────────┬─────────────────┘
              │
              │ ORM (SQLAlchemy)
              ▼
     ┌──────────────────────────┐
     │   PostgreSQL Database    │
     │ (patients, calls, appts) │
     └────────┬─────────────────┘
              │ response text
              ▼
     ┌──────────────────────┐
     │   Text-to-Speech     │
     │     (Edge-TTS)       │
     └────────┬─────────────┘
              │ audio base64
              ▼
        ┌───────────────────┐
        │   Web Client      │
        │  (plays audio &   │
        │   updates UI)     │
        └───────────────────┘
```

## Tech Stack

**Backend**

- Python 3.12
- FastAPI (HTTP API & routing)
- SQLAlchemy (ORM)
- PostgreSQL
- Uvicorn (ASGI Server)

**AI / ML**

- faster-whisper (speech-to-text)
- DistilBERT fine-tuned classifiers
- ollama (LLM host / inference engine)

**Voice & Audio**

- Edge-TTS (text-to-speech)
- FFmpeg - browser audio (WebM/Opus → WAV) conversion

**Frontend**

- JavaScript, HTML, CSS (browser client + UI)
- `navigator.mediaDevices.getUserMedia` + `MediaRecorder` for microphone capture
- Web Audio API (`AudioContext`, `AnalyserNode`) for silence detection

**DevOPS / Infrastrcuture**

- Cloudflared (secure HTTPS tunneling)

## Accuracy & Evaluation

- 42 / 42 test scenarios were passed
- The tests included various different scenarios where the user tried to schedule appointments, cancel appointments, get administrative information, refill a prescription or talk to a human rep.
- Overall average messages from the user per conversation was 2.45
- If you'd like to see how the tests were done + screenshots of the conversations & database as proof, go to: clinai/metrics/test_results.ipynb

## Local Setup & Installation

# Quickstart (OPTIONAL)

```bash
git clone https://github.com/Brandon-Nicholson/ClinAI.git
cd ClinAI
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
py -m classifiers.intent_model.train_intent
py -m app.db.create_tables
uvicorn app.clinai_web:app --reload
```

# Step by step

1. Clone the repo:

```bash
git clone https://github.com/Brandon-Nicholson/ClinAI.git
cd clinai
```

2. Create & activate new venv

```bash
python -m venv .venv
```

Linux/MacOS:

```bash
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Train classifiers (IMPORTANT)

The 3 DistilBERT classifiers are **not included** in the repository due to GitHub upload size limits.  
You must train them locally before starting the full ClinAI system.

From the project root (with your virtual environment activated), run:

```bash
py -m classifiers.intent_model.train_intent
py -m classifiers.confirmation_model.train_confirmation
py -m classifiers.appt_context_model.train_appt_context
```

5. PostgreSQL setup (REQUIRED)

Install PostgreSQL from https://www.postgresql.org/download/  
(Remember your superuser password, you'll need it)

Open a terminal and run:

```bash
psql -U postgres
```

It will ask for your password. Then run:

```bash
CREATE DATABASE clinai;
\q
```

Create your `.env` file  
Inside the project root, create `.env` containing:

```bash
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/clinai
```

Now from the project root, run:

```bash
py -m app.db.create_tables
```

This will instantly create all the tables. Refresh your database in PostgreSQL and verify the tables are there

6. Ollama Setup (REQUIRED)

Download it here (Windows,MacOS, Linux):
https://ollama.com/download

Pull (download) the recommended model: llama3.1:8b
or you can test with smaller models displayed here: https://ollama.com/library
(If you use a different model, make sure to replace "llama3.1:8b" with your new model's name everywhere in the clinai_web.py file)

```bash
ollama pull llama3.1:8b
```

Verify your model is there

```bash
ollama list
```

Run manually

```bash
ollama serve
```

Test your model

```bash
ollama run llama3.1:8b "Hello!"
```

If it prints a response, it's working

7. (OPTIONAL) Test conversation_loop.py
   conversation_loop.py is a CLI tool where most of the logic and conversation flow was derived from
   Running this file will allow you to speak in a conversation loop with the agent (may be more buggy):

```bash
py -m app.cli.conversation_loop
```

8. Test the ClinAI webapp locally
   From the project root (with your virtual environment activated), run:

```bash
uvicorn app.clinai_web:app --reload
```

Follow the link in the terminal (will look something like http://127.0.0.1:8000)
It should take you to the UI where you can test the ClinAI agent locally!

## Live Demo URL

- [useclinai.com](https://useclinai.com/)

## Contact

Built by Brandon N.

Email: brandonickk@gmail.com
