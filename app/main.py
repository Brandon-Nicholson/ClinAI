# main.py
USE_EDGE = True # change this to False if you want to use gTTS

from voice.synthesizer import speak_gtts, stop_speaking, EdgeTTSPlayer
from voice.transcriber import start_microphone, listen_and_transcribe_whisper
from voice.llm import query_ollama
from faster_whisper import WhisperModel
import time

def main_edge():
    print("Loading Whisper model...")
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

    chat_history = []
    llm_model = "llama3.1:8b"

    tts = EdgeTTSPlayer(voice="en-US-AvaMultilingualNeural", rate="+15%")

    print("Voice AI agent ready! Speak now or say 'exit' to quit.")

    try:
        while True:
            # before listening, cut off any ongoing speech
            tts.stop()

            q, stream = start_microphone()
            user_input = listen_and_transcribe_whisper(whisper_model, q)
            stream.stop(); stream.close()

            if not user_input.strip():
                continue

            print(f"You: {user_input}")

            if user_input.lower().strip() in ["exit", "quit", "stop", "goodbye", 
                                              "exit.", "quit.", "stop.", "goodbye.",
                                              "exit!", "quit!", "stop!", "goodbye!"]:
                print("Goodbye!")
                tts.speak("Goodbye!")
                time.sleep(3)
                tts.stop()
                break

            print("Thinking...")
            response = query_ollama(user_input, chat_history, llm_model)
            print(f"AI: {response}")

            # This plays asynchronously, but loop keeps running
            tts.speak(response)

            print("Ready for next input...")

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        tts.stop()

def main_gtts():
    # Initialize components
    print("Loading Whisper model...")
    model_size = "base"
    whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    
    # Conversation settings
    chat_history = []
    llm_model = "llama3.1:8b"
    
    print("Voice AI agent ready! Speak now or press Ctrl+C to exit.")
    
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
                stop_speaking()   # <-- stop any ongoing speech
                break

            # Get response from LLM
            print("Thinking...")
            response = query_ollama(user_input, chat_history, llm_model)
            print(f"AI: {response}")

            # Speak the response (non-blocking now)
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