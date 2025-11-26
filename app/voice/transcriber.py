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

# This implementation is for conversation_loop.py, not the web app

# Open mic stream and push audio into a queue
def start_microphone(sample_rate: int = 16000, blocksize: int = 4000):

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
    # Quick RMS volume check to tell if someone’s talking
    
    a = np.frombuffer(buf_bytes, dtype=np.int16)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean((a.astype(np.float32))**2)))

def _pcm_bytes_to_float32(buf_bytes: bytes) -> np.ndarray:
    # Whisper wants float32 [-1, 1], but the mic gives us int16.
    
    a = np.frombuffer(buf_bytes, dtype=np.int16).astype(np.float32) # int16 -> int32 conversion
    return a / 32768.0

def _seg_conf(seg):
    # handle both spellings just in case
    return getattr(seg, "avg_logprob", getattr(seg, "avg_log_prob", -10.0))

# returns condfidence score for transcribed audio
def _avg_conf_and_text(segments):
    segs = list(segments)  # generator -> list
    if not segs:
        return -10.0, ""
    text = " ".join(s.text.strip() for s in segs).strip()
    conf = sum(_seg_conf(s) for s in segs) / max(len(segs), 1)
    return conf, text

def listen_and_transcribe_whisper(
    model,
    q,
    response,
    sample_rate=16000,
    rms_threshold=200,       # threshold for how loud input speech needs to be
    max_silence_frames=50,   # wait ~2 sec of silence
    hot_start_frames=2,      # ignore first few frames (avoid false triggers)
    max_buffer_seconds=10,   # hard max, ~10 sec of speech
    max_wait_seconds=10,     # hard timeout
    min_conf=-0.60,          # minimum confidence threshold
):
    import time
    import traceback
    import numpy as np

    print("🎧 Waiting for speech...")

    spoken_started = False
    warmups = 0
    buffer = bytearray()
    silence_streak = 0
    start_time = time.time()

    # add an additional 0.4s per word in the LLM's response (avg speech rate is 2.5 words/second)
    additional_wait_seconds = len(response.split()) * (1 / 2.5)
    total_wait_seconds = additional_wait_seconds + max_wait_seconds

    def transcribe_and_gate():
        # Convert PCM -> float32 numpy
        try:
            raw_bytes = bytes(buffer)
            if not raw_bytes:
                print("[STT DEBUG] Buffer empty, nothing to transcribe.")
                return ""

            audio_f32 = _pcm_bytes_to_float32(raw_bytes)
            audio_f32 = np.asarray(audio_f32, dtype="float32").flatten()
            print(f"[STT DEBUG] audio_f32 shape={audio_f32.shape}, dtype={audio_f32.dtype}")
        except Exception:
            print("Error converting PCM bytes to float32:")
            traceback.print_exc()
            return ""

        # Call Whisper with protection so GPU errors can't kill the process
        try:
            segments_iter, info = model.transcribe(
                audio_f32,
                language="en",
                beam_size=1,
                word_timestamps=False,
            )
            # force materialization in case it's a generator
            segments = list(segments_iter)
        except Exception:
            print("Whisper GPU transcribe error:")
            traceback.print_exc()
            return ""

        # Now compute avg_conf + text safely
        try:
            avg_conf, text = _avg_conf_and_text(segments)
        except Exception:
            print("Error computing avg_conf/text from segments:")
            traceback.print_exc()
            return ""

        print(f"[DEBUG] Transcribed={text!r} | avg_conf={avg_conf:.2f}")

        # make confidence threshold more lenient for short prompts
        word_count = len(text.split())
        if word_count < 3:
            adj_conf = avg_conf + 0.48  # big increase for 1–2 words
        elif word_count == 3:
            adj_conf = avg_conf + 0.20  # smaller increase for 3 words
        else:
            adj_conf = avg_conf         # no increase for 4+ words

        if adj_conf < min_conf:
            print(f"[DEBUG] adj_conf={adj_conf:.2f} below min_conf={min_conf:.2f}, treating as empty.")
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
                    print("[STT DEBUG] Waited too long for speech, returning None.")
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

