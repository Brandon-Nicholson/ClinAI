"""
synthesizer.py

Text-to-Speech (TTS) playback utilities.

- Default: Microsoft Edge TTS (natural voices, async).
- Fallback: Google gTTS (simple, requires internet).
- Both use pygame.mixer for playback and support interruption.
"""

import pygame
import io
import threading

# Try Edge TTS first
try:
    import edge_tts
    import asyncio
    USE_EDGE = True
except ImportError:
    edge_tts = None
    USE_EDGE = False

# Try gTTS as fallback
try:
    from gtts import gTTS
except ImportError:
    gTTS = None

pygame.mixer.init()

def stop_speaking():
    # Immediately cut off any current playback
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()


# ---------------------------
# Edge TTS implementation
# ---------------------------
class EdgeTTSPlayer:
    
    """
    Wrapper around Microsoft Edge TTS.
    Uses asyncio in a background thread to fetch audio and play it with pygame.
    """
    
    def __init__(self, rate, voice):
        if edge_tts is None:
            raise RuntimeError("edge-tts not installed. Run: pip install edge-tts")
        self.rate = rate
        self.voice = voice
        
        # Edge TTS requires asyncio - run an event loop in a separate thread
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    
    async def _speak_async(self, text):
        # Generate speech with Edge TTS and play it immediately
        
        # create temporary file to store mp3 data
        mp3_fp = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice=self.voice, rate=self.rate)

        # Stream audio chunks into memory
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_fp.write(chunk["data"])
        mp3_fp.seek(0)

        # Stop old playback before starting new one
        stop_speaking()
        pygame.mixer.music.load(mp3_fp)
        pygame.mixer.music.play()

    def speak(self, text):
        # Public method to speak text (schedules the async call)
        asyncio.run_coroutine_threadsafe(self._speak_async(text), self.loop)

    def stop(self):
        # Stop any current playback
        stop_speaking()

# ---------------------------
# gTTS implementation
# ---------------------------

# Keep a reference to the playback thread so we can stop/replace it
_playback_thread = None

def _play_audio(mp3_fp):
    # Load and play audio from a BytesIO file-like object
    pygame.mixer.music.load(mp3_fp)
    pygame.mixer.music.play()

def speak_gtts(text, lang='en'):
    """
    Speak text using Google gTTS.
    Runs playback in a background thread so the main loop isn’t blocked.
    """
    global _playback_thread
    tts = gTTS(text=text, lang=lang, slow=False)
    
    # Save the generated audio into memory (instead of a temp file)
    mp3_fp = io.BytesIO()
    tts.write_to_fp(mp3_fp)
    mp3_fp.seek(0)

    # Stop anything that’s already playing
    stop_speaking()
    
    # Play in a separate thread so the program keeps running
    _playback_thread = threading.Thread(target=_play_audio, args=(mp3_fp,), daemon=True)
    _playback_thread.start()



    

