import pygame
import io
import threading
from gtts import gTTS

# Optional: Edge TTS
try:
    import edge_tts
    import asyncio
except ImportError:
    edge_tts = None

pygame.mixer.init()

# ---------------------------
# gTTS implementation
# ---------------------------
_playback_thread = None

def _play_audio(mp3_fp):
    pygame.mixer.music.load(mp3_fp)
    pygame.mixer.music.play()

def speak_gtts(text, lang='en'):
    """Non-blocking TTS using gTTS"""
    global _playback_thread
    tts = gTTS(text=text, lang=lang, slow=False)
    mp3_fp = io.BytesIO()
    tts.write_to_fp(mp3_fp)
    mp3_fp.seek(0)

    stop_speaking()
    _playback_thread = threading.Thread(target=_play_audio, args=(mp3_fp,), daemon=True)
    _playback_thread.start()

def stop_speaking():
    """Stop current playback immediately"""
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()

# ---------------------------
# Edge TTS implementation
# ---------------------------
class EdgeTTSPlayer:
    def __init__(self, voice="en-US-AvaMultilingualNeural", rate="+0%"):
        if edge_tts is None:
            raise RuntimeError("edge-tts not installed. Run: pip install edge-tts")
        self.voice = voice
        self.rate = rate
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    async def _speak_async(self, text):
        mp3_fp = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice=self.voice, rate=self.rate)

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_fp.write(chunk["data"])
        mp3_fp.seek(0)

        stop_speaking()  # stop old playback first
        pygame.mixer.music.load(mp3_fp)
        pygame.mixer.music.play()

    def speak(self, text):
        asyncio.run_coroutine_threadsafe(self._speak_async(text), self.loop)

    def stop(self):
        stop_speaking()




    

