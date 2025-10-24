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
import re
import time

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

def _seg_conf(seg):
    # handle both spellings just in case
    return getattr(seg, "avg_logprob", getattr(seg, "avg_log_prob", -10.0))

def _avg_conf_and_text(segments):
    segs = list(segments)  # generator -> list
    if not segs:
        return -10.0, ""
    text = " ".join(s.text.strip() for s in segs).strip()
    conf = sum(_seg_conf(s) for s in segs) / max(len(segs), 1)
    return conf, text

# Listen once, then transcribe with Whisper
def listen_and_transcribe_whisper(model, q, response, sample_rate=16000,
                                  rms_threshold=1000,
                                  max_silence_frames=50,   # wait ~2 sec of silence
                                  hot_start_frames=2,      # ignore first few frames (avoid false triggers)
                                  max_buffer_seconds=10,   # hard max, ~10 sec of speech
                                  max_wait_seconds=10,      # hard timeout
                                  min_conf=-0.72):         # minimum confidence threshold
    print("🎧 Waiting for speech...")
    
    spoken_started = False
    warmups = 0
    buffer = bytearray()
    silence_streak = 0
    # start wait counter before patient speaks
    start_time = time.time()
    
    # add an additional 0.4s per word in the LLM's response (avg speech rate is 2.5 words/second)
    additional_wait_seconds = len(response.split()) * (1/2.5)
    total_wait_seconds = additional_wait_seconds + max_wait_seconds
    
    def transcribe_and_gate():
        audio_f32 = _pcm_bytes_to_float32(bytes(buffer))
        segments, _ = model.transcribe(audio_f32, language="en", beam_size=1, word_timestamps=False)
        avg_conf, text = _avg_conf_and_text(segments)
        print(f"[DEBUG] Transcribed={text!r} | avg_conf={avg_conf:.2f}")
        
        # make confidence threshold more lenient (-1.2) for 1-2 word prompts
        word_count = len(text.split())
        if word_count < 3:
            adj_conf = avg_conf + 0.48 # big bump for 1–2 words
        elif word_count == 3:
            adj_conf = avg_conf + 0.20 # smaller bump for 3 words
        else:
            adj_conf = avg_conf # no bump for 4+ words

        if adj_conf < min_conf:
            return ""
        
        # require at least one alpha char
        if not re.search(r"[A-Za-z]", text):
            return ""
        return text

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
                # if patient waits too long before speaking, return sentinel
                if (time.time() - start_time) > total_wait_seconds:
                    return None
                else:
                    continue
            spoken_started = True   # first voice detected
            start_time = time.time()
            
        # collect audio while talking
        buffer.extend(data)

        # track user silence
        if energy < rms_threshold:
            silence_streak += 1
        else:
            silence_streak = 0

        # enough silence after speech -> transcribe
        if silence_streak >= max_silence_frames and len(buffer) > 0:
            return transcribe_and_gate()

        # if speech too long, transcribe anyway (with the SAME gate)
        if len(buffer) >= sample_rate * max_buffer_seconds:
            return transcribe_and_gate()

