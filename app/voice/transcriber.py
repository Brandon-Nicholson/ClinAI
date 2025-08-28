"""
transcriber.py

Microphone + Whisper speech-to-text loop.

- Uses sounddevice to grab audio from the mic.
- Buffers chunks until you stop talking (silence detection).
- Runs through faster-whisper and spits out the recognized text.
"""

from faster_whisper import WhisperModel
import queue
import sounddevice as sd
import numpy as np

def start_microphone(sample_rate: int = 16000, blocksize: int = 4000):
    """
    Open mic stream and push audio into a queue.
    Returns (queue, stream).
    """
    q = queue.Queue()

    def callback(indata, frames, time, status):
        if status: print(status)
        q.put(bytes(indata))

    stream = sd.RawInputStream(
        samplerate=sample_rate, blocksize=blocksize, dtype='int16',
        channels=1, callback=callback
    )
    stream.start()
    return q, stream

# Helpers
def rms_int16(buf_bytes: bytes) -> float:
    # Quick RMS (volume) check to tell if someone’s talking.
    
    a = np.frombuffer(buf_bytes, dtype=np.int16)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean((a.astype(np.float32))**2)))

def _pcm_bytes_to_float32(buf_bytes: bytes) -> np.ndarray:
    # Whisper wants float32 [-1, 1], but the mic gives us int16.
    
    a = np.frombuffer(buf_bytes, dtype=np.int16).astype(np.float32)
    return a / 32768.0  # Whisper expects float32 in [-1.0, 1.0]

# Listen once, then transcribe with Whisper
def listen_and_transcribe_whisper(model, q, sample_rate=16000,
                                  rms_threshold=400,
                                  max_silence_frames=50,   # wait ~2 sec of silence
                                  hot_start_frames=2,      # ignore first few frames (avoid false triggers)
                                  max_buffer_seconds=10):  # hard max, ~10 sec of speech
    print("🎧 Waiting for speech...")

    spoken_started = False
    warmups = 0
    buffer = bytearray()
    silence_streak = 0

    while True:
        data = q.get()

        # ignore first couple frames while mic turns on
        if warmups < hot_start_frames:
            warmups += 1
            continue

        energy = rms_int16(data)

        # Wait until voice starts
        if not spoken_started:
            if energy < rms_threshold:
                continue
            spoken_started = True   # first voice detected

        # collect audio while talking
        buffer.extend(data)

        # track user silence
        if energy < rms_threshold:
            silence_streak += 1
        else:
            silence_streak = 0

        # return text if enough silence detected after speech
        if silence_streak >= max_silence_frames and len(buffer) > 0:
            audio_f32 = _pcm_bytes_to_float32(bytes(buffer))
            segments, _ = model.transcribe(audio_f32, language="en", beam_size=1)
            text = "".join(seg.text for seg in segments).strip()
            return text

        # if speech too long, return any trasncribed text
        if len(buffer) >= sample_rate * max_buffer_seconds:
            audio_f32 = _pcm_bytes_to_float32(bytes(buffer))
            segments, _ = model.transcribe(audio_f32, language="en", beam_size=1)
            text = "".join(seg.text for seg in segments).strip()
            return text

