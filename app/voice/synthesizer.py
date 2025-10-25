"""
synthesizer.py

Text-to-Speech (TTS) playback utilities.

- Default: Microsoft Edge TTS (natural voices, async).
- pygame.mixer for playback and support interruption.
"""

import pygame
import io
import threading
import time
import edge_tts
import asyncio


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
        # Generates speech with Edge TTS and play it immediately
        
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
        
    def speak_and_wait(self, text, poll=0.03):
        print(f"Agent: {text}")
        # Synthesize + play and block until playback finishes
        # Wait for synthesis + .play() to be scheduled/completed
        fut = asyncio.run_coroutine_threadsafe(self._speak_async(text), self.loop)
        fut.result()  # wait until audio is loaded and playback started

        # Wait until pygame finishes playing this clip
        # busy becomes True shortly after .play()
        start_deadline = time.time() + 2.0  # guard if device is muted/etc.
        while not pygame.mixer.music.get_busy() and time.time() < start_deadline:
            time.sleep(poll)
        while pygame.mixer.music.get_busy():
            time.sleep(poll)

    def stop(self):
        # Stop any current playback
        stop_speaking()



    

