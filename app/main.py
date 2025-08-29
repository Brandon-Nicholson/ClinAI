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
from app.services.call_service import start_call, end_call, set_intent, log_turn, was_resolved
from app.voice.synthesizer import speak_gtts, stop_speaking, EdgeTTSPlayer, USE_EDGE
from app.voice.transcriber import start_microphone, listen_and_transcribe_whisper
from app.voice.llm import query_ollama, add_to_history, main_system_prompt, info_system_prompt
from faster_whisper import WhisperModel
from intent_model.intent_classifier import classify_intent
import time
import re
import json

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
    chat_history = [{"role": "system", "content": main_system_prompt},
                    {"role": "system", "content": info_system_prompt}] # pre-load system prompts to context window
    llm_model = "llama3.1:8b"

    # Initialize EdgeTTS with chosen voice and rate
    tts_intro = EdgeTTSPlayer(rate="+25%", voice="en-US-RogerNeural")
    tts = EdgeTTSPlayer(rate="+15%", voice="en-US-AriaNeural")

    # start a call record
    call = start_call(patient.id, patient.phone)
    
    # initialize list of patient intents
    patient_intents = []
    
    # intro messages
    intro_msg = "Your call may be monitored or recorded for quality assurance. Exclusively say 'stop'.. or 'quit'.. at any time to exit the conversation."
    tts_intro.speak(intro_msg)
    add_to_history(chat_history, "system", intro_msg) # adds default responses to chat_history
    time.sleep(9)
    welcome_msg = f"Hi {patient.first_name}... I'm Ava. How can I assist you today?"
    tts.speak(welcome_msg)
    add_to_history(chat_history, "system", welcome_msg)
    time.sleep(5.5)

    # count number of times max wait time for input was exceeded
    max_wait_counter = 0
    
    # initially set LLM response to an empty string
    response = "" # needs to be assigned before listen_and_transcribe_whisper is called
    
    loop_convo = True
    try:
        while True:
            # before listening, cut off any ongoing speech
            tts.stop()

            # Start microphone stream
            q, stream = start_microphone()
            user_input = listen_and_transcribe_whisper(whisper_model, q, response)
            # Stop and close mic stream after transcribing
            stream.stop(); stream.close()

            # skip empties or junk (no letters/numbers)
            if not user_input or not re.search(r"[A-Za-z0-9]", user_input):
                repeat_msg = "Sorry, I didn’t catch that clearly. Could you repeat?"
                tts.speak(repeat_msg)
                add_to_history(chat_history, "assistant", repeat_msg)
                continue
            else:
                # revert counter back to 0 if utterance
                max_wait_counter = 0

            print(f"You: {user_input}")
            
            # get bool from was_resolved when convo ends
            if not loop_convo and user_input:
                resolved = was_resolved(user_input)
                tts.speak("Your feedback is appreciated, Goodbye!")
                time.sleep(3)
                break
            
            # add 1 to max_wait_counter if set wait time without speaking is exceeded
            if user_input == "max_wait_exceeded":
                max_wait_counter+=1
                
                # only allow 1 max_wait_exceeded during patient feedback
                if not loop_convo:
                    resolved = None
                    break
                
                # end the call if patient goes too long without speaking
                elif max_wait_counter >= 2:
                    tts.speak("Goodbye")
                    time.sleep(2)
                    break
                
                # try to get patient's attention if they're not speaking
                check_presence = "Are you still there?"
                tts.speak(check_presence)
                time.sleep(3)
                add_to_history(chat_history, "assistant", check_presence)
                continue
            
            if user_input.lower().strip() in ["exit", "quit", "stop", "goodbye", "good bye", 
                                              "exit.", "quit.", "stop.", "goodbye.", "good bye.",
                                              "exit!", "quit!", "stop!", "goodbye!", "good bye!"]:
                print("Goodbye!")
                
                # ask if query was resolved
                tts.speak(f"The conversation has ended. Was your query resolved today, {patient.first_name}?")
                time.sleep(5.5)
                tts.stop()
                loop_convo = False
                continue
            # log user input -> db
            log_turn(call.id, "user", user_input)
            
            # classify user intent
            intent = classify_intent(user_input, patient_intents)
            print(intent)
            
            print("Thinking...")
            
            # get LLM query
            response = query_ollama(user_input, chat_history, llm_model)
            print(f"AI: {response}")
            
            # log LLM output -> db
            log_turn(call.id, "assistant", response)

            # This plays asynchronously, but loop keeps running
            tts.speak(response)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:

        tts.stop()
        
        # update db with intent
        db_intents = json.dumps(patient_intents)
        set_intent(call.id, db_intents)
        
        end_call(call.id, resolved=resolved, escalated=False, notes="blank")

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