# ClinAI (voice CLI)

Real-time voice loop: Whisper (faster-whisper) → Ollama → Edge TTS (or gTTS).
Supports barge-in and clean exit commands.

## Setup

python -m venv .venv
. .venv/Scripts/activate # Windows
pip install -r requirements.txt

# Ensure Ollama is running locally.

## Run

python main.py

## Toggle Edge vs gTTS

Edit `main.py`:
USE_EDGE = True # or False

## Choose voice (Edge)

Inside `main_edge()`:
tts = EdgeTTSPlayer(voice="en-US-GuyNeural", rate="+10%")

## Exit commands

Say exactly: "exit", "quit", "stop", or "goodbye".

## Requirements

See requirements.txt
