"""
main.py

Entry point for ClinAI.

- Choose between EdgeTTS (default, better voices) and gTTS (fallback).
- Runs a simple "listen → transcribe → respond → speak" loop.
- Exit cleanly if user says "exit", "quit", "stop", or "goodbye".
"""
# Toggle which synthesizer to use
USE_EDGE = True # change this to False if you want to use gTTS

# Imports from modular voice pipeline
from app.ui.intake_form import run_intake_form
from app.services.call_service import start_call, end_call
from app.voice.synthesizer import speak_gtts, stop_speaking, EdgeTTSPlayer, USE_EDGE
from app.voice.transcriber import start_microphone, listen_and_transcribe_whisper
from app.voice.llm import query_ollama, main_system_prompt
from faster_whisper import WhisperModel
import time

# ---------------------------
# EdgeTTS version of main loop
# ---------------------------
def main_edge():
    # submit patient info before talking to agent
    patient = run_intake_form()
    if not patient:
        print("Call aborted: no patient submitted.")
        return
    
    print(f"Starting ClinAI agent for patient: {patient.first_name} {patient.last_name}")
    
    # Load Whisper model for STT (speech-to-text)
    print("Loading Whisper model...")
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

    # Store running conversation so the LLM has context
    chat_history = [{"role": "system", "content": main_system_prompt}] # pre-load system prompt to context window
    llm_model = "llama3.1:8b"

    # Initialize EdgeTTS with chosen voice and rate
    tts_intro = EdgeTTSPlayer(rate="+25%", voice="en-US-RogerNeural")
    tts = EdgeTTSPlayer(rate="+15%", voice="en-US-AriaNeural")

    # start a call record
    call = start_call(patient.id, patient.phone)
    
    # intro messages
    tts_intro.speak("Your call may be monitored or recorded for quality assurance. Exclusively say 'stop'.. or 'quit'.. at any time to exit the conversation.")
    time.sleep(9)
    tts.speak(f"Hi {patient.first_name}... I'm Ava. How can I assist you today?")
    time.sleep(5.5)

    try:
        while True:
            # before listening, cut off any ongoing speech
            tts.stop()

            # Start microphone stream
            q, stream = start_microphone()
            user_input = listen_and_transcribe_whisper(whisper_model, q)
            # Stop and close mic stream after transcribing
            stream.stop(); stream.close()

            if not user_input.strip():
                continue

            print(f"You: {user_input}")

            if user_input.lower().strip() in ["exit", "quit", "stop", "goodbye", "good bye", 
                                              "exit.", "quit.", "stop.", "goodbye.", "good bye.",
                                              "exit!", "quit!", "stop!", "goodbye!", "good bye!"]:
                print("Goodbye!")
                tts.speak(f"Goodbye, {patient.first_name}!")
                time.sleep(3)
                tts.stop()
                break

            print("Thinking...")
            response = query_ollama(user_input, chat_history, llm_model)
            print(f"AI: {response}")

            # This plays asynchronously, but loop keeps running
            tts.speak(response)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        tts.stop()
        end_call(call.id, resolved=True, escalated=False, notes="blankity blankity blank")

# ---------------------------
# gTTS version of main loop
# ---------------------------
def main_gtts():
    # submit patient info before talking to agent
    patient = run_intake_form()
    if not patient:
        print("No patient submitted. Exiting...")
        return
    
    print(f"Starting ClinAI agent for patient: {patient.first_name} {patient.last_name}")
    
    # Initialize components
    print("Loading Whisper model...")
    model_size = "base"
    whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    
    # Conversation settings
    chat_history = []
    llm_model = "llama3.1:8b"
    
    print("Voice AI agent ready! Speak now or say 'stop' to exit.")
    
    try:
        while True:
            # Start microphone
            q, stream = start_microphone()
            
            # Listen for user input
            user_input = listen_and_transcribe_whisper(whisper_model, q)

            # Close microphone
            stream.stop()
            stream.close()

            if not user_input or user_input.strip() == "":
                continue

            print(f"You: {user_input}")

            # Check for exit command
            if any(exit_cmd in user_input.lower() for exit_cmd in ["exit", "quit", "stop", "goodbye"]):
                print("Goodbye!")
                stop_speaking()   # stop any ongoing speech
                break

            # Get response from LLM
            print("Thinking...")
            response = query_ollama(user_input, chat_history, llm_model)
            print(f"AI: {response}")

            # Speak the response
            speak_gtts(response)

            print("Ready for next input...")
                
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        stop_speaking()

if __name__ == "__main__":
    if USE_EDGE:
        main_edge()
    else:
        main_gtts()